import os
import sys
import json
import argparse
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_extraction_logger
from scraper.extract_lesson import clean_filename

logger = setup_extraction_logger()

STATE_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_state.json"
INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "course_index.json"
EXPLORATION_DIR = Path(__file__).resolve().parents[1] / "data" / "exploration"
SCREENSHOTS_DIR = EXPLORATION_DIR / "screenshots"

def select_samples(limit_per_module=2):
    """Seleciona uma amostra de aulas para explorar."""
    if not INDEX_PATH.exists():
        logger.error(f"Índice do curso não encontrado em {INDEX_PATH}. Execute a sincronização primeiro.")
        return []

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        course_data = json.load(f)

    samples = []
    for modulo in course_data.get("modulos", []):
        mod_name = modulo.get("modulo", "Sem Nome")
        lessons = modulo.get("aulas", [])
        logger.info(f"Módulo '{mod_name}' possui {len(lessons)} aulas. Selecionando amostra...")
        
        # Pega as primeiras e algumas do meio/fim para variar os tipos se possível
        selected = lessons[:limit_per_module]
        for idx, lesson in enumerate(selected):
            samples.append({
                "modulo": mod_name,
                "titulo": lesson.get("titulo"),
                "url": lesson.get("url"),
                "slug": lesson.get("slug") or f"aula-{idx}"
            })
            
    logger.info(f"Selecionadas {len(samples)} aulas para exploração.")
    return samples

def analyze_page(page):
    """Analisa elementos do DOM e classifica o tipo de página/aula."""
    # Espera inteligente pelo carregamento de elementos cruciais (vídeo, iframe ou resumo)
    try:
        # Tenta esperar que o player de vídeo ou o resumo da aula apareça na tela
        page.wait_for_selector('video, iframe[src*="mediadelivery"], iframe[src*="vimeo"], iframe[src*="youtube"], iframe[src*="panda"], .MuiTypography-h5', timeout=10000)
    except Exception:
        # Fallback de segurança caso a rede esteja lenta
        page.wait_for_timeout(3000)
    
    # Pequeno delay de estabilização final
    page.wait_for_timeout(1500)
    
    # 1. Verifica se há player de vídeo
    has_video = (
        page.locator("video").count() > 0 
        or page.locator("iframe[src*='vimeo']").count() > 0 
        or page.locator("iframe[src*='youtube']").count() > 0
        or page.locator("iframe[src*='mediadelivery.net']").count() > 0
        or page.locator("iframe[src*='panda.video']").count() > 0
    )
    
    # 2. Verifica se há aba de Transcrição
    has_transcript_tab = page.locator('button', has_text="Transcrição").count() > 0
    
    # 3. Verifica se há resumo (.MuiTypography-h5)
    has_summary = page.locator(".MuiTypography-h5").count() > 0
    
    # 4. Coleta todos os links externos da página, excluindo rodapé e sidebar lateral
    links = page.evaluate("""() => {
        const anchors = Array.from(document.querySelectorAll('a[href]'));
        return anchors.filter(a => {
            const href = a.href;
            if (!href.startsWith('http') || href.includes('plataforma.fullcycle')) return false;
            
            // Filtrar links institucionais do rodapé
            if (href.includes('fullcycle.com.br/validar-certificado') || 
                href.includes('fullcycle.com.br/politica') || 
                href.includes('fullcycle.com.br/termos') || 
                href.includes('faq')) {
                return false;
            }
            
            // Filtrar links que estão dentro da sidebar (menu lateral/acordeão)
            let isSidebar = false;
            let parent = a.parentElement;
            while (parent) {
                if (parent.classList && (
                    parent.classList.contains('MuiCollapse-root') || 
                    parent.classList.contains('MuiAccordion-root') ||
                    parent.classList.contains('MuiListItem-root')
                )) {
                    isSidebar = true;
                    break;
                }
                parent = parent.parentElement;
            }
            return !isSidebar;
        }).map(a => {
            let txt = (a.innerText || a.textContent || '').trim();
            // Remove sufixos de tempo (ex: "Slides120:00" -> "Slides", "Docker25:00" -> "Docker")
            txt = txt.replace(/\\s*\\d{2}:\\d{2}$/, '').trim();
            return {
                text: txt || 'Link Externo',
                href: a.href
            };
        });
    }""")
    
    # 5. Verifica se há botões com links externos ou textos específicos
    page_text = page.inner_text("body") or ""
    
    # Classificação
    if has_video:
        detected_type = "video_lecture"
    elif "questionário" in page_text.lower() or "quiz" in page_text.lower() or page.locator("input[type='radio']").count() > 0:
        detected_type = "quiz"
    elif len(links) > 0:
        # É uma aula de material/links
        github_links = [l for l in links if "github.com" in l["href"]]
        notion_links = [l for l in links if "notion.so" in l["href"] or "notion.site" in l["href"]]
        
        if github_links:
            detected_type = "github_link_lecture"
        elif notion_links:
            detected_type = "notion_link_lecture"
        else:
            detected_type = "external_link_lecture"
    else:
        detected_type = "text_lecture"
        
    return {
        "url_final": page.url,
        "tipo_detectado": detected_type,
        "has_video": has_video,
        "has_transcript_tab": has_transcript_tab,
        "has_summary": has_summary,
        "links_externos": links,
        "resumo_dom": page_text[:500] + "..." if len(page_text) > 500 else page_text
    }

def explore_course(limit_per_module=2):
    """Navega por uma amostra de aulas e gera um relatório sobre os templates de layout."""
    if not STATE_PATH.exists():
        logger.error("storage_state.json não encontrado. Faça o login primeiro.")
        return False

    samples = select_samples(limit_per_module)
    if not samples:
        return False

    EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    report = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))

        for idx, sample in enumerate(samples, start=1):
            url = sample["url"]
            titulo = sample["titulo"]
            modulo = sample["modulo"]
            slug = sample["slug"]
            
            logger.info(f"[{idx}/{len(samples)}] Explorando: '{titulo}' ({modulo})")
            
            page = context.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                
                # Análise do DOM
                analysis = analyze_page(page)
                
                # Salva screenshot para validação visual
                screenshot_filename = f"{clean_filename(modulo)}-{clean_filename(titulo)}.png"
                screenshot_path = SCREENSHOTS_DIR / screenshot_filename
                page.screenshot(path=str(screenshot_path))
                
                entry = {
                    "modulo": modulo,
                    "titulo": titulo,
                    "url": url,
                    "slug": slug,
                    "analise": analysis,
                    "screenshot": str(screenshot_path.relative_to(EXPLORATION_DIR.parent))
                }
                report.append(entry)
                
                logger.info(f"  -> Tipo detectado: {analysis['tipo_detectado']} | Screenshot salvo em: {screenshot_filename}")
                
            except Exception as e:
                logger.error(f"  -> Erro ao explorar '{titulo}': {e}")
                report.append({
                    "modulo": modulo,
                    "titulo": titulo,
                    "url": url,
                    "slug": slug,
                    "erro": str(e)
                })
            finally:
                page.close()
                
        browser.close()

    report_path = EXPLORATION_DIR / "exploration_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Relatório de exploração salvo com sucesso em: {report_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explora o layout de amostras de aulas na plataforma.")
    parser.add_argument("--limit-per-module", type=int, default=2, help="Limite de aulas para extrair de amostra por módulo.")
    args = parser.parse_args()

    explore_course(limit_per_module=args.limit_per_module)
