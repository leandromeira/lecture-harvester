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

def clean_filename(name):
    """Remove caracteres inválidos para nomes de arquivos e diretórios."""
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def extract_course_id(url):
    """Extrai o ID/slug do curso a partir da URL /courses/<id-ou-slug>."""
    match = re.search(r"/courses/([^/?#]+)", url or "")
    return match.group(1) if match else None

def list_available_courses(page):
    """Lista cursos visíveis na tela inicial de cursos."""
    courses = []
    seen_urls = set()
    links = page.query_selector_all("a")

    for link in links:
        try:
            text = page.evaluate("(el) => el.innerText", link).strip()
            href = page.evaluate("(el) => el.href", link)
            if not href or "/courses/" not in href:
                continue

            course_id = extract_course_id(href)
            if not course_id or href in seen_urls:
                continue

            name = text.split("\n")[0].strip() if text else course_id
            courses.append({"id": course_id, "name": name, "url": href})
            seen_urls.add(href)
        except Exception:
            continue

    return courses

def load_existing_index():
    """Carrega o índice atual se ele já existir."""
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao carregar índice existente: {e}")
    return {"curso": os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA"), "modulos": []}

def crawl_course(sync_mode=True, course_id=None, list_courses=False):
    """
    Varre a página do curso na Full Cycle, encontra os módulos e suas respectivas aulas.
    Se sync_mode=True, mescla as aulas encontradas sem apagar o histórico,
    marcando quais são novas para extração futura.
    """
    platform_url = os.getenv("PLATFORM_URL")
    target_course_name = os.getenv("COURSE_NAME")

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
            if "login" in page.url:
                logger.error("Sessão expirada ou inválida! O navegador foi redirecionado para a tela de login. Execute 'venv/bin/python scraper/login.py' para renovar sua sessão.")
                return []

            try:
                page.wait_for_selector('a[href*="/courses/"]', timeout=15000)
            except Exception:
                logger.warning("Timeout aguardando links de cursos. Tentando prosseguir...")
            page.wait_for_timeout(1000)
            logger.info(f"Página carregada. URL atual: {page.url} | Título: {page.title()}")

            # Clicar em "Listar Todos" se houver
            try:
                listar_todos_btn = page.locator("text=Listar Todos")
                if listar_todos_btn.count() > 0:
                    logger.info("Botão 'Listar Todos' encontrado. Expandindo lista de cursos...")
                    listar_todos_btn.first.click()
                    page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Erro ao tentar clicar em 'Listar Todos': {e}")

            # 2. Encontrar cursos e selecionar dinamicamente
            available_courses = list_available_courses(page)
            if list_courses:
                logger.info(f"Cursos encontrados: {len(available_courses)}")
                return available_courses

            if not available_courses:
                logger.error("Nenhum curso encontrado na plataforma!")
                return []

            selected_course = None
            normalized_course_id = str(course_id).strip() if course_id is not None else None
            if course_id:
                selected_course = next((c for c in available_courses if c["id"] == normalized_course_id), None)
                if not selected_course and normalized_course_id:
                    selected_course = next(
                        (c for c in available_courses if normalized_course_id in c["url"]),
                        None
                    )
                if not selected_course:
                    logger.error(f"Curso com ID '{course_id}' não encontrado.")
                    return []
            elif target_course_name:
                target_name_lower = target_course_name.lower()
                selected_course = next(
                    (c for c in available_courses if target_name_lower in c["name"].lower()),
                    None
                )
                if not selected_course and "mba" in target_name_lower and "ia" in target_name_lower:
                    selected_course = next(
                        (c for c in available_courses if "mba" in c["name"].lower() and "ia" in c["name"].lower()),
                        None
                    )

            if not selected_course:
                selected_course = available_courses[0]
                if target_course_name:
                    logger.warning(
                        f"Curso '{target_course_name}' não encontrado. Usando primeiro disponível: {selected_course['name']}"
                    )

            course_url = selected_course["url"]
            course_full_name = selected_course["name"]
            os.environ["COURSE_NAME"] = course_full_name
            logger.info(f"Curso selecionado: '{course_full_name}' -> URL: {course_url}")

            # 3. Navegar para a página do curso e extrair os módulos
            page.goto(course_url, timeout=60000, wait_until="domcontentloaded")
            try:
                page.wait_for_selector('a[href*="/conteudos"]', timeout=15000)
            except Exception:
                logger.warning("Timeout aguardando módulos do curso. Tentando prosseguir...")
            page.wait_for_timeout(1000)
            
            logger.info("Extraindo módulos da página do curso...")
            module_links_data = page.evaluate("""() => {
                const links = Array.from(document.querySelectorAll('a'));
                const modules = [];
                links.forEach(l => {
                    const href = l.href;
                    const text = l.innerText.trim();
                    if (href && href.includes('/conteudos') && text) {
                        const lines = text.split('\\n').map(x => x.trim()).filter(Boolean);
                        // Filtrar badges comuns que ficam no topo do link (ex: "Novo", "Nova", "Atualizado", "Em breve")
                        const filteredLines = lines.filter(x => {
                            const lower = x.toLowerCase();
                            return lower !== 'novo' && lower !== 'nova' && lower !== 'atualizado' && lower !== 'em breve';
                        });
                        let title = filteredLines[0] || 'Módulo';
                        if (filteredLines.length > 1 && /^\\d+$/.test(filteredLines[0])) {
                            title = filteredLines[1];
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
            active_m_idx = 1
            for m_idx, m_data in enumerate(module_links_data):
                m_raw_title = m_data["title"]
                m_url = m_data["url"]
                
                # Verificar se o módulo deve ser ignorado
                if any(ignored in m_raw_title.lower() for ignored in ignore_modules):
                    logger.info(f"Módulo [{m_idx + 1}/{len(module_links_data)}]: '{m_raw_title}' ignorado (conforme IGNORE_MODULES no .env).")
                    continue

                m_title = f"{active_m_idx:02d} - {m_raw_title}"
                active_m_idx += 1
                logger.info(f"Processando módulo [{m_idx}/{len(module_links_data)}]: '{m_title}'")

                try:
                    page.goto(m_url, timeout=60000, wait_until="domcontentloaded")
                    try:
                        page.wait_for_selector('[id^="chapter-"], h3 button', timeout=15000)
                    except Exception:
                        logger.warning("Timeout aguardando capítulos do módulo. Tentando prosseguir...")
                    page.wait_for_timeout(1000)

                    # Expandir todos os capítulos (acordeões)
                    page.evaluate("""() => {
                        const buttons = document.querySelectorAll('h3 button[aria-expanded="false"]');
                        buttons.forEach(btn => btn.click());
                    }""")
                    # Espera dinâmica para que pelo menos uma aula seja carregada/renderizada na tela
                    try:
                        page.wait_for_selector('[id^="list-content-"]', timeout=10000)
                    except Exception:
                        pass
                    page.wait_for_timeout(2000)  # Tempo adicional para garantir renderização de todo o lote

                    chapters = page.evaluate("""() => {
                        const results = [];
                        const chapterElms = document.querySelectorAll('[id^="chapter-"]');
                        
                        chapterElms.forEach((elm) => {
                            const titleEl = elm.querySelector('h5');
                            const chapTitle = titleEl ? titleEl.innerText.trim() : '';
                            
                            // Seleciona tanto li quanto a tags com id iniciando com list-content-
                            const itemElms = elm.querySelectorAll('[id^="list-content-"]');
                            const lessons = [];
                            
                            itemElms.forEach((item) => {
                                const itemId = item.id;
                                const conteudoId = itemId.replace('list-content-', '');
                                
                                const textEl = item.querySelector('.MuiListItemText-primary');
                                let lessonTitle = '';
                                if (textEl) {
                                    lessonTitle = textEl.textContent.trim();
                                } else {
                                    lessonTitle = item.textContent.trim();
                                }
                                
                                // Limpa sufixos de tempo (ex: "Slides120:00" -> "Slides", "Docker25:00" -> "Docker")
                                lessonTitle = lessonTitle.replace(/\\s*\\d{2}:\\d{2}$/, '').trim();
                                
                                const isExternal = item.tagName.toLowerCase() === 'a';
                                const externalUrl = isExternal ? item.href : null;
                                
                                if (lessonTitle) {
                                    lessons.push({
                                        title: lessonTitle,
                                        id: conteudoId,
                                        is_external: isExternal,
                                        external_url: externalUrl
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

                    for chap_idx, chap in enumerate(chapters):
                        chap_title = chap["chapterTitle"]
                        chap_folder = f"{chap_idx + 1:02d} - {chap_title}" if chap_title else ""
                        for lesson_idx, lesson in enumerate(chap["lessons"]):
                            lesson_title = lesson["title"]
                            lesson_id = lesson["id"]
                            is_external = lesson.get("is_external", False)
                            external_url = lesson.get("external_url")
                            
                            # Formatar URL
                            if is_external:
                                lesson_url = external_url
                            else:
                                lesson_url = f"{m_url}?capitulo={modulo_id}&conteudo={lesson_id}"
                                
                            lesson_slug = clean_slug(lesson_title)
                            
                            # Título numerado: ex: "01 - Introdução"
                            numbered_title = f"{lesson_idx + 1:02d} - {lesson_title}"
                            
                            aula_data = {
                                "titulo": numbered_title,
                                "url": lesson_url,
                                "slug": lesson_slug
                            }
                            if is_external:
                                aula_data["is_external"] = True
                                aula_data["external_url"] = external_url
                                
                            if chap_folder:
                                aula_data["subpasta"] = chap_folder
                                
                            aulas.append(aula_data)
                            
                            # Verifica se o arquivo JSON bruto correspondente já existe fisicamente no disco
                            raw_dir = INDEX_PATH.parent
                            mod_clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', m_title or "").strip()
                            if chap_folder:
                                chap_clean = clean_filename(chap_folder)
                                raw_file_path = raw_dir / mod_clean / chap_clean / f"{lesson_slug}.json"
                            else:
                                raw_file_path = raw_dir / mod_clean / f"{lesson_slug}.json"
                            
                            if lesson_url not in existing_urls or not raw_file_path.exists():
                                new_lessons_found.append({
                                    "curso": course_full_name or target_course_name or "Curso",
                                    "modulo": m_title,
                                    **aula_data
                                })
                            else:
                                # Se o arquivo existe, verifica se está vazio ou se é apenas um esqueleto (sem transcrição e sem resumo)
                                is_empty_or_skeleton = False
                                try:
                                    with open(raw_file_path, "r", encoding="utf-8") as f_raw:
                                        raw_json_data = json.load(f_raw)
                                        # Se for aula interna e não tiver transcrição nem resumo
                                        if not raw_json_data.get("is_external", False):
                                            if not raw_json_data.get("transcricao", "").strip() and not raw_json_data.get("resumo_original", "").strip():
                                                is_empty_or_skeleton = True
                                except Exception:
                                    is_empty_or_skeleton = True

                                if is_empty_or_skeleton:
                                    logger.info(f"Detectado cache incompleto/esqueleto para a aula '{numbered_title}'. Marcando para re-extração.")
                                    new_lessons_found.append({
                                        "curso": course_full_name or target_course_name or "Curso",
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
    parser.add_argument("--course-id", type=str, help="ID do curso para sincronizar.")
    parser.add_argument("--list-courses", action="store_true", help="Lista cursos disponíveis e encerra.")
    args = parser.parse_args()

    result = crawl_course(sync_mode=not args.no_sync, course_id=args.course_id, list_courses=args.list_courses)
    if result:
        if args.list_courses:
            print("Cursos disponíveis:")
            for course in result:
                print(f"- ID {course['id']}: {course['name']}")
        else:
            print(f"Novas aulas encontradas para download:\n{json.dumps(result, indent=2)}")
