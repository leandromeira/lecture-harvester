import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_notion_links(url):
    print(f"\n--- Inspecionando links e estrutura do Notion: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH) if STATE_PATH.exists() else None)
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            print("Aguardando 6 segundos...")
            page.wait_for_timeout(6000)
            
            # Extrair links internos
            links = page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll('.notion-page-content a[href]'));
                return anchors.map(a => ({
                    text: a.innerText.trim(),
                    href: a.href,
                    html: a.outerHTML
                }));
            }""")
            
            print(f"Encontrados {len(links)} links dentro do conteúdo:")
            for idx, l in enumerate(links[:20]):
                print(f"  Link {idx + 1}:")
                print(f"    Texto: '{l['text']}'")
                print(f"    Href: '{l['href']}'")
                print(f"    HTML: '{l['html']}'")
                
            # Extrair títulos e classes do DOM para conversão em Markdown
            dom_sample = page.evaluate("""() => {
                const contentEl = document.querySelector('.notion-page-content');
                if (!contentEl) return 'Conteúdo não encontrado';
                
                // Pegar os primeiros 10 elementos filhos de segundo nível
                const children = Array.from(contentEl.querySelectorAll('.notion-selectable, h1, h2, h3, p, a'));
                return children.slice(0, 15).map(c => ({
                    tagName: c.tagName,
                    className: c.className,
                    innerText: c.innerText ? c.innerText.trim().substring(0, 100) : '',
                    html: c.outerHTML.substring(0, 150)
                }));
            }""")
            
            print("\nAmostra de elementos no DOM:")
            for idx, el in enumerate(dom_sample):
                print(f"  El {idx + 1}: <{el['tagName']}> class='{el['className']}', text='{el['innerText']}'")
                print(f"    HTML: {el['html']}...")
                
        except Exception as e:
            print(f"Erro: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    url = "https://devfullcycle.notion.site/Design-e-Arquitetura-2a01423c038880068dbff012c80c4aa2"
    inspect_notion_links(url)
