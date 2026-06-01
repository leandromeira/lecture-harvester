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

SELECTORS = {
    "summary_item": ".MuiTypography-h5 p, .MuiTypography-h5 h2"
}

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def extract_summary(page, url):
    """Executa a rotina robusta de extração de resumo."""
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        resumo_original = ""
        for attempt in range(1, 6):
            resumo_elms = page.query_selector_all(SELECTORS["summary_item"])
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
                return resumo_original

            # Forçar clique na aba do resumo
            if attempt == 2:
                try:
                    resumo_btn = page.locator('button', has_text="Resumo da Aula")
                    if resumo_btn.is_visible():
                        resumo_btn.click()
                except:
                    pass

            page.wait_for_timeout(1000)
            
        return ""
    except Exception as e:
        print(f"    Erro ao acessar a página: {e}")
        return ""

def main():
    if not STATE_PATH.exists():
        print("Erro: storage_state.json não encontrado. Faça login antes.")
        sys.exit(1)

    print("Varrendo arquivos locais para identificar aulas com resumo ausente...")
    raw_files = list(RAW_DIR.glob("**/*.json"))
    raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]
    
    candidates = []
    for rf in raw_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            is_external = data.get("is_external", False)
            lesson_title = data.get("aula", "")
            resumo = data.get("resumo_original", "").strip()
            
            if is_external:
                continue
                
            # Desconsiderar materiais e slides
            title_lower = lesson_title.lower()
            if any(keyword in title_lower for keyword in ["material", "slides", "código fonte", "codigo-fonte", "código-fonte"]):
                continue
                
            if not resumo:
                candidates.append((rf, data))
        except Exception as e:
            print(f"Erro ao analisar {rf.name}: {e}")

    print(f"Total de aulas identificadas sem resumo: {len(candidates)}")
    if not candidates:
        print("Nenhuma aula precisa de re-extração. Tudo em ordem!")
        return

    success_count = 0
    updated_count = 0

    print("\nIniciando navegador com Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        for idx, (rf_path, data) in enumerate(candidates, start=1):
            aula = data.get("aula", "Sem título")
            url = data.get("url", "")
            
            print(f"[{idx}/{len(candidates)}] Verificando: '{aula}'...")
            
            resumo = extract_summary(page, url)
            if resumo:
                print(f"  -> Resumo encontrado! Salvando no JSON...")
                data["resumo_original"] = resumo
                
                # Salvar JSON atualizado
                with open(rf_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    
                # Regerar Markdown correspondente
                try:
                    generate_obsidian_markdown(rf_path, force=True)
                    print(f"  -> Markdown atualizado no Obsidian.")
                except Exception as md_err:
                    print(f"  -> Erro ao atualizar Markdown: {md_err}")
                
                updated_count += 1
            else:
                print(f"  -> Aula realmente não possui resumo na plataforma.")
                
            success_count += 1
            
        browser.close()

    print(f"\n==========================================")
    print(f"RE-EXTRAÇÃO DE RESUMOS CONCLUÍDA")
    print(f"==========================================")
    print(f"Total de aulas verificadas: {success_count}")
    print(f"Aulas atualizadas com novo resumo: {updated_count}")
    print(f"Aulas sem resumo na plataforma: {success_count - updated_count}")
    print(f"==========================================\n")

if __name__ == "__main__":
    main()
