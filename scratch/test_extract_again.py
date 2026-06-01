import os
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")
SELECTORS = {
    "lesson_title": "h1, .MuiBreadcrumbs-ol li:last-child",
    "summary_item": ".MuiTypography-h5 p, .MuiTypography-h5 h2"
}

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def test_extract(url, title):
    print(f"\nTentando extrair: '{title}' ({url})")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            # Loop de retry
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
                    print(f"  -> Sucesso na tentativa {attempt}! Tamanho do resumo: {len(resumo_original)} caracteres.")
                    print(f"  -> Início do resumo: '{resumo_original[:120]}...'")
                    return True

                if attempt == 2:
                    try:
                        resumo_btn = page.locator('button', has_text="Resumo da Aula")
                        if resumo_btn.is_visible():
                            resumo_btn.click()
                    except:
                        pass

                page.wait_for_timeout(1000)
                
            print("  -> Não foi encontrado nenhum resumo na plataforma para esta aula (após 5 segundos).")
            return False
            
        except Exception as e:
            print(f"  -> Erro na navegação: {e}")
            return False
        finally:
            browser.close()

def main():
    # Testar com 3 aulas que deram falta de resumo
    test_cases = [
        {
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17387",
            "title": "Ferramentas e Workflows"
        },
        {
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17389",
            "title": "Paralelização"
        },
        {
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16375",
            "title": "Como a Gen IA aprende"
        }
    ]
    
    for tc in test_cases:
        test_extract(tc["url"], tc["title"])

if __name__ == "__main__":
    main()
