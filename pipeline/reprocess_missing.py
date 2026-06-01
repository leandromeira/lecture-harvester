import os
import sys
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
STATE_PATH = PROJECT_ROOT / "config" / "storage_state.json"

sys.path.append(str(PROJECT_ROOT))
from pipeline.generate_markdown import generate_obsidian_markdown
from pipeline.ai_summarizer import process_lesson_ai

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

def map_urls_to_raw_files():
    """Mapeia URLs de aulas para seus respectivos caminhos de arquivos JSON brutos."""
    mapping = {}
    for rf in RAW_DIR.glob("**/*.json"):
        if rf.name == "course_index.json":
            continue
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
            url = data.get("url", "")
            if url:
                mapping[url] = rf
        except Exception:
            pass
    return mapping

def check_md_missing_content(md_path: Path):
    """Analisa uma nota Markdown e retorna se ela precisa de resumo ou transcrição."""
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"Erro ao ler a nota {md_path.name}: {e}")
        return None

    # Parse YAML Frontmatter
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not fm_match:
        return None
        
    fm_text = fm_match.group(1)
    metadata = {}
    for line in fm_text.split('\n'):
        if ':' in line:
            parts = line.split(':', 1)
            k = parts[0].strip()
            v = parts[1].strip().strip('"').strip("'")
            metadata[k] = v

    url = metadata.get("url", "")
    aula = metadata.get("aula", "")
    
    if not url or "plataforma.fullcycle.com.br" not in url:
        return None

    aula_lower = aula.lower()
    # Pular materiais e slides que naturalmente não possuem vídeo/transcrição
    if any(keyword in aula_lower for keyword in ["material", "slides", "código fonte", "codigo-fonte", "código-fonte", "templates", "guidelines", "github", "desafio"]):
        return None

    # Verificar se as seções estão vazias ou contêm os placeholders de ausência
    resumo_match = re.search(r'# Resumo da aula na plataforma\s*\n(.*?)(?=\n#|\Z)', content, re.DOTALL)
    trans_match = re.search(r'# Transcrição completa da aula\s*\n(.*?)(?=\n#|\Z)', content, re.DOTALL)

    resumo_text = resumo_match.group(1).strip() if resumo_match else ""
    trans_text = trans_match.group(1).strip() if trans_match else ""

    need_summary = not resumo_text or resumo_text == "Sem resumo na plataforma."
    need_trans = not trans_text or trans_text == "Sem transcrição disponível." or len(trans_text) < 10

    if need_summary or need_trans:
        return {
            "path": md_path,
            "url": url,
            "aula": aula,
            "modulo": metadata.get("modulo", "Geral"),
            "curso": metadata.get("curso", ""),
            "need_summary": need_summary,
            "need_trans": need_trans,
            "metadata": metadata
        }

    return None

def extract_content_from_platform(page, url, need_summary, need_transcription):
    """Navega para a URL da aula na Full Cycle e extrai resumo e/ou transcrição."""
    resumo_original = ""
    transcricao = ""
    
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # 1. Extração do resumo se necessário
        if need_summary:
            for attempt in range(1, 6):
                resumo_elms = page.query_selector_all(".MuiTypography-h5 p, .MuiTypography-h5 h2")
                resumo_texts = []
                for el in resumo_elms:
                    txt = el.inner_text().strip()
                    if txt and txt not in resumo_texts:
                        resumo_texts.append(txt)
                
                if not resumo_texts:
                    fallback_elms = page.query_selector_all(".MuiTypography-h5")
                    for el in fallback_elms:
                        txt = el.inner_text().strip()
                        if txt and txt not in resumo_texts:
                            resumo_texts.append(txt)
                
                resumo_original = "\n\n".join(resumo_texts).strip()
                if resumo_original:
                    break
                    
                if attempt == 2:
                    try:
                        resumo_btn = page.locator('button', has_text="Resumo da Aula")
                        if resumo_btn.is_visible():
                            resumo_btn.click()
                    except:
                        pass
                page.wait_for_timeout(1000)
                
        # 2. Extração de transcrição se necessário
        if need_transcription:
            for attempt in range(1, 6):
                # Tentar clicar no botão nas primeiras tentativas
                if attempt in (1, 2):
                    try:
                        trans_btn = page.locator('button', has_text="Transcrição")
                        if trans_btn.is_visible():
                            trans_btn.click(timeout=3000)
                    except:
                        pass
                
                page.wait_for_timeout(1500)
                
                # Buscar elementos da transcrição
                trans_elms = page.query_selector_all("#panel-1 div > span:last-child")
                if not trans_elms:
                    trans_elms = page.query_selector_all("#panel-1 span")
                
                trans_texts = [el.inner_text().strip() for el in trans_elms]
                # Filtrar timestamps
                trans_texts = [t for t in trans_texts if t and not re.match(r'^\d{2}:\d{2}(:\d{2})?$', t)]
                
                transcricao = " ".join(trans_texts).strip()
                if transcricao:
                    break
                    
                page.wait_for_timeout(1000)
                
        return resumo_original, transcricao
        
    except Exception as e:
        print(f"    Erro de navegação/extração: {e}")
        return "", ""

