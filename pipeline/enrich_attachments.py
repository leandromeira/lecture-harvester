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
from pipeline.ai_summarizer import get_ai_client, call_ai, extract_json_block

logger = setup_processing_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched" / "materials"
STATE_PATH = PROJECT_ROOT / "config" / "storage_state.json"


def clean_name(value: str) -> str:
    import re
    import unicodedata
    value = value or "material"
    # Normalizar caracteres acentuados para suas formas base em ASCII
    value = unicodedata.normalize('NFKD', value).encode('ASCII', 'ignore').decode('ASCII')
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", value).strip("-")
    # Remover múltiplos hifens consecutivos
    cleaned = re.sub(r"-+", "-", cleaned)
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
    main_title = material.get("titulo", "notion")
    main_slug = clean_name(main_title)
    
    # Pasta isolada para o material do Notion e suas subpáginas
    material_dir = ENRICHED_DIR / "notion" / main_slug
    material_dir.mkdir(parents=True, exist_ok=True)
    
    if not STATE_PATH.exists():
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = "Sessão Playwright indisponível para capturar página Notion."
        return material

    # Extrair ID da URL
    def extract_notion_id(u: str) -> str:
        parsed = urlparse(u)
        path = parsed.path
        match = re.search(r'([a-fA-F0-9]{32})$', path.replace('-', ''))
        if match:
            return match.group(1).lower()
        return re.sub(r'[^a-zA-Z0-9]', '', path).lower()

    # Rastrear URLs crawled para evitar loops e mapear URLs de Notion para nomes de arquivos locais
    crawled_urls = {} # map: page_id -> local_slug
    local_artifacts = []
    
    # Fila de URLs para processar: list of (url, depth, is_main)
    queue = [(url, 1, True)]
    visited_ids = set()
    
    # Lista de páginas com conteúdo convertido e seus links internos para processamento posterior
    pages_to_write = [] # list of dict: {"id": page_id, "slug": local_slug, "title": title, "markdown_raw": markdown, "links": [...], "is_main": is_main}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
            context = browser.new_context(storage_state=str(STATE_PATH))
            
            while queue:
                current_url, depth, is_main = queue.pop(0)
                page_id = extract_notion_id(current_url)
                if page_id in visited_ids:
                    continue
                visited_ids.add(page_id)
                
                # Se for maior que profundidade 2, não crawlamos mais subpáginas
                if depth > 2:
                    continue
                    
                logger.info(f"Crawling Notion [{depth}]: {current_url}")
                sub_page = context.new_page()
                try:
                    sub_page.goto(current_url, timeout=20000, wait_until="commit")
                    sub_page.wait_for_timeout(6000)
                    
                    # Extrair título, Markdown parcial e links internos
                    extracted = sub_page.evaluate("""() => {
                        const contentEl = document.querySelector('.notion-page-content') || document.querySelector('.notion-selectable')?.parentElement;
                        if (!contentEl) return null;

                        const titleEl = document.querySelector('.notion-page-block h1, h1.notion-page-title, .notion-title-block, .notion-page-controls + div');
                        const title = titleEl ? titleEl.innerText.trim() : document.title || 'Sem Título';

                        // Coletar links internos do Notion
                        const internalLinks = [];
                        const anchors = Array.from(contentEl.querySelectorAll('a[href]'));
                        anchors.forEach(a => {
                            const href = a.href;
                            if (href && (href.includes('notion.so') || href.includes('notion.site')) && !href.includes('image')) {
                                internalLinks.push({
                                    text: a.innerText.trim(),
                                    href: href
                                });
                            }
                        });

                        function convertNodeToMarkdown(node) {
                            if (node.nodeType === Node.TEXT_NODE) {
                                return node.textContent;
                            }
                            if (node.nodeType !== Node.ELEMENT_NODE) {
                                return '';
                            }

                            const tagName = node.tagName.toLowerCase();
                            const classes = Array.from(node.classList);

                            // Se for link
                            if (tagName === 'a' && node.getAttribute('href')) {
                                const href = node.href;
                                const text = node.innerText.trim() || 'Link';
                                if (href.includes('notion.so') || href.includes('notion.site')) {
                                    return `[NOTION_LINK:${href}][${text}]`;
                                }
                                return `[${text}](${href})`;
                            }

                            // Formatações básicas
                            if (tagName === 'strong' || tagName === 'b' || node.style.fontWeight === 'bold') {
                                return `**${Array.from(node.childNodes).map(convertNodeToMarkdown).join('')}**`;
                            }
                            if (tagName === 'em' || tagName === 'i' || node.style.fontStyle === 'italic') {
                                return `*${Array.from(node.childNodes).map(convertNodeToMarkdown).join('')}*`;
                            }
                            if (tagName === 'code') {
                                return `\`${node.innerText}\``;
                            }

                            // Blocos estruturais do Notion
                            if (classes.includes('notion-bulleted_list-block')) {
                                return `* ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\n`;
                            }
                            if (classes.includes('notion-numbered_list-block')) {
                                return `1. ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\n`;
                            }
                            if (classes.includes('notion-to_do-block')) {
                                const checked = node.querySelector('input[type="checkbox"]') ? node.querySelector('input[type="checkbox"]').checked : false;
                                return `- [${checked ? 'x' : ' '}] ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\n`;
                            }
                            if (classes.includes('notion-code-block')) {
                                const codeEl = node.querySelector('code');
                                const codeText = codeEl ? codeEl.innerText : node.innerText;
                                return `\`\`\`\\n${codeText.trim()}\\n\`\`\`\\n\\n`;
                            }
                            if (classes.includes('notion-quote-block')) {
                                return `> ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\n\n`;
                            }
                            if (classes.includes('notion-callout-block')) {
                                return `> [!NOTE]\\n> ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim().replace(/\\n/g, '\\n> ')}\n\n`;
                            }
                            if (classes.includes('notion-divider-block')) {
                                return `---\n\n`;
                            }
                            if (classes.includes('notion-header-block')) {
                                return `\\n# ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\\n\\n`;
                            }
                            if (classes.includes('notion-sub_header-block')) {
                                return `\\n## ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\\n\\n`;
                            }
                            if (classes.includes('notion-sub_sub_header-block')) {
                                return `\\n### ${Array.from(node.childNodes).map(convertNodeToMarkdown).join('').trim()}\\n\\n`;
                            }
                            if (classes.includes('notion-page-block')) {
                                const a = node.querySelector('a[href]');
                                if (a) {
                                    const href = a.href;
                                    const text = a.innerText.trim() || node.innerText.trim();
                                    return `\\n* **Página:** [NOTION_LINK:${href}][${text}]\\n`;
                                }
                                return `\\n* **Página:** ${node.innerText.trim()}\\n`;
                            }

                            if (tagName === 'div' && classes.some(c => c.startsWith('notion-'))) {
                                return Array.from(node.childNodes).map(convertNodeToMarkdown).join('') + '\\n';
                            }

                            return Array.from(node.childNodes).map(convertNodeToMarkdown).join('');
                        }

                        const blocks = Array.from(contentEl.children);
                        let markdown = blocks.map(convertNodeToMarkdown).join('\\n');
                        markdown = markdown.replace(/\\n{3,}/g, '\\n\\n');

                        return { title, markdown, links: internalLinks };
                    }""")
                    
                    if not extracted:
                        logger.warning(f"Não foi possível obter conteúdo para a página Notion: {current_url}")
                        continue
                        
                    title = extracted.get("title", "Sem Título")
                    markdown = extracted.get("markdown", "")
                    links = extracted.get("links", [])
                    
                    # Definir slug local
                    if is_main:
                        local_slug = main_slug
                    else:
                        local_slug = clean_name(title)
                        # Evitar conflitos de nomes duplicados
                        base_slug = local_slug
                        counter = 2
                        while any(p["slug"] == local_slug for p in pages_to_write):
                            local_slug = f"{base_slug}-{counter}"
                            counter += 1
                            
                    crawled_urls[page_id] = local_slug
                    pages_to_write.append({
                        "id": page_id,
                        "slug": local_slug,
                        "title": title,
                        "markdown_raw": markdown,
                        "links": links,
                        "is_main": is_main
                    })
                    
                    # Adicionar novos links descobertos à fila (se profundidade permitir)
                    if depth < 2:
                        for l in links:
                            link_url = l["href"]
                            link_id = extract_notion_id(link_url)
                            if link_id not in visited_ids:
                                queue.append((link_url, depth + 1, False))
                                
                except Exception as page_err:
                    logger.warning(f"Erro ao processar página Notion {current_url}: {page_err}")
                finally:
                    sub_page.close()
                    
            browser.close()
            
    except Exception as e:
        logger.warning(f"Erro na execução geral do Playwright para o Notion '{url}': {e}")
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = str(e)
        return material

    if not pages_to_write:
        material["status"] = "erro_enriquecimento"
        material["erro_enriquecimento"] = "Nenhuma página Notion foi capturada com sucesso."
        return material

    # Segunda passada em Python: resolver e reescrever links internos
    for page_data in pages_to_write:
        md = page_data["markdown_raw"]
        
        # Encontrar todas as marcações [NOTION_LINK:url][texto]
        # e substituir por [[local_slug|texto]] se a URL estiver no crawled_urls
        def replace_notion_link(match):
            link_url = match.group(1)
            link_text = match.group(2)
            link_id = extract_notion_id(link_url)
            
            if link_id in crawled_urls:
                slug_dest = crawled_urls[link_id]
                return f"[[{slug_dest}|{link_text}]]"
            else:
                # Se não foi crawled (por limite de profundidade, etc.), manter como link externo normal
                return f"[{link_text}]({link_url})"
                
        md_resolved = re.sub(r'\[NOTION_LINK:([^\]]+)\]\[([^\]]+)\]', replace_notion_link, md)
        
        # Formatar cabeçalho
        title = page_data["title"]
        final_md = f"# {title}\n\n{md_resolved}"
        
        # Salvar nota localmente
        out_file = material_dir / f"{page_data['slug']}.md"
        out_file.write_text(final_md, encoding="utf-8")
        
        # Adicionar à lista de artefatos
        relative_path = to_relative(out_file)
        local_artifacts.append(relative_path)
        
        # Se for a página principal, salvar a referência em material
        if page_data["is_main"]:
            material["arquivo_local"] = relative_path

    # Atualizar metadados do material
    material["artefatos_locais"] = local_artifacts
    material["status"] = "enriquecido"
    material["baixado"] = True
    
    ai_data = {"resumo": "", "pontos_chave": []}
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


def enrich_attachments_for_file(raw_json_path: Path, use_ai: bool = False, force: bool = False) -> bool:
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


def enrich_attachments_for_all(use_ai: bool = False, force: bool = False, limit: int = None):
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
    parser.add_argument("--use-ai", action="store_true", help="Executa enriquecimento com sumarização por IA.")
    parser.add_argument("--force", action="store_true", help="Força reprocessamento dos materiais já enriquecidos.")
    parser.add_argument("--limit", type=int, help="Limite de arquivos para processar com --all.")
    args = parser.parse_args()

    use_ai = args.use_ai
    if args.file:
        ok = enrich_attachments_for_file(Path(args.file), use_ai=use_ai, force=args.force)
        sys.exit(0 if ok else 1)
    elif args.all:
        success, total = enrich_attachments_for_all(use_ai=use_ai, force=args.force, limit=args.limit)
        logger.info(f"Enriquecimento concluído: {success} de {total} arquivos.")
        sys.exit(0 if success == total else 1)
    else:
        parser.print_help()
