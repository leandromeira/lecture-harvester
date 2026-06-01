import os
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_dom(url):
    print(f"\n--- Inspecionando DOM para: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            # Dump the innerHTML of .css-16mda28 or any element with MuiTypography-h5
            html_dumps = page.evaluate("""() => {
                const results = [];
                const elms = Array.from(document.querySelectorAll('.MuiTypography-h5, .css-16mda28'));
                elms.forEach((el, idx) => {
                    results.push({
                        index: idx,
                        tagName: el.tagName,
                        className: el.className,
                        innerHTML: el.innerHTML
                    });
                });
                return results;
            }""")
            
            print(f"Encontrados {len(html_dumps)} elementos:")
            for dump in html_dumps:
                print(f"\nElemento {dump['index'] + 1} ({dump['tagName']} class='{dump['className']}'):")
                print("HTML:")
                print(dump['innerHTML'][:1000]) # Mostra os primeiros 1000 caracteres
                print("-" * 50)
                
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    url = "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17377"
    inspect_dom(url)
