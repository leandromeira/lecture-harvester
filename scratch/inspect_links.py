import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_links(url):
    print(f"\n--- Analisando Links de: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000) # espera carregar tudo
        
        # Obter detalhes de todos os links com informações de seus pais (parents)
        link_details = page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => {
                // Obter árvore de pais simples
                let path = [];
                let parent = a.parentElement;
                while (parent && path.length < 5) {
                    let selector = parent.tagName.toLowerCase();
                    if (parent.id) selector += '#' + parent.id;
                    if (parent.className) {
                        // Limitar classes para não ficar gigante
                        const classes = Array.from(parent.classList).join('.');
                        if (classes) selector += '.' + classes;
                    }
                    path.push(selector);
                    parent = parent.parentElement;
                }
                
                return {
                    text: (a.innerText || a.textContent || '').trim(),
                    href: a.href,
                    path: path.reverse().join(' > '),
                    parentClass: a.parentElement.className
                };
            }).filter(l => l.href.startsWith('http') && !l.href.includes('plataforma.fullcycle'));
        }""")
        
        for idx, l in enumerate(link_details):
            print(f"Link {idx}:")
            print(f"  Texto: '{l['text']}'")
            print(f"  URL: {l['href']}")
            print(f"  Parent Class: '{l['parentClass']}'")
            print(f"  Caminho dos Pais: {l['path']}")
            print("-" * 50)
            
        browser.close()

if __name__ == "__main__":
    inspect_links("https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17377")
