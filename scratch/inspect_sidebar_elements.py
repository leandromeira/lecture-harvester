import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_sidebar_elements(url):
    print(f"\n--- Analisando elementos da sidebar em: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        # Obter o HTML das li do menu lateral
        items = page.evaluate("""() => {
            const listItems = Array.from(document.querySelectorAll('ul.MuiList-root.MuiList-padding li, ul.MuiList-root.MuiList-padding a'));
            return listItems.slice(0, 15).map((el, idx) => ({
                index: idx,
                tagName: el.tagName.toLowerCase(),
                id: el.id,
                className: el.className,
                html: el.outerHTML.substring(0, 300)
            }));
        }""")
        
        for item in items:
            print(f"Item {item['index']}: <{item['tagName']}> id='{item['id']}' class='{item['className']}'")
            print(f"  HTML: {item['html']}")
            print("-" * 50)
            
        browser.close()

if __name__ == "__main__":
    inspect_sidebar_elements("https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364")
