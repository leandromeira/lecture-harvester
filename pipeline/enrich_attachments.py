import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_processing_logger
from pipeline.summarize import get_ai_client, call_ai, extract_json_block

logger = setup_processing_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched" / "materials"
STATE_PATH = PROJECT_ROOT / "config" / "storage_state.json"


def clean_name(value: str) -> str:
    import re
    value = value or "material"
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", value).strip("-")
    return cleaned or "material"


def detect_material_type(url: str) -> str:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if "github.com" in host:
        segments = [s for s in parsed.path.split("/") if s]
        if len(segments) >= 2:
            return "github_repo"
    if "notion.so" in host or "notion.site" in host:
        return "notion_page"
    if any(path.endswith(ext) for ext in (".pdf", ".zip", ".ppt", ".pptx", ".doc", ".docx")):
        return "direct_file"
    return "external_link"


def to_relative(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def summarize_text_with_ai(title: str, text: str) -> dict:
    provider = os.getenv("AI_PROVIDER", "openai")
    model = os.getenv("AI_MODEL", "gpt-4o")
    temp_str = os.getenv("AI_TEMPERATURE")
    try:
        temperature = float(temp_str) if temp_str is not None else 0.2
    except ValueError:
        temperature = 0.2

    client = get_ai_client(provider)
    prompt = f"""
Resuma o conteúdo a seguir em JSON válido.

TÍTULO: {title}
CONTEÚDO:
{text[:14000]}

Formato obrigatório:
{{
  "resumo": "resumo curto",
  "pontos_chave": ["ponto 1", "ponto 2", "ponto 3"]
}}
"""
    raw = call_ai(
        provider,
        model,
        prompt,
        client,
        temperature=temperature,
        call_context="attachments_enrich:summarize_text"
    )
    parsed = extract_json_block(raw)
    return {
        "resumo": parsed.get("resumo", ""),
        "pontos_chave": parsed.get("pontos_chave", []),
    }


def enrich_github_material(material: dict, use_ai: bool, force: bool) -> dict:
    url = material.get("url", "")
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2:
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = "URL de repositório GitHub inválida."
        return material

    owner, repo = segments[0], segments[1].replace(".git", "")
    repo_slug = clean_name(f"{owner}-{repo}")
    out_dir = ENRICHED_DIR / "github" / repo_slug
    repo_dir = out_dir / "repo"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        if repo_dir.exists() and force:
            shutil.rmtree(repo_dir)

        if not repo_dir.exists():
            clone_url = f"https://github.com/{owner}/{repo}.git"
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, str(repo_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

        zip_base = out_dir / repo_slug
        zip_file = Path(shutil.make_archive(str(zip_base), "zip", root_dir=repo_dir))
        readme_candidates = sorted(repo_dir.glob("README*"))
        readme_text = ""
        if readme_candidates:
            readme_text = readme_candidates[0].read_text(encoding="utf-8", errors="ignore")

        ai_data = {"resumo": "", "pontos_chave": []}
        if use_ai and readme_text.strip():
            ai_data = summarize_text_with_ai(material.get("titulo", repo_slug), readme_text)

        material["artefatos_locais"] = [to_relative(zip_file)]
        material["status"] = "enriquecido"
        material["enriquecimento"] = {
            "tipo": "github_repo",
            "repo": f"{owner}/{repo}",
            "resumo": ai_data.get("resumo", ""),
            "pontos_chave": ai_data.get("pontos_chave", []),
            "atualizado_em": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        logger.warning(f"Erro ao enriquecer material GitHub '{url}': {e}")
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = str(e)

    return material


def enrich_notion_material(material: dict, use_ai: bool) -> dict:
    url = material.get("url", "")
    slug = clean_name(material.get("titulo", "notion"))
    out_dir = ENRICHED_DIR / "notion"
    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_file = out_dir / f"{slug}.txt"

    if not STATE_PATH.exists():
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = "Sessão Playwright indisponível para capturar página Notion."
        return material

    page_text = ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
            try:
                context = browser.new_context(storage_state=str(STATE_PATH))
                page = context.new_page()
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                page_text = page.inner_text("body")
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"Erro ao capturar conteúdo Notion '{url}': {e}")
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = str(e)
        return material

    snapshot_file.write_text(page_text or "", encoding="utf-8")
    ai_data = {"resumo": "", "pontos_chave": []}
    if use_ai and page_text.strip():
        try:
            ai_data = summarize_text_with_ai(material.get("titulo", "Notion"), page_text)
        except Exception as e:
            logger.warning(f"Falha na síntese de Notion com IA para '{url}': {e}")

    material["artefatos_locais"] = [to_relative(snapshot_file)]
    material["status"] = "enriquecido"
    material["enriquecimento"] = {
        "tipo": "notion_page",
        "resumo": ai_data.get("resumo", ""),
        "pontos_chave": ai_data.get("pontos_chave", []),
        "atualizado_em": datetime.utcnow().isoformat() + "Z",
    }
    return material


def enrich_attachments_for_file(raw_json_path: Path, use_ai: bool = True, force: bool = False) -> bool:
    if not raw_json_path.exists():
        logger.error(f"Arquivo não encontrado para enriquecimento: {raw_json_path}")
        return False

    with open(raw_json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    materials = raw_data.get("materiais_apoio", [])
    if not materials:
        logger.info(f"Sem materiais de apoio para enriquecer em {raw_json_path.name}.")
        return True

    changed = False
    enriched_items = []
    for material in materials:
        material_type = material.get("tipo") or detect_material_type(material.get("url", ""))
        material["tipo"] = material_type

        if material_type == "github_repo":
            if force or material.get("status") != "enriquecido":
                material = enrich_github_material(material, use_ai=use_ai, force=force)
                changed = True
        elif material_type == "notion_page":
            if force or material.get("status") != "enriquecido":
                material = enrich_notion_material(material, use_ai=use_ai)
                changed = True

        enriched_items.append(material)

    if changed:
        raw_data["materiais_apoio"] = enriched_items
        with open(raw_json_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Materiais enriquecidos e salvos em {raw_json_path}")
    else:
        logger.info(f"Nenhuma atualização de enriquecimento necessária para {raw_json_path.name}.")

    return True


def enrich_attachments_for_all(use_ai: bool = True, force: bool = False, limit: int = None):
    raw_files = [f for f in RAW_DATA_DIR.glob("**/*.json") if f.name != "course_index.json"]
    if limit:
        raw_files = raw_files[:limit]

    success_count = 0
    for raw_file in raw_files:
        if enrich_attachments_for_file(raw_file, use_ai=use_ai, force=force):
            success_count += 1

    return success_count, len(raw_files)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Enriquece materiais de apoio (Notion/GitHub) das aulas extraídas.")
    parser.add_argument("--file", type=str, help="Arquivo JSON bruto da aula para enriquecer.")
    parser.add_argument("--all", action="store_true", help="Enriquecer todas as aulas do cache bruto.")
    parser.add_argument("--no-ai", action="store_true", help="Executa enriquecimento sem sumarização por IA.")
    parser.add_argument("--force", action="store_true", help="Força reprocessamento dos materiais já enriquecidos.")
    parser.add_argument("--limit", type=int, help="Limite de arquivos para processar com --all.")
    args = parser.parse_args()

    use_ai = not args.no_ai
    if args.file:
        ok = enrich_attachments_for_file(Path(args.file), use_ai=use_ai, force=args.force)
        sys.exit(0 if ok else 1)
    elif args.all:
        success, total = enrich_attachments_for_all(use_ai=use_ai, force=args.force, limit=args.limit)
        logger.info(f"Enriquecimento concluído: {success} de {total} arquivos.")
        sys.exit(0 if success == total else 1)
    else:
        parser.print_help()
