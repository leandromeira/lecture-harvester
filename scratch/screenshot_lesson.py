import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def take_screenshot(url, filename):
    print(f"\n--- Acessando: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(8000)
            
            # Print title
            print(f"Título da página: {page.title()}")
            
            # Print some page details
            content = page.evaluate("""() => {
                const header = document.querySelector('h1') || document.querySelector('h2');
                const mainText = document.body ? document.body.innerText.substring(0, 500) : 'Sem corpo';
                const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText + (b.disabled ? ' (disabled)' : ''));
                return {
                    header: header ? header.innerText : 'Sem header',
                    mainText: mainText,
                    buttons: buttons
                };
            }""")
            
            print(f"Header: {content['header']}")
            print(f"Botões na página: {content['buttons']}")
            print(f"Amostra de texto:\n{content['mainText'][:300]}")
            
            # Salvar screenshot
            dest_path = Path(__file__).resolve().parent / filename
            page.screenshot(path=str(dest_path))
            print(f"Screenshot salvo em: {dest_path}")
            
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    url = "https://devfullcycle.notion.site/HLD-Rate-Limiter-2981423c0388803c904ac92eeb11a049?pvs=25"
    take_screenshot(url, "notion_subpage_test.png")
