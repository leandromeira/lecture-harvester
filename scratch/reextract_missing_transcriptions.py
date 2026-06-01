import os
import sys
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
STATE_PATH = PROJECT_ROOT / "config" / "storage_state.json"

sys.path.append(str(PROJECT_ROOT))
from pipeline.generate_markdown import generate_obsidian_markdown

def extract_content(page, url, need_summary, need_transcription):
    """Navega para a URL da aula e extrai resumo e/ou transcrição."""
    resumo_original = ""
    transcricao = ""
    
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # 1. Extração do resumo se necessário
        if need_summary:
            print("  -> Extraindo resumo original...")
            for attempt in range(1, 6):
                resumo_elms = page.query_selector_all(".MuiTypography-h5 p, .MuiTypography-h5 h2")
                resumo_texts = []
                for el in resumo_elms:
                    txt = el.inner_text().strip()
                    if txt and txt not in resumo_texts:
                        resumo_texts.append(txt)
                
                if not resumo_texts:
                    fallback_elms = page.query_selector_all(".MuiTypography-h5")
                    for el in fallback_elms:
                        txt = el.inner_text().strip()
                        if txt and txt not in resumo_texts:
                            resumo_texts.append(txt)
                
                resumo_original = "\n\n".join(resumo_texts).strip()
                if resumo_original:
                    print(f"    Resumo extraído com sucesso (tentativa {attempt}/5).")
                    break
                    
                if attempt == 2:
                    try:
                        resumo_btn = page.locator('button', has_text="Resumo da Aula")
                        if resumo_btn.is_visible():
                            resumo_btn.click()
                    except:
                        pass
                page.wait_for_timeout(1000)
                
        # 2. Extração de transcrição se necessário
        if need_transcription:
            print("  -> Extraindo transcrição...")
            for attempt in range(1, 6):
                # Tentar clicar no botão nas primeiras tentativas
                if attempt in (1, 2):
                    try:
                        trans_btn = page.locator('button', has_text="Transcrição")
                        if trans_btn.is_visible():
                            trans_btn.click(timeout=3000)
                    except Exception as e:
                        print(f"    [Aviso] Falha ao clicar na aba Transcrição: {e}")
                
                page.wait_for_timeout(1500)
                
                # Buscar elementos da transcrição
                trans_elms = page.query_selector_all("#panel-1 div > span:last-child")
                if not trans_elms:
                    trans_elms = page.query_selector_all("#panel-1 span")
                
                trans_texts = [el.inner_text().strip() for el in trans_elms]
                # Filtrar timestamps
                trans_texts = [t for t in trans_texts if t and not re.match(r'^\d{2}:\d{2}(:\d{2})?$', t)]
                
                transcricao = " ".join(trans_texts).strip()
                if transcricao:
                    print(f"    Transcrição extraída com sucesso (tentativa {attempt}/5), tamanho: {len(transcricao)} caracteres.")
                    break
                    
                page.wait_for_timeout(1000)
                
        return resumo_original, transcricao
        
    except Exception as e:
        print(f"    Erro ao acessar/interagir com a página: {e}")
        return "", ""

def main():
    if not STATE_PATH.exists():
        print("Erro: storage_state.json não encontrado. Faça login antes.")
        sys.exit(1)
        
    # As 7 aulas identificadas sem transcrição
    target_lessons = [
        {
            "path": "Desenvolvimento de aplicaes com IA/07 - Projeto prático - Workflow base - Fundamentos/dinamica-de-desenvolvimento-do-projeto-greenfield.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17643"
        },
        {
            "path": "Desenvolvimento de aplicaes com IA/07 - Projeto prático - Workflow base - Fundamentos/criando-projeto-backend-com-nestjs.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17646"
        },
        {
            "path": "Desenvolvimento de aplicaes com IA/08 - Projeto prático - Workflow base - Implementação/introducao-ao-workflow-de-desenvolvimento.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/283/conteudos?capitulo=283&conteudo=17697"
        },
        {
            "path": "Fundamentos de IA Generativa/03 - Gen IA/introducao-as-diferencas-de-ia.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16367"
        },
        {
            "path": "Fundamentos de IA Generativa/03 - Gen IA/o-que-e-gen-ai.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16366"
        },
        {
            "path": "Fundamentos de IA Generativa/02 - Introdução/nosso-momento.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16365"
        },
        {
            "path": "Fundamentos de IA Generativa/02 - Introdução/introducao.json",
            "url": "https://plataforma.fullcycle.com.br/courses/a091b0fe-a5c6-4287-a3d3-1ec61defcfd3/408/224/263/conteudos?capitulo=263&conteudo=16364"
        }
    ]
    
    print(f"Iniciando re-extração para as {len(target_lessons)} aulas sem transcrição...")
    
    success_count = 0
    updated_trans_count = 0
    updated_sum_count = 0
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        
        for idx, item in enumerate(target_lessons, start=1):
            rf_path = RAW_DIR / item["path"]
            url = item["url"]
            
            if not rf_path.exists():
                print(f"[{idx}/{len(target_lessons)}] ⚠️ Arquivo não existe no disco: {item['path']}. Pulando...")
                continue
                
            try:
                with open(rf_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as read_err:
                print(f"[{idx}/{len(target_lessons)}] ❌ Erro ao ler JSON: {read_err}. Pulando...")
                continue
                
            aula = data.get("aula", "Sem título")
            resumo_original = data.get("resumo_original", "").strip()
            transcricao = data.get("transcricao", "").strip()
            
            need_summary = not resumo_original
            need_transcription = not transcricao
            
            print(f"\n[{idx}/{len(target_lessons)}] Verificando: '{aula}'...")
            print(f"  URL: {url}")
            print(f"  Precisa de resumo: {need_summary} | Precisa de transcrição: {need_transcription}")
            
            if not need_summary and not need_transcription:
                print("  -> Nada a extrair para esta aula.")
                continue
                
            extracted_sum, extracted_trans = extract_content(page, url, need_summary, need_transcription)
            
            updated = False
            if extracted_sum:
                data["resumo_original"] = extracted_sum
                updated_sum_count += 1
                updated = True
            if extracted_trans:
                data["transcricao"] = extracted_trans
                updated_trans_count += 1
                updated = True
                
            if updated:
                # Salvar arquivo JSON atualizado
                try:
                    with open(rf_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print("  -> JSON atualizado no disco.")
                    
                    # Atualizar nota Markdown no Obsidian
                    generate_obsidian_markdown(rf_path, force=True)
                    print("  -> Nota Markdown regerada no Obsidian.")
                    success_count += 1
                except Exception as save_err:
                    print(f"  -> Erro ao salvar atualizações: {save_err}")
            else:
                print("  -> Nenhuma nova informação pôde ser extraída para esta aula.")
                
        browser.close()
        
    print(f"\n==========================================")
    print(f"RE-EXTRAÇÃO DE TRANSCRIÇÕES CONCLUÍDA")
    print(f"==========================================")
    print(f"Aulas atualizadas com sucesso: {success_count} / {len(target_lessons)}")
    print(f"Novas transcrições salvas: {updated_trans_count}")
    print(f"Novos resumos originais salvos: {updated_sum_count}")
    print(f"==========================================\n")

if __name__ == "__main__":
    main()
