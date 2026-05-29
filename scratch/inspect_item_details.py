import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_item_details(url):
    print(f"\n--- Analisando detalhadamente itens da sidebar em: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        # Obter HTML detalhado e textos de sub-elementos para os primeiros itens da sidebar
        items = page.evaluate("""() => {
            const listItems = Array.from(document.querySelectorAll('[id^="list-content-"]'));
            return listItems.slice(0, 3).map((el, idx) => {
                return {
                    index: idx,
                    tagName: el.tagName.toLowerCase(),
                    id: el.id,
                    href: el.href || null,
                    textContent: el.textContent.trim(),
                    html: el.outerHTML
                };
            });
        }""")
        
        for item in items:
            print(f"Item {item['index']}: <{item['tagName']}> id='{item['id']}' href='{item['href']}'")
            print(f"  textContent: '{item['textContent']}'")
            print(f"  HTML: {item['html']}")
            print("-" * 50)
            
        browser.close()

if __name__ == "__main__":
    inspect_item_details("https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364")
