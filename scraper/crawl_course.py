import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_extraction_logger

logger = setup_extraction_logger()

# Configurações carregadas via variáveis de ambiente (.env)

STATE_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_state.json"
INDEX_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "course_index.json"

def clean_slug(text):
    """Gera um slug amigável a partir do título."""
    text = text.lower()
    text = re.sub(r'[áàâãä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôõö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text.strip('-')

def load_existing_index():
    """Carrega o índice atual se ele já existir."""
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar índice existente: {e}")
    return {"curso": os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA"), "modulos": []}

def crawl_course(sync_mode=True):
    """
    Varre a página do curso na Full Cycle, encontra os módulos e suas respectivas aulas.
    Se sync_mode=True, mescla as aulas encontradas sem apagar o histórico,
    marcando quais são novas para extração futura.
    """
    platform_url = os.getenv("PLATFORM_URL")
    target_course_name = os.getenv("COURSE_NAME")
    if not target_course_name:
        logger.error("A variável de ambiente 'COURSE_NAME' não está definida no arquivo .env!")
        raise ValueError("A variável de ambiente 'COURSE_NAME' não está definida no arquivo .env!")

    ignore_modules_str = os.getenv("IGNORE_MODULES", "")
    ignore_modules = [m.strip().strip('"').strip("'").lower() for m in ignore_modules_str.split(",") if m.strip()]

    if not STATE_PATH.exists():
        logger.error("Sessão não encontrada! Execute o script de login primeiro.")
        return None

    logger.info("Iniciando crawl do curso para mapeamento de módulos e aulas na Full Cycle...")
    existing_index = load_existing_index()
    
    # Criar um set de URLs já existentes para verificação rápida
    existing_urls = set()
    for mod in existing_index.get("modulos", []):
        for lesson in mod.get("aulas", []):
            existing_urls.add(lesson["url"])

    new_lessons_found = []

    with sync_playwright() as p:
        # Usa o headless configurado no settings.yaml (ou True por padrão)
        browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        try:
            # 1. Navegar para a página principal de cursos
            courses_url = "https://plataforma.fullcycle.com.br/courses"
            logger.info(f"Navegando para a listagem de cursos: {courses_url}")
            page.goto(courses_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            logger.info(f"Página carregada. URL atual: {page.url} | Título: {page.title()}")

            # 2. Encontrar a URL do curso configurado
            logger.info(f"Procurando curso correspondente a: '{target_course_name}'")
            
            links = page.query_selector_all("a")
            course_url = None
            course_full_name = None
            
            # 1. Tentar encontrar links diretos de curso (sem "/catalog/")
            for link in links:
                try:
                    text = page.evaluate("(el) => el.innerText", link).strip()
                    href = page.evaluate("(el) => el.href", link)
                    
                    if href and "/courses/" in href and "/catalog/" not in href:
                        if target_course_name.lower() in text.lower() or (
                            "mba" in target_course_name.lower() and "ia" in target_course_name.lower() and
                            "mba" in text.lower() and "ia" in text.lower()
                        ):
                            course_url = href
                            course_full_name = text.split("\n")[0]
                            break
                except Exception:
                    continue
                    
            # 2. Tentar encontrar qualquer link de curso ou catálogo se não achou direto
            if not course_url:
                for link in links:
                    try:
                        text = page.evaluate("(el) => el.innerText", link).strip()
                        href = page.evaluate("(el) => el.href", link)
                        
                        if href and ("/courses/" in href or "/catalog/" in href):
                            if target_course_name.lower() in text.lower() or (
                                "mba" in target_course_name.lower() and "ia" in target_course_name.lower() and
                                "mba" in text.lower() and "ia" in text.lower()
                            ):
                                course_url = href
                                course_full_name = text.split("\n")[0]
                                break
                    except Exception:
                        continue
                        
            # 3. Fallback: Pegar o primeiro link de curso se nada acima bater
            if not course_url:
                logger.warning(f"Não encontramos curso com o nome '{target_course_name}'. Tentando pegar o primeiro curso disponível...")
                for link in links:
                    try:
                        href = page.evaluate("(el) => el.href", link)
                        if href and "/courses/" in href and "/catalog/" not in href:
                            text = page.evaluate("(el) => el.innerText", link).strip()
                            course_url = href
                            course_full_name = text.split("\n")[0] if text else "Curso Detectado"
                            break
                    except Exception:
                        continue
                        
            if not course_url:
                logger.error("Nenhum curso encontrado na plataforma!")
                return []

            logger.info(f"Curso selecionado: '{course_full_name}' -> URL: {course_url}")

            # 3. Navegar para a página do curso e extrair os módulos
            page.goto(course_url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            logger.info("Extraindo módulos da página do curso...")
            module_links_data = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a'));
                const modules = [];
                links.forEach(l => {
                    const href = l.href;
                    const text = l.innerText.trim();
                    if (href && href.includes('/conteudos') && text) {
                        const lines = text.split('\\n').map(x => x.trim()).filter(Boolean);
                        let title = lines[0] || 'Módulo';
                        if (lines.length > 1 && /^\\d+$/.test(lines[0])) {
                            title = lines[1];
                        }
                        modules.push({
                            title: title,
                            url: href
                        });
                    }
                });
                return modules;
            }""")
            
            if not module_links_data:
                logger.error("Nenhum módulo encontrado na página do curso!")
                return []

            logger.info(f"Encontrados {len(module_links_data)} módulos. Iniciando extração de aulas...")
            scraped_modules = []

            # 4. Para cada módulo, navegar até a página /conteudos e extrair os capítulos e aulas
            for m_idx, m_data in enumerate(module_links_data):
                m_title = m_data["title"]
                m_url = m_data["url"]
                
                # Verificar se o módulo deve ser ignorado
                if any(ignored in m_title.lower() for ignored in ignore_modules):
                    logger.info(f"Módulo [{m_idx + 1}/{len(module_links_data)}]: '{m_title}' ignorado (conforme IGNORE_MODULES no .env).")
                    continue

                logger.info(f"Processando módulo [{m_idx + 1}/{len(module_links_data)}]: '{m_title}'")

                try:
                    page.goto(m_url, timeout=60000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)

                    # Expandir todos os capítulos (acordeões)
                    page.evaluate("""() => {
                        const buttons = document.querySelectorAll('h3 button[aria-expanded="false"]');
                        buttons.forEach(btn => btn.click());
                    }""")
                    page.wait_for_timeout(2000)

                    # Extrair os capítulos e suas aulas internas do DOM
                    chapters = page.evaluate("""() => {
                        const results = [];
                        const chapterElms = document.querySelectorAll('[id^="chapter-"]');
                        
                        chapterElms.forEach((elm) => {
                            const titleEl = elm.querySelector('h5');
                            const chapTitle = titleEl ? titleEl.innerText.trim() : '';
                            
                            const liElms = elm.querySelectorAll('li[id^="list-content-"]');
                            const lessons = [];
                            
                            liElms.forEach((li) => {
                                const liId = li.id;
                                const conteudoId = liId.replace('list-content-', '');
                                
                                const textEl = li.querySelector('.MuiListItemText-primary');
                                const lessonTitle = textEl ? textEl.innerText.trim() : '';
                                
                                if (lessonTitle) {
                                    lessons.push({
                                        title: lessonTitle,
                                        id: conteudoId
                                    });
                                }
                            });
                            
                            results.push({
                                chapterTitle: chapTitle,
                                lessons: lessons
                            });
                        });
                        return results;
                    }""")

                    # Formatar as aulas do módulo
                    aulas = []
                    # Obter modulo_id da URL do módulo
                    parts = m_url.rstrip("/").split("/")
                    modulo_id = parts[-2] if len(parts) >= 2 else ""

                    for chap in chapters:
                        chap_title = chap["chapterTitle"]
                        for lesson in chap["lessons"]:
                            lesson_title = lesson["title"]
                            lesson_id = lesson["id"]
                            
                            # Formatar URL no padrão Full Cycle para aulas
                            lesson_url = f"{m_url}?capitulo={modulo_id}&conteudo={lesson_id}"
                            lesson_slug = clean_slug(lesson_title)
                            
                            # Título composto: Capítulo - Aula
                            full_title = f"{chap_title} - {lesson_title}" if chap_title else lesson_title
                            
                            aula_data = {
                                "titulo": full_title,
                                "url": lesson_url,
                                "slug": lesson_slug
                            }
                            aulas.append(aula_data)
                            
                            if lesson_url not in existing_urls:
                                new_lessons_found.append({
                                    "modulo": m_title,
                                    **aula_data
                                })

                    if aulas:
                        scraped_modules.append({
                            "modulo": m_title,
                            "aulas": aulas
                        })
                        logger.info(f"Módulo '{m_title}' processado com sucesso. Aulas encontradas: {len(aulas)}")
                    else:
                        logger.warning(f"Nenhuma aula encontrada no módulo '{m_title}'!")

                except Exception as e:
                    logger.error(f"Erro ao processar o módulo '{m_title}': {e}")
                    continue

            # 5. Atualizar/Sincronizar o arquivo de índice
            if sync_mode:
                logger.info("Atualizando índice local de forma incremental (Sync Mode)...")
                existing_index["curso"] = course_full_name or existing_index.get("curso")
                
                for s_mod in scraped_modules:
                    # Verifica se o módulo já existe
                    matched_mod = next((m for m in existing_index["modulos"] if m["modulo"] == s_mod["modulo"]), None)
                    if not matched_mod:
                        existing_index["modulos"].append(s_mod)
                    else:
                        # Insere apenas aulas que não possuem a mesma URL
                        for s_aula in s_mod["aulas"]:
                            if not any(a["url"] == s_aula["url"] for a in matched_mod["aulas"]):
                                matched_mod["aulas"].append(s_aula)
                updated_index = existing_index
            else:
                logger.info("Sobrescrevendo índice local...")
                updated_index = {
                    "curso": course_full_name or target_course_name,
                    "modulos": scraped_modules
                }

            # Salvar arquivo JSON final
            INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(updated_index, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Índice do curso atualizado com sucesso em {INDEX_PATH}!")
            logger.info(f"Aulas novas detectadas neste sync: {len(new_lessons_found)}")
            
            return new_lessons_found

        except Exception as e:
            logger.exception(f"Erro ao varrer o curso: {e}")
            return []
        finally:
            browser.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Varredura de aulas da plataforma Full Cycle.")
    parser.add_argument("--no-sync", action="store_true", help="Sobrescrever o índice existente em vez de mesclar incrementalmente.")
    args = parser.parse_args()
    
    new_lessons = crawl_course(sync_mode=not args.no_sync)
    if new_lessons:
        print(f"Novas aulas encontradas para download:\n{json.dumps(new_lessons, indent=2)}")
