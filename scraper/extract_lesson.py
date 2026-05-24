import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_extraction_logger

logger = setup_extraction_logger()

# Configurações carregadas via variáveis de ambiente (.env)

STATE_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_state.json"
RAW_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Seletores para os elementos da aula no Full Cycle
SELECTORS = {
    "lesson_title": "h1, .MuiBreadcrumbs-ol li:last-child",
    "transcript_item": "span.css-1gie7yz",
    "summary_item": ".css-rymwba p, .css-rymwba"
}

def clean_filename(name):
    """Limpador de nome de pasta/arquivo para evitar problemas no OS."""
    import re
    return re.sub(r'[^a-zA-Z0-9\s_-]', '', name).strip()

def get_mock_data(curso, modulo, aula, url):
    """Gera dados simulados (mock) para testes da pipeline."""
    return {
        "curso": curso or os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA"),
        "modulo": modulo or "Módulo 01 - Introdução ao Harvester",
        "aula": aula or "Aula 01 - Primeiros Passos com o Pipeline",
        "url": url or "https://plataforma.exemplo.com/aulas/harvester-101",
        "resumo_original": "Este é um resumo original pré-existente na plataforma de ensino. Explica os conceitos básicos de como configurar seu ambiente python, instalar o playwright e rodar a extração inicial.",
        "transcricao": "Olá a todos e bem-vindos a esta aula de Introdução ao Pipeline. Hoje vamos falar sobre a filosofia do projeto. O nosso sistema não deve ser um agente autônomo. Queremos scripts previsíveis e um pipeline determinístico. Vamos usar caches locais. Por exemplo, salvamos a transcrição e o resumo em arquivos JSON brutos dentro da pasta data/raw. Depois, processamos isso separadamente usando a API da OpenAI. Isso desacopla a extração do processamento de IA. É excelente para economizar tokens, pois se quisermos alterar o prompt ou o modelo de IA, não precisamos fazer a raspagem de dados novamente. Também é importante configurar o storage_state no Playwright para evitar logins manuais repetidos. Colocamos o usuário e a senha no arquivo .env e deixamos o script se logar automaticamente se expirar. Na próxima aula falaremos sobre a Engenharia de Prompt e o tamanho das janelas de contexto (Context Window). Até lá!"
    }

def extract_lesson(url, modulo_nome, aula_titulo, slug, mock=False):
    """
    Navega para a URL da aula, extrai as informações brutas
    e salva o arquivo JSON correspondente na pasta data/raw/.
    """
    curso = os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    mod_clean = clean_filename(modulo_nome or "Modulo Desconhecido")
    slug_clean = clean_filename(slug or "aula_desconhecida")
    
    output_dir = RAW_DATA_DIR / mod_clean
    output_path = output_dir / f"{slug_clean}.json"

    if mock:
        logger.info(f"[MOCK] Gerando dados fictícios para {aula_titulo}...")
        data = get_mock_data(curso, modulo_nome, aula_titulo, url)
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"[MOCK] JSON gerado com sucesso em {output_path}")
        return data

    if not STATE_PATH.exists():
        logger.error("Sessão expirada ou arquivo de storage_state não encontrado. Faça o login primeiro.")
        return None

    logger.info(f"Extraindo aula: {aula_titulo} ({url})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true")
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        try:
            # Usar domcontentloaded e uma pequena espera para carregamento dos dados React
            page.goto(url, timeout=int(os.getenv("PLAYWRIGHT_TIMEOUT", 30000)), wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # Priorizar o título recebido do índice (aula_titulo), caindo de volta para a extração do DOM
            extracted_title = (aula_titulo or "").strip()
            if not extracted_title:
                title_el = page.query_selector(SELECTORS["lesson_title"])
                extracted_title = title_el.inner_text().strip() if title_el else "Sem título"

            # 1. Extrair resumo da aula
            resumo_elms = page.query_selector_all(SELECTORS["summary_item"])
            resumo_texts = []
            for el in resumo_elms:
                txt = el.inner_text().strip()
                if txt and txt not in resumo_texts:
                    resumo_texts.append(txt)
            resumo_original = "\n\n".join(resumo_texts)

            # 2. Clicar no botão da aba de transcrição
            clicked = page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const transBtn = buttons.find(b => b.innerText.includes("Transcrição"));
                if (transBtn) {
                    if (transBtn.disabled) return false;
                    transBtn.click();
                    return true;
                }
                return false;
            }""")

            transcricao = ""
            if clicked:
                # Aguarda renderização da transcrição
                page.wait_for_timeout(3000)
                # Extrair o conteúdo da transcrição
                trans_elms = page.query_selector_all(SELECTORS["transcript_item"])
                trans_texts = [el.inner_text().strip() for el in trans_elms]
                transcricao = " ".join([t for t in trans_texts if t])
            else:
                logger.warning(f"Aba de transcrição não disponível ou não pôde ser clicada para a aula {url}.")

            data = {
                "curso": curso,
                "modulo": modulo_nome or "Geral",
                "aula": extracted_title,
                "url": url,
                "transcricao": transcricao,
                "resumo_original": resumo_original
            }

            # Salva o JSON bruto
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Aula extraída com sucesso e salva em {output_path}")
            return data

        except Exception as e:
            logger.exception(f"Erro ao extrair dados da aula {url}: {e}")
            return None
        finally:
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai dados de uma aula específica.")
    parser.add_argument("--url", type=str, help="URL da aula.")
    parser.add_argument("--modulo", type=str, help="Nome do módulo.")
    parser.add_argument("--aula", type=str, help="Título da aula.")
    parser.add_argument("--slug", type=str, help="Slug para o nome do arquivo.")
    parser.add_argument("--mock", action="store_true", help="Gera dados mockados de simulação.")
    args = parser.parse_args()

    if not args.mock and not args.url:
        parser.error("A URL é obrigatória caso o modo --mock não esteja ativo.")

    extract_lesson(args.url, args.modulo, args.aula, args.slug, mock=args.mock)
