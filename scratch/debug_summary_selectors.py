import os
import sys
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_summary_elements(url):
    print(f"\n--- Inspecionando URL: {url} ---")
    if not STATE_PATH.exists():
        print(f"Erro: storage_state não encontrado em {STATE_PATH}")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded")
            print("Aguardando 8 segundos para a página carregar completamente...")
            page.wait_for_timeout(8000)
            
            print(f"URL final carregada: {page.url}")
            
            # Tirar screenshot para podermos conferir visualmente
            screenshot_path = Path("/Users/leandromeira/Dev/lecture-harvester/scratch/summary_debug.png")
            page.screenshot(path=str(screenshot_path))
            print(f"Screenshot salvo em: {screenshot_path}")
            
            # Buscar elementos contendo a palavra 'Redefinição' ou 'mentalidade' ou 'Material Complementar'
            print("\nProcurando elementos com base no conteúdo textual...")
            elements_info = page.evaluate("""() => {
                const results = [];
                // Procurar todas as tags p, h1, h2, h3, h4, h5, h6, div, span
                const tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'span'];
                tags.forEach(tag => {
                    const elms = Array.from(document.querySelectorAll(tag));
                    elms.forEach(el => {
                        const text = el.innerText ? el.innerText.trim() : '';
                        if (text.includes('Redefinição da profissão') || text.includes('Mentalidade sobre programar')) {
                            // Registra informações do elemento e seus pais para encontrar o melhor seletor
                            results.push({
                                tag: tag,
                                id: el.id,
                                className: el.className,
                                textSample: text.substring(0, 150),
                                parentTag: el.parentElement ? el.parentElement.tagName : '',
                                parentClass: el.parentElement ? el.parentElement.className : '',
                                parentParentTag: el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.tagName : '',
                                parentParentClass: el.parentElement && el.parentElement.parentElement ? el.parentElement.parentElement.className : ''
                            });
                        }
                    });
                });
                return results;
            }""")
            
            print(f"Encontrados {len(elements_info)} elementos candidatos:")
            for idx, info in enumerate(elements_info):
                print(f"\nCandidato {idx + 1}:")
                print(f"  Tag: {info['tag']} | ID: '{info['id']}' | Class: '{info['className']}'")
                print(f"  Sample: '{info['textSample']}'")
                print(f"  Pai: {info['parentTag']} | Pai Class: '{info['parentClass']}'")
                print(f"  Avô: {info['parentParentTag']} | Avô Class: '{info['parentParentClass']}'")
                
            # Agora vamos listar todos os H2, H3, H4, H5, p dentro de containers principais
            print("\nListando todos os títulos e parágrafos abaixo do Material Complementar...")
            content_structure = page.evaluate("""() => {
                const results = [];
                // Vamos tentar achar o botão 'Resumo da Aula' ou o título 'Resumo da Aula'
                const headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, p'));
                headings.forEach(h => {
                    const text = h.innerText ? h.innerText.trim() : '';
                    if (text.length > 5 && text.length < 200) {
                        results.push({
                            tag: h.tagName,
                            class: h.className,
                            text: text
                        });
                    }
                });
                return results;
            }""")
            for h in content_structure[:40]:
                print(f"  [{h['tag']}] (class: '{h['class']}'): {h['text']}")
                
        except Exception as e:
            print(f"Erro na execução do Playwright: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    url = "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17377"
    inspect_summary_elements(url)
