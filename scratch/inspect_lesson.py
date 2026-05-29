import os
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_lesson(url):
    print(f"\n--- Inspecionando URL: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        
        # Espera forçada de 8 segundos para garantir carregamento completo
        print("Aguardando 8 segundos para o React carregar...")
        page.wait_for_timeout(8000)
        
        # Dump da URL final
        print(f"URL final: {page.url}")
        
        # Tirar screenshot para verificação
        screenshot_path = Path("/Users/leandromeira/Dev/lecture-harvester/data/exploration/screenshots/inspect_test.png")
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot salvo em: {screenshot_path}")
        
        # Procurar por tags de vídeo e iframe
        videos = page.locator("video").all()
        iframes = page.locator("iframe").all()
        print(f"Vídeos encontrados: {len(videos)}")
        for idx, vid in enumerate(videos):
            print(f"  Video {idx}: src={vid.get_attribute('src')}, class={vid.get_attribute('class')}")
            
        print(f"Iframes encontrados: {len(iframes)}")
        for idx, iframe in enumerate(iframes):
            print(f"  Iframe {idx}: src={iframe.get_attribute('src')}, class={iframe.get_attribute('class')}")
            
        # Procurar títulos ou resumos (.MuiTypography-h5, p, h1, h2, h3)
        h1s = page.locator("h1").all()
        print(f"h1s encontrados: {len(h1s)}")
        for idx, h1 in enumerate(h1s):
            print(f"  h1 {idx}: text='{h1.inner_text().strip()}'")
            
        # Vamos listar classes de div que parecem conter o conteúdo principal
        # Ex: divs com texto longo
        divs = page.evaluate("""() => {
            const results = [];
            const allDivs = Array.from(document.querySelectorAll('div'));
            allDivs.forEach(div => {
                const text = div.innerText ? div.innerText.trim() : '';
                if (text.length > 100 && text.length < 1000 && !text.includes('Meus Cursos') && !text.includes('Termos de Uso')) {
                    results.push({
                        class: div.className,
                        textLength: text.length,
                        textSample: text.substring(0, 100)
                    });
                }
            });
            return results.slice(0, 10);
        }""")
        print("\nDivs com conteúdo em potencial:")
        for idx, d in enumerate(divs):
            print(f"  Div {idx}: class='{d['class']}', length={d['textLength']}, sample='{d['textSample']}'")
            
        # Coleta de todos os links
        links = page.evaluate("""() => {
            const anchors = Array.from(document.querySelectorAll('a[href]'));
            return anchors.map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.href
            })).filter(l => l.href.startsWith('http') && !l.href.includes('plataforma.fullcycle'));
        }""")
        print(f"\nLinks externos encontrados ({len(links)}):")
        for l in links:
            print(f"  - {l['text']}: {l['href']}")
            
        browser.close()

if __name__ == "__main__":
    # Testar com uma das aulas que deu external_link_lecture sem vídeo
    url_test_1 = "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364"
    inspect_lesson(url_test_1)
    
    # Testar com a aula de Desenvolvimento de aplicações com IA que tem links
    url_test_2 = "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17377"
    inspect_lesson(url_test_2)
