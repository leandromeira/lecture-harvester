import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "config" / "storage_state.json"

def main():
    if not STATE_PATH.exists():
        print("Erro: storage_state.json não encontrado.")
        return

    print("Iniciando Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        print("Navegando para https://plataforma.fullcycle.com.br/courses...")
        page.goto("https://plataforma.fullcycle.com.br/courses", timeout=60000, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # Verificar se existe "Listar Todos"
        listar_todos_btn = page.locator("text=Listar Todos")
        if listar_todos_btn.count() > 0:
            print("Botão 'Listar Todos' encontrado! Informações do botão:")
            # Imprimir tag name e classe
            inner_html = listar_todos_btn.first.inner_html()
            print(f"HTML interno: {inner_html}")
            
            print("Clicando em 'Listar Todos'...")
            listar_todos_btn.first.click()
            page.wait_for_timeout(4000)
            print("Botão clicado.")
        else:
            print("Botão 'Listar Todos' NÃO encontrado.")

        # Tirar screenshot pós-clique
        screenshot_path = PROJECT_ROOT / "scratch" / "courses_screenshot_after.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot salvo em {screenshot_path}")

        # Listar todos os links <a> na página
        print("\n--- Listando todos os links da página após clique ---")
        links = page.query_selector_all("a")
        for link in links:
            try:
                href = link.get_attribute("href")
                text = link.inner_text().strip().replace('\n', ' ')
                if href:
                    print(f"Link: {href} | Texto: {text}")
            except Exception as e:
                pass

        browser.close()

if __name__ == "__main__":
    main()
