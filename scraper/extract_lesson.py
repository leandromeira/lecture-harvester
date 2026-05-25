import os
import sys
import json
import argparse
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_extraction_logger

logger = setup_extraction_logger()

# Configurações carregadas via variáveis de ambiente (.env)

STATE_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_state.json"
RAW_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Seletores para os elementos da aula no Full Cycle
SELECTORS = {
    "lesson_title": "h1, .MuiBreadcrumbs-ol li:last-child",
    "transcript_item": "#panel-1 div > span:last-child",
    "summary_item": ".MuiTypography-h5 p, .MuiTypography-h5 h2"
}

ATTACHMENT_EXTENSIONS = {
    ".pdf", ".ppt", ".pptx", ".zip", ".rar", ".7z",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
    ".md", ".py", ".ipynb"
}
ATTACHMENT_KEYWORDS = (
    "material", "apoio", "slides", "slide", "download",
    "anexo", "arquivo", "github", "repositorio", "repositório"
)

def clean_filename(name):
    """Limpador de nome de pasta/arquivo para evitar problemas no OS."""
    import re
    return re.sub(r'[^a-zA-Z0-9\s_-]', '', name).strip()

def should_download_material(title, url):
    """Heurística para identificar links candidatos a material de apoio."""
    parsed = urlparse(url or "")
    if not parsed.scheme.startswith("http"):
        return False

    path_lower = parsed.path.lower()
    title_lower = (title or "").lower()
    query_lower = (parsed.query or "").lower()
    netloc_lower = (parsed.netloc or "").lower()

    if any(path_lower.endswith(ext) for ext in ATTACHMENT_EXTENSIONS):
        return True
    if "download" in query_lower:
        return True
    if any(keyword in title_lower for keyword in ATTACHMENT_KEYWORDS):
        return True
    if any(host in netloc_lower for host in ("github.com", "drive.google.com", "dropbox.com", "notion.so", "notion.site")):
        return True
    return False

def detect_material_type(title, url):
    """Classifica o tipo do material para enriquecimento posterior."""
    parsed = urlparse(url or "")
    netloc_lower = parsed.netloc.lower()
    path_lower = parsed.path.lower()
    query_lower = parsed.query.lower()

    if "github.com" in netloc_lower:
        segments = [seg for seg in parsed.path.split("/") if seg]
        if len(segments) >= 2:
            return "github_repo"

    if "notion.so" in netloc_lower or "notion.site" in netloc_lower:
        return "notion_page"

    if any(path_lower.endswith(ext) for ext in ATTACHMENT_EXTENSIONS):
        return "direct_file"

    if "download" in query_lower and "github.com" not in netloc_lower and "notion" not in netloc_lower:
        return "direct_file"

    if "drive.google.com" in netloc_lower and "/uc" in path_lower and "export=download" in query_lower:
        return "direct_file"

    return "external_link"

