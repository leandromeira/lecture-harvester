import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_notion(url):
    print(f"\n--- Inspecionando Notion URL: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use simple context (no storage state needed for public Notion docs, but let's load it just in case)
        context = browser.new_context(storage_state=str(STATE_PATH) if STATE_PATH.exists() else None)
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        print("Aguardando 6 segundos para o Notion renderizar...")
        page.wait_for_timeout(6000)
        
        # Tirar screenshot
        screenshot_path = Path("/Users/leandromeira/Dev/lecture-harvester/data/exploration/screenshots/notion_test.png")
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot salvo em: {screenshot_path}")
        
        # Testar seletores de título e conteúdo do Notion
        # Notion moderno usa classes bem específicas ou seletores
        title = page.evaluate("""() => {
            // Tenta encontrar o título usando diferentes classes do Notion
            const titleEl = document.querySelector('.notion-page-block h1, h1.notion-page-title, .notion-title-block, .notion-page-controls + div');
            if (titleEl) return titleEl.innerText.trim();
            
            // Fallback: tenta buscar o primeiro h1 ou elemento h1 na página
            const firstH1 = document.querySelector('h1, h2');
            if (firstH1) return firstH1.innerText.trim();
            
            return document.title || 'Não encontrado';
        }""")
        
        content = page.evaluate("""() => {
            // Conteúdo principal do Notion
            const contentEl = document.querySelector('.notion-page-content');
            return contentEl ? contentEl.innerText.trim().substring(0, 1000) + '...' : 'Não encontrado';
        }""")
        
        print(f"Título detectado: '{title}'")
        print(f"Início do conteúdo detectado:\n{content}")
        
        # Vamos imprimir a lista de algumas classes importantes presentes na página
        classes = page.evaluate("""() => {
            const divs = Array.from(document.querySelectorAll('div'));
            const classSet = new Set();
            divs.forEach(d => {
                if (d.className) {
                    d.className.split(' ').forEach(c => {
                        if (c.startsWith('notion-')) classSet.add(c);
                    });
                }
            });
            return Array.from(classSet);
        }""")
        print(f"Classes 'notion-' encontradas na página: {classes}")
        
        browser.close()

if __name__ == "__main__":
    inspect_notion("https://devfullcycle.notion.site/Quick-Wins-com-IA-29-07-2025-2411423c0388801d8369f34cfe403e6c")
