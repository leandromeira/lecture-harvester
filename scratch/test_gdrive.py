import os
import re
import urllib.request
from urllib.parse import urlparse, parse_qs

def test_gdrive(url):
    print(f"\n--- Testando download do Google Drive: {url} ---")
    file_id = None
    
    # Extrair ID do arquivo do Google Drive
    match = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if match:
        file_id = match.group(1)
    else:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        if 'id' in q:
            file_id = q['id'][0]
            
    if not file_id:
        print("Não foi possível extrair o ID do arquivo do Google Drive.")
        return False
        
    print(f"ID do arquivo extraído: {file_id}")
    
    # URL de download direto do Google Drive
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    print(f"URL de download direto: {download_url}")
    
    try:
        # Fazer a requisição HTTP
        req = urllib.request.Request(
            download_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            headers = response.info()
            content_type = headers.get('Content-Type', '')
            content_disposition = headers.get('Content-Disposition', '')
            print(f"Status da resposta: {response.status}")
            print(f"Content-Type: {content_type}")
            print(f"Content-Disposition: {content_disposition}")
            
            # Verificar se fomos redirecionados ou se recebemos uma página HTML de confirmação
            # Se for uma página de confirmação de tamanho/vírus, o Content-Type será text/html
            body = response.read(200)
            print(f"Primeiros 200 bytes do corpo da resposta: {body[:200]}")
            
            if "text/html" in content_type.lower():
                # Tentar extrair código de confirmação se houver aviso de vírus/tamanho
                body_str = body.decode('utf-8', errors='ignore')
                confirm_match = re.search(r'confirm=([a-zA-Z0-9_-]+)', body_str)
                if confirm_match:
                    confirm_code = confirm_match.group(1)
                    confirm_download_url = f"{download_url}&confirm={confirm_code}"
                    print(f"Confirm code encontrado! Nova URL: {confirm_download_url}")
                    # Baixar de novo com confirmação
                    req_confirm = urllib.request.Request(confirm_download_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_confirm, timeout=15) as resp_conf:
                        print(f"Status com confirmação: {resp_conf.status}")
                        print(f"Content-Type com confirmação: {resp_conf.info().get('Content-Type')}")
                else:
                    print("Aviso: Recebemos HTML, o arquivo pode ser privado ou requer confirmação que não pudemos automatizar.")
            else:
                print("Sucesso! O arquivo foi retornado diretamente (provavelmente PDF/apresentação público).")
    except Exception as e:
        print(f"Erro ao baixar do Google Drive: {e}")

if __name__ == "__main__":
    test_gdrive("https://drive.google.com/file/d/1jnRiqGAAa2bXmnLlg-XWecg2GF5KSTcy/view?usp=sharing")