def collect_support_materials(page):
    """Coleta links candidatos a materiais de apoio na página da aula."""
    links = page.evaluate("""() => {
        const anchors = Array.from(document.querySelectorAll('a[href]'));
        return anchors.map((a) => ({
            title: (a.innerText || a.textContent || '').trim(),
            url: a.href
        }));
    }""")

    materials = []
    seen_urls = set()
    for link in links:
        title = (link.get("title") or "").strip()
        url = (link.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        if should_download_material(title, url):
            material_type = detect_material_type(title, url)
            materials.append({
                "titulo": title or "Material de Apoio",
                "url": url,
                "tipo": material_type,
                "baixado": False,
                "arquivo_local": None,
                "status": "pendente_enriquecimento" if material_type in ("github_repo", "notion_page") else "capturado"
            })
            seen_urls.add(url)
    return materials

def download_support_materials(page, materials, attachments_dir):
    """Baixa materiais de apoio e retorna metadados enriquecidos para o JSON da aula."""
    downloaded = []
    attachments_dir.mkdir(parents=True, exist_ok=True)

    for index, material in enumerate(materials, start=1):
        entry = dict(material)
        title = entry.get("titulo", f"material-{index}")
        url = entry.get("url", "")
        material_type = entry.get("tipo", "external_link")

        if material_type != "direct_file":
            downloaded.append(entry)
            continue

        filename = clean_filename(Path(urlparse(url).path).name)
        if not filename:
            filename = f"material-{index}.bin"
        elif "." not in filename:
            filename = f"{filename}.bin"

        target_path = attachments_dir / filename
        stem = target_path.stem
        suffix = target_path.suffix
        dedupe = 2
        while target_path.exists():
            target_path = attachments_dir / f"{stem}-{dedupe}{suffix}"
            dedupe += 1

        try:
            response = page.request.get(url, timeout=30000)
            if response.ok:
                target_path.write_bytes(response.body())
                try:
                    relative = target_path.relative_to(PROJECT_ROOT).as_posix()
                except ValueError:
                    relative = str(target_path)
                entry["baixado"] = True
                entry["arquivo_local"] = relative
                entry["status"] = "baixado"
            else:
                logger.warning(f"Falha ao baixar material '{title}' ({url}). Status: {response.status}")
        except Exception as e:
            logger.warning(f"Erro ao baixar material '{title}' ({url}): {e}")

        downloaded.append(entry)

    return downloaded

def get_mock_data(curso, modulo, aula, url):
    """Gera dados simulados (mock) para testes da pipeline."""
    return {
        "curso": curso or os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA"),
        "modulo": modulo or "Módulo 01 - Introdução ao Harvester",
        "aula": aula or "Aula 01 - Primeiros Passos com o Pipeline",
        "url": url or "https://plataforma.exemplo.com/aulas/harvester-101",
        "resumo_original": "Este é um resumo original pré-existente na plataforma de ensino. Explica os conceitos básicos de como configurar seu ambiente python, instalar o playwright e rodar a extração inicial.",
        "transcricao": "Olá a todos e bem-vindos a esta aula de Introdução ao Pipeline. Hoje vamos falar sobre a filosofia do projeto. O nosso sistema não deve ser um agente autônomo. Queremos scripts previsíveis e um pipeline determinístico. Vamos usar caches locais. Por exemplo, salvamos a transcrição e o resumo em arquivos JSON brutos dentro da pasta data/raw. Depois, processamos isso separadamente usando a API da OpenAI. Isso desacopla a extração do processamento de IA. É excelente para economizar tokens, pois se quisermos alterar o prompt ou o modelo de IA, não precisamos fazer a raspagem de dados novamente. Também é importante configurar o storage_state no Playwright para evitar logins manuais repetidos. Colocamos o usuário e a senha no arquivo .env e deixamos o script se logar automaticamente se expirar. Na próxima aula falaremos sobre a Engenharia de Prompt e o tamanho das janelas de contexto (Context Window). Até lá!",
        "materiais_apoio": [
            {
                "titulo": "Repositório Exemplo",
                "url": "https://github.com/example/repo",
                "tipo": "github_repo",
                "baixado": False,
                "arquivo_local": None,
                "status": "pendente_enriquecimento"
            },
            {
                "titulo": "Slides",
                "url": "https://example.com/slides.pdf",
                "tipo": "direct_file",
                "baixado": False,
                "arquivo_local": None,
                "status": "capturado"
            }
        ]
    }

def extract_lesson(url, modulo_nome, aula_titulo, slug, mock=False, curso_nome=None):
    """
    Navega para a URL da aula, extrai as informações brutas
    e salva o arquivo JSON correspondente na pasta data/raw/.
    """
    curso = curso_nome or os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    mod_clean = clean_filename(modulo_nome or "Modulo Desconhecido")
    slug_clean = clean_filename(slug or "aula_desconhecida")
    
    output_dir = RAW_DATA_DIR / mod_clean
    output_path = output_dir / f"{slug_clean}.json"
    attachments_dir = output_dir / "attachments" / slug_clean

    if mock:
        logger.info(f"[MOCK] Gerando dados fictícios para {aula_titulo}...")
        data = get_mock_data(curso, modulo_nome, aula_titulo, url)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"[MOCK] JSON gerado com sucesso em {output_path}")
        return data

    if not STATE_PATH.exists():
        logger.error("Sessão expirada ou arquivo de storage_state não encontrado. Faça o login primeiro.")
        return None

    logger.info(f"Extraindo aula: {aula_titulo} ({url})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        try:
            # Usar domcontentloaded e aguardar de forma inteligente o carregamento dos componentes React
            page.goto(url, timeout=int(os.getenv("PLAYWRIGHT_TIMEOUT", 30000)), wait_until="domcontentloaded")
            try:
                page.wait_for_selector('button[role="tab"]', timeout=10000)
                # Esperar o container de resumo aparecer na tela (se existir)
                page.wait_for_selector('.MuiTypography-h5', timeout=5000)
            except Exception:
                # Fallback de tempo de segurança caso a rede esteja lenta ou a página não tenha resumo
                page.wait_for_timeout(2000)

            # Priorizar o título recebido do índice (aula_titulo), caindo de volta para a extração do DOM
            extracted_title = (aula_titulo or "").strip()
            if not extracted_title:
                title_el = page.query_selector(SELECTORS["lesson_title"])
                extracted_title = title_el.inner_text().strip() if title_el else "Sem título"

            # 1. Extrair resumo da aula
            resumo_elms = page.query_selector_all(SELECTORS["summary_item"])
            resumo_texts = []
            for el in resumo_elms:
                txt = el.inner_text().strip()
                if txt and txt not in resumo_texts:
                    resumo_texts.append(txt)

            # Fallback robusto caso não encontre elementos p ou h2 específicos (.MuiTypography-h5)
            if not resumo_texts:
                fallback_elms = page.query_selector_all(".MuiTypography-h5")
                for el in fallback_elms:
                    txt = el.inner_text().strip()
                    if txt and txt not in resumo_texts:
                        resumo_texts.append(txt)

            resumo_original = "\n\n".join(resumo_texts)

            # 2. Clicar no botão da aba de transcrição
            clicked = False
            try:
                # Localizar botão com o texto Transcrição
                trans_btn = page.locator('button', has_text="Transcrição")
                # Esperar estar visível (timeout de 5s)
                trans_btn.wait_for(state="visible", timeout=5000)
                # Clica e aguarda actionability (se estiver disabled, o Playwright esperará até que seja habilitado)
                trans_btn.click(timeout=5000)
                clicked = True
            except Exception as e:
                logger.debug(f"Não foi possível clicar no botão de Transcrição usando locator: {e}")
                # Fallback secundário usando evaluate para compatibilidade
                clicked = page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const transBtn = buttons.find(b => b.innerText.includes("Transcrição"));
                    if (transBtn && !transBtn.disabled) {
                        transBtn.click();
                        return true;
                    }
                    return false;
                }""")

            transcricao = ""
            if clicked:
                # Aguarda renderização da transcrição (timeout de 3s)
                page.wait_for_timeout(3000)
                # Extrair o conteúdo da transcrição
                trans_elms = page.query_selector_all(SELECTORS["transcript_item"])
                trans_texts = [el.inner_text().strip() for el in trans_elms]
                transcricao = " ".join([t for t in trans_texts if t])
            else:
                logger.warning(f"Aba de transcrição não disponível ou não pôde ser clicada para a aula {url}.")

            # 3. Materiais de apoio (downloads e links)
            materials = collect_support_materials(page)
            support_materials = download_support_materials(page, materials, attachments_dir) if materials else []

            data = {
                "curso": curso,
                "modulo": modulo_nome or "Geral",
                "aula": extracted_title,
                "url": url,
                "transcricao": transcricao,
                "resumo_original": resumo_original,
                "materiais_apoio": support_materials
            }

            # Salva o JSON bruto
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Aula extraída com sucesso e salva em {output_path}")
            return data

        except Exception as e:
            logger.exception(f"Erro ao extrair dados da aula {url}: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai dados de uma aula específica.")
    parser.add_argument("--url", type=str, help="URL da aula.")
    parser.add_argument("--modulo", type=str, help="Nome do módulo.")
    parser.add_argument("--aula", type=str, help="Título da aula.")
    parser.add_argument("--slug", type=str, help="Slug para o nome do arquivo.")
    parser.add_argument("--mock", action="store_true", help="Gera dados mockados de simulação.")
    args = parser.parse_args()

    if not args.mock and not args.url:
        parser.error("A URL é obrigatória caso o modo --mock não esteja ativo.")

    extract_lesson(args.url, args.modulo, args.aula, args.slug, mock=args.mock)
