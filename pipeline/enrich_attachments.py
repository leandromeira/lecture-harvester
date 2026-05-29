import os
import sys
import json
import shutil
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs

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
    if "drive.google.com" in host:
        return "google_drive"
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
            clone_url_https = f"https://github.com/{owner}/{repo}.git"
            logger.info(f"Tentando clonar via HTTPS: {clone_url_https}")
            subprocess.run(
                ["git", "clone", "--depth", "1", clone_url_https, str(repo_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

        zip_base = out_dir / repo_slug
        zip_file = Path(shutil.make_archive(str(zip_base), "zip", root_dir=repo_dir))
        
        # Desativado resumo de IA para materiais conforme solicitado
        ai_data = {"resumo": "", "pontos_chave": []}

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
                
                # Aguarda renderização completa do Notion
                page.wait_for_timeout(6000)
                
                # Extrair título e conteúdo limpos do Notion
                extracted = page.evaluate("""() => {
                    const titleEl = document.querySelector('.notion-page-block h1, h1.notion-page-title, .notion-title-block, .notion-page-controls + div');
                    let title = titleEl ? titleEl.innerText.trim() : '';
                    if (!title) {
                        title = document.title || 'Sem Título';
                    }
                    
                    const contentEl = document.querySelector('.notion-page-content');
                    const content = contentEl ? contentEl.innerText.trim() : '';
                    
                    return { title, content };
                }""")
                
                title = extracted.get("title", "Sem Título")
                page_text = f"Título: {title}\n\nConteúdo:\n{extracted.get('content', '')}"
            finally:
                browser.close()
    except Exception as e:
        logger.warning(f"Erro ao capturar conteúdo Notion '{url}': {e}")
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = str(e)
        return material

    snapshot_file.write_text(page_text or "", encoding="utf-8")
    
    # Desativado resumo de IA para Notion conforme solicitado
    ai_data = {"resumo": "", "pontos_chave": []}

    material["artefatos_locais"] = [to_relative(snapshot_file)]
    material["status"] = "enriquecido"
    material["enriquecimento"] = {
        "tipo": "notion_page",
        "resumo": ai_data.get("resumo", ""),
        "pontos_chave": ai_data.get("pontos_chave", []),
        "atualizado_em": datetime.utcnow().isoformat() + "Z",
    }
    return material


def download_google_drive_material(material: dict, attachments_dir: Path) -> dict:
    url = material.get("url", "")
    title = material.get("titulo", "Google Drive File")
    
    file_id = None
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
    else:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        if 'id' in q:
            file_id = q['id'][0]
            
    if not file_id:
        logger.warning(f"Não foi possível extrair ID do link Google Drive: {url}")
        material["status"] = "erro_download"
        return material
        
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    logger.info(f"Baixando arquivo do Google Drive: {title} ({download_url})")
    
    attachments_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        import urllib.request
        req = urllib.request.Request(
            download_url,
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            content_type = response.info().get('Content-Type', '')
            content_disposition = response.info().get('Content-Disposition', '')
            
            # Se vier HTML, quer dizer que falhou ou requer confirmação de tamanho
            if "text/html" in content_type.lower():
                body_bytes = response.read(10000)
                body_str = body_bytes.decode('utf-8', errors='ignore')
                confirm_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', body_str)
                
                if confirm_match:
                    confirm_code = confirm_match.group(1)
                    confirm_url = f"{download_url}&confirm={confirm_code}"
                    logger.info(f"Confirmando download de arquivo grande do Drive: {confirm_url}")
                    req_confirm = urllib.request.Request(
                        confirm_url,
                        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    )
                    with urllib.request.urlopen(req_confirm, timeout=30) as resp_conf:
                        response_data = resp_conf.read()
                        headers = resp_conf.info()
                        content_disposition = headers.get('Content-Disposition', '')
                else:
                    logger.warning(f"Link do Google Drive não é público ou requer login: {url}")
                    material["status"] = "link_privado"
                    return material
            else:
                response_data = response.read()
                
            # Extrair nome do arquivo do Content-Disposition se houver
            filename = None
            if content_disposition:
                fn_match = re.search(r'filename="([^"]+)"', content_disposition)
                if fn_match:
                    filename = fn_match.group(1)
                    
            if not filename:
                filename = clean_name(title)
                if not "." in filename:
                    filename = f"{filename}.pdf"
                    
            # Sanitizar nome de arquivo
            filename = re.sub(r'[\\/*?:"<>|]', '', filename).strip()
            target_path = attachments_dir / filename
            target_path.write_bytes(response_data)
            
            material["baixado"] = True
            material["arquivo_local"] = to_relative(target_path)
            material["status"] = "baixado"
            logger.info(f"Sucesso ao baixar arquivo do Google Drive e salvar em {target_path}")
            
    except Exception as e:
        logger.warning(f"Erro ao baixar arquivo do Google Drive '{url}': {e}")
        material["status"] = "erro_download"
        material["erro_download"] = str(e)
        
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
        material_type = detect_material_type(material.get("url", ""))
        material["tipo"] = material_type

        if material_type == "github_repo":
            if force or material.get("status") != "enriquecido":
                material = enrich_github_material(material, use_ai=use_ai, force=force)
                changed = True
        elif material_type == "notion_page":
            if force or material.get("status") != "enriquecido":
                material = enrich_notion_material(material, use_ai=use_ai)
                changed = True
        elif material_type == "google_drive":
            if force or material.get("status") != "baixado":
                material = download_google_drive_material(material, raw_json_path.parent / "attachments" / raw_json_path.stem)
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
