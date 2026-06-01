import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_transcript_dom(url):
    print(f"\n--- Inspecionando DOM do painel de transcrição para: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            # Clicar na aba Transcrição para garantir
            try:
                trans_btn = page.locator('button', has_text="Transcrição")
                if trans_btn.is_visible():
                    trans_btn.click()
                    print("Clicou na aba Transcrição.")
                    page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Erro ao tentar clicar na aba Transcrição: {e}")

            # Dump structural overview of #panel-1
            panel_data = page.evaluate("""() => {
                const panel = document.querySelector('#panel-1');
                if (!panel) return { found: false };
                
                // Pegar os primeiros filhos e suas tags/classes
                const children = Array.from(panel.children).map((c, i) => ({
                    index: i,
                    tagName: c.tagName,
                    className: c.className,
                    innerTextSample: c.innerText ? c.innerText.trim().substring(0, 100) : '',
                    childrenCount: c.children.length
                }));
                
                return {
                    found: true,
                    innerHTML: panel.innerHTML.substring(0, 2000),
                    children: children
                };
            }""")
            
            if not panel_data['found']:
                print("Painel #panel-1 não encontrado!")
            else:
                print("Estrutura de #panel-1:")
                for child in panel_data['children']:
                    print(f"  Child {child['index']}: <{child['tagName']}> class='{child['className']}', children={child['childrenCount']}, text='{child['innerTextSample']}'")
                print("\nHTML parcial de #panel-1:")
                print(panel_data['innerHTML'])
                
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    url = "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364"
    inspect_transcript_dom(url)
