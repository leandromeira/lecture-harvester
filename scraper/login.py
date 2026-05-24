import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Carregar variáveis de ambiente e log
load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_extraction_logger

logger = setup_extraction_logger()

# Configurações carregadas via variáveis de ambiente (.env)

STATE_PATH = Path(__file__).resolve().parents[1] / "config" / "storage_state.json"

# Seletores do login (Ajuste conforme a sua plataforma)
# Estes seletores podem ser editados manualmente ou por um agente explorador
SELECTORS = {
    "username_input": 'input[type="email"], input[type="text"], #username, #email',
    "password_input": 'input[type="password"], #password',
    "submit_button": 'button[type="submit"], #login-btn, .login-button',
    # Um seletor na página interna que confirma que o login foi bem sucedido
    "logged_in_indicator": '.dashboard, .user-profile, a[href*="logout"], .course-list, text="Meus Cursos", text="Central do Aluno", .MuiAvatar-root'
}

def login(force=False):
    """
    Realiza o login na plataforma.
    Se force=False e o storage_state.json existir, valida a sessão atual.
    Se não for válido ou se force=True, inicia um navegador headed interativo
    para que o usuário realize o login manualmente, salvando o estado da sessão.
    """
    platform_url = os.getenv("PLATFORM_URL")
    if not platform_url:
        logger.error("PLATFORM_URL não está definida no arquivo .env!")
        return False

    # 1. Se o cache de sessão existir e não formos forçar o login, valida
    if STATE_PATH.exists() and not force:
        logger.info("Encontrado storage_state.json anterior. Validando sessão...")
        with sync_playwright() as p:
            headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(storage_state=str(STATE_PATH))
            page = context.new_page()
            try:
                page.goto(platform_url, timeout=int(os.getenv("PLAYWRIGHT_TIMEOUT", 30000)))
                page.wait_for_load_state("networkidle")
                
                logged_in = False
                try:
                    page.wait_for_selector(SELECTORS["logged_in_indicator"], timeout=5000)
                    logged_in = True
                except Exception:
                    current_url = page.url
                    if "/courses" in current_url or "/conteudos" in current_url:
                        logger.info(f"Seletor indicador não apareceu, mas URL '{current_url}' indica login bem-sucedido.")
                        logged_in = True
                
                if logged_in:
                    logger.info("Sessão existente é válida e ativa.")
                    return True
                else:
                    logger.warning("Sessão existente é inválida ou expirou. Iniciando login interativo...")
            except Exception as e:
                logger.warning(f"Erro ao validar sessão existente: {e}. Iniciando login interativo...")
            finally:
                browser.close()

    # 2. Inicia login interativo
    logger.info(f"Iniciando navegador interativo (headed) para login manual na URL: {platform_url}")
    with sync_playwright() as p:
        # Lança Chromium visível (headless=False)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            page.goto(platform_url, timeout=60000)
            logger.info("Por favor, faça o login manualmente na janela do navegador.")
            print("\n" + "="*80)
            print("INSTRUÇÕES:")
            print("1. Realize o login no navegador que foi aberto.")
            print("2. Assim que o login for concluído e você entrar no painel/dashboard,")
            print("   o script irá detectar automaticamente e salvar a sessão.")
            print("="*80 + "\n")

            # Aguardar até que a URL mude para a área logada (exclui URLs de login e autenticação)
            logged_in = False
            for _ in range(180): # Limite de 3 minutos
                try:
                    current_url = page.url
                    if current_url != "about:blank" and "login" not in current_url and "keycloak" not in current_url and "auth" not in current_url:
                        logger.info(f"Detectada mudança de página para: {current_url}")
                        logger.info("Aguardando 5 segundos para consolidação dos cookies...")
                        page.wait_for_timeout(5000)
                        
                        # Salva o estado da sessão para reuso futuro
                        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                        context.storage_state(path=str(STATE_PATH))
                        logger.info(f"Sessão salva com sucesso em: {STATE_PATH}")
                        logged_in = True
                        break
                except Exception as e:
                    logger.debug(f"Erro ao checar URL: {e}")
                page.wait_for_timeout(1000)

            if not logged_in:
                logger.error("Tempo limite esgotado. O login não foi concluído.")
                return False
            return True

        except Exception as e:
            logger.exception(f"Erro durante o login interativo: {e}")
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Autenticação na plataforma de pós-graduação.")
    parser.add_argument("--force", action="store_true", help="Forçar nova autenticação e ignorar cache.")
    args = parser.parse_args()
    
    success = login(force=args.force)
    sys.exit(0 if success else 1)