def reprocess_missing_content(use_ai=False):
    """Varre o vault do Obsidian buscando notas com conteúdo ausente e as re-extrai."""
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH")
    if not vault_path_str:
        print("Erro: OBSIDIAN_VAULT_PATH não definida no arquivo .env.")
        return False

    vault_path = Path(vault_path_str)
    if not vault_path.exists():
        print(f"Erro: O caminho do vault do Obsidian não existe: {vault_path}")
        return False

    if not STATE_PATH.exists():
        print("Erro: storage_state.json não encontrado. Faça o login antes de reprocessar.")
        return False

    print("Varrendo o vault do Obsidian em busca de notas incompletas...")
    md_files = list(vault_path.glob("**/*.md"))
    
    candidates = []
    for mf in md_files:
        res = check_md_missing_content(mf)
        if res:
            candidates.append(res)
            
    print(f"Total de notas no vault analisadas: {len(md_files)}")
    print(f"Total de notas identificadas como incompletas: {len(candidates)}")
    
    if not candidates:
        print("Tudo certo! Nenhuma nota incompleta encontrada no vault.")
        return True

    # Carregar mapeamento de URLs para arquivos JSON locais
    url_to_raw = map_urls_to_raw_files()
    
    updated_count = 0
    
    print("\nIniciando Playwright em modo headless...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        for idx, item in enumerate(candidates, start=1):
            aula = item["aula"]
            url = item["url"]
            need_sum = item["need_summary"]
            need_trans = item["need_trans"]
            
            print(f"\n[{idx}/{len(candidates)}] Reprocessando: '{aula}'")
            print(f"  URL: {url}")
            print(f"  Ações necessárias: {'[Resumo]' if need_sum else ''} {'[Transcrição]' if need_trans else ''}")
            
            # Tenta localizar o JSON correspondente
            raw_path = url_to_raw.get(url)
            if not raw_path:
                # Se não encontrar no mapeamento de URLs existentes, tenta calcular o caminho padrão
                def clean_filename_local(name):
                    return re.sub(r'[\\/*?:"<>|]', '', name).strip()
                
                mod_clean = clean_filename_local(item["modulo"])
                slug_clean = clean_slug(aula)
                raw_path = RAW_DIR / mod_clean / f"{slug_clean}.json"
                print(f"  ⚠️ JSON bruto não mapeado por URL. Usando caminho padrão: {raw_path.name}")
                
            # Extrair da plataforma
            extracted_sum, extracted_trans = extract_content_from_platform(page, url, need_sum, need_trans)
            
            # Carregar ou inicializar o JSON
            if raw_path.exists():
                try:
                    with open(raw_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            else:
                data = {}
                
            # Preencher dados básicos se o JSON for novo
            if not data:
                data = {
                    "curso": item["curso"] or os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA"),
                    "modulo": item["modulo"],
                    "aula": aula,
                    "url": url,
                    "transcricao": "",
                    "resumo_original": "",
                    "materiais_apoio": []
                }
                
            updated = False
            if extracted_sum:
                data["resumo_original"] = extracted_sum
                print("  -> Resumo extraído com sucesso.")
                updated = True
            elif need_sum:
                print("  -> Resumo não disponível na plataforma.")
                
            if extracted_trans:
                data["transcricao"] = extracted_trans
                print("  -> Transcrição extraída com sucesso.")
                updated = True
            elif need_trans:
                print("  -> Transcrição não disponível ou desabilitada na plataforma.")
                
            if updated:
                # Salva o JSON bruto atualizado
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                with open(raw_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("  -> JSON bruto atualizado.")
                
                # Se solicitado, processa a IA (Phase 3)
                if use_ai:
                    print("  -> Processando enriquecimento IA...")
                    process_lesson_ai(raw_path, force=True)
                    
                # Regenera o Markdown no vault
                generate_obsidian_markdown(raw_path, force=True)
                print("  -> Nota Markdown regerada no vault do Obsidian.")
                updated_count += 1
            else:
                print("  -> Nenhuma nova informação pôde ser extraída da plataforma.")
                
        browser.close()
        
    print(f"\n==========================================")
    print(f"REPROCESSAMENTO CONCLUÍDO")
    print(f"==========================================")
    print(f"Total de notas verificadas como incompletas: {len(candidates)}")
    print(f"Notas atualizadas com sucesso: {updated_count}")
    print(f"==========================================\n")
    return True
