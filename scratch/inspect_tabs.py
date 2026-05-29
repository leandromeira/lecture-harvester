import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/config/storage_state.json")

def inspect_tabs(url):
    print(f"\n--- Analisando abas e painéis: {url} ---")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        
        # 1. Identificar botões de abas
        tabs = page.evaluate("""() => {
            const buttons = Array.from(document.querySelectorAll('button[role="tab"]'));
            return buttons.map((b, idx) => ({
                index: idx,
                text: b.innerText.trim(),
                selected: b.getAttribute('aria-selected') === 'true',
                id: b.id,
                controls: b.getAttribute('aria-controls')
            }));
        }""")
        print("Abas encontradas:")
        for t in tabs:
            print(f"  Tab {t['index']}: '{t['text']}' (Selected: {t['selected']}, id: {t['id']}, controls: {t['controls']})")
            
        # 2. Identificar painéis de conteúdo das abas (tabpanels)
        panels = page.evaluate("""() => {
            const panelElms = Array.from(document.querySelectorAll('[role="tabpanel"], [id^="panel-"]'));
            return panelElms.map((p, idx) => {
                const anchors = Array.from(p.querySelectorAll('a[href]'));
                const links = anchors.map(a => ({
                    text: a.innerText.trim(),
                    href: a.href
                })).filter(l => !l.href.includes('plataforma.fullcycle'));
                
                return {
                    index: idx,
                    id: p.id,
                    className: p.className,
                    textLength: p.innerText ? p.innerText.trim().length : 0,
                    textSample: p.innerText ? p.innerText.trim().substring(0, 150) : '',
                    externalLinks: links
                };
            });
        }""")
        print("\nPainéis de Abas (tabpanel) encontrados:")
        for p in panels:
            print(f"  Painel {p['index']}: id='{p['id']}', class='{p['className']}', length={p['textLength']}, sample='{p['textSample']}'")
            print(f"    Links externos no painel ({len(p['externalLinks'])}):")
            for l in p['externalLinks']:
                print(f"      - {l['text']}: {l['href']}")
                
        # 3. Se houver aba "Materiais" que não esteja selecionada, clicar nela e repetir a busca
        materiais_tab = next((t for t in tabs if "materiais" in t['text'].lower()), None)
        if materiais_tab and not materiais_tab['selected']:
            print(f"\nClicando na aba 'Materiais' ({materiais_tab['text']})...")
            page.click(f'button[role="tab"]:has-text("{materiais_tab["text"]}")')
            page.wait_for_timeout(3000)
            
            # Re-analisar painéis
            panels_after_click = page.evaluate("""() => {
                const panelElms = Array.from(document.querySelectorAll('[role="tabpanel"], [id^="panel-"]'));
                return panelElms.map((p, idx) => {
                    const anchors = Array.from(p.querySelectorAll('a[href]'));
                    const links = anchors.map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    })).filter(l => !l.href.includes('plataforma.fullcycle'));
                    
                    return {
                        index: idx,
                        id: p.id,
                        className: p.className,
                        textLength: p.innerText ? p.innerText.trim().length : 0,
                        textSample: p.innerText ? p.innerText.trim().substring(0, 150) : '',
                        externalLinks: links
                    };
                });
            }""")
            print("Painéis de Abas após clicar em 'Materiais':")
            for p in panels_after_click:
                print(f"  Painel {p['index']}: id='{p['id']}', class='{p['className']}', length={p['textLength']}, sample='{p['textSample']}'")
                print(f"    Links externos no painel ({len(p['externalLinks'])}):")
                for l in p['externalLinks']:
                    print(f"      - {l['text']}: {l['href']}")
                    
        browser.close()

if __name__ == "__main__":
    inspect_tabs("https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364")
