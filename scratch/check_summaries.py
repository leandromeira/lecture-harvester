import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis do .env
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
INDEX_PATH = RAW_DIR / "course_index.json"

def clean_slug(text):
    text = text.lower()
    text = re.sub(r'[áàâãä]', 'a', text)
    text = re.sub(r'[éèêë]', 'e', text)
    text = re.sub(r'[íìîï]', 'i', text)
    text = re.sub(r'[óòôõö]', 'o', text)
    text = re.sub(r'[úùûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text.strip('-')

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def main():
    if not INDEX_PATH.exists():
        print(f"Erro: O arquivo de índice do curso não foi encontrado em: {INDEX_PATH}")
        sys.exit(1)

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        course_index = json.load(f)

    course_name_env = os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH", "/Users/leandromeira/Obsidian")
    vault_path = Path(vault_path_str)

    modules = course_index.get("modulos", [])
    
    total_lessons = 0
    not_extracted = []
    extracted_no_ai = []
    extracted_ai_incomplete = []
    ready = []
    
    print(f"Total de módulos encontrados no índice: {len(modules)}")
    
    for mod_idx, mod in enumerate(modules):
        m_title = mod.get("modulo", "")
        print(f"Processando módulo [{mod_idx + 1}/{len(modules)}]: {m_title}")
        # Como o crawl_course cria a pasta do módulo bruto:
        mod_clean_raw = re.sub(r'[^a-zA-Z0-9\s_-]', '', m_title or "").strip()
        # Como o generate_markdown cria a pasta do módulo no Obsidian:
        mod_clean_md = clean_filename(m_title)
        
        aulas = mod.get("aulas", [])
        for lesson_idx, lesson in enumerate(aulas):
            total_lessons += 1
            lesson_title = lesson.get("titulo", "")
            lesson_slug = lesson.get("slug", "")
            subpasta = lesson.get("subpasta", "")
            
            # Localizar caminho do JSON bruto
            if subpasta:
                subpasta_clean = clean_filename(subpasta)
                raw_file = RAW_DIR / mod_clean_raw / subpasta_clean / f"{lesson_slug}.json"
                processed_file = PROCESSED_DIR / mod_clean_raw / subpasta_clean / f"{lesson_slug}.json"
            else:
                raw_file = RAW_DIR / mod_clean_raw / f"{lesson_slug}.json"
                processed_file = PROCESSED_DIR / mod_clean_raw / f"{lesson_slug}.json"
                
            # Localizar caminho no Obsidian
            aula_clean = clean_filename(lesson_title)
            if subpasta:
                obsidian_file = vault_path / course_name_env / mod_clean_md / subpasta_clean / f"{aula_clean}.md"
            else:
                obsidian_file = vault_path / course_name_env / mod_clean_md / f"{aula_clean}.md"

            print(f"  -> Aula [{lesson_idx + 1}/{len(aulas)}]: {lesson_title}")
            print(f"     Verificando raw_file: {raw_file.name} ...")
            raw_exists = raw_file.exists()
            print(f"     Verificando processed_file: {processed_file.name} ...")
            processed_exists = processed_file.exists()
            print(f"     Verificando obsidian_file: {obsidian_file.name} ...")
            try:
                # Usar um timeout rápido ou tratar se demorar
                obsidian_exists = obsidian_file.exists()
            except Exception as e:
                print(f"     Erro ao verificar obsidian_file: {e}")
                obsidian_exists = False

            status = {
                "modulo": m_title,
                "aula": lesson_title,
                "slug": lesson_slug,
                "raw_exists": raw_exists,
                "processed_exists": processed_exists,
                "obsidian_exists": obsidian_exists,
                "has_raw_transcript": False,
                "has_raw_summary": False,
                "has_ai_summary": False,
                "is_external": lesson.get("is_external", False),
                "ai_summary_status": "Pendente",
                "obsidian_status": "Pendente"
            }

            if status["raw_exists"]:
                try:
                    with open(raw_file, "r", encoding="utf-8") as rf:
                        raw_data = json.load(rf)
                        status["has_raw_transcript"] = bool(raw_data.get("transcricao", "").strip())
                        status["has_raw_summary"] = bool(raw_data.get("resumo_original", "").strip())
                        status["is_external"] = raw_data.get("is_external", False)
                except Exception as e:
                    print(f"     Erro ao ler raw_file: {e}")

            if status["processed_exists"]:
                try:
                    with open(processed_file, "r", encoding="utf-8") as pf:
                        processed_data = json.load(pf)
                        resumo_exec = processed_data.get("resumo_executivo", "")
                        if resumo_exec and resumo_exec != "Não gerado." and resumo_exec != "Resumo não disponível.":
                            status["has_ai_summary"] = True
                            status["ai_summary_status"] = "OK"
                        else:
                            status["ai_summary_status"] = "Vazio/Incompleto"
                except Exception as e:
                    status["ai_summary_status"] = "Erro ao ler"
            else:
                status["ai_summary_status"] = "Ausente"

            if status["obsidian_exists"]:
                try:
                    with open(obsidian_file, "r", encoding="utf-8") as of:
                        content = of.read()
                        if "Nota gerada em modo simples (sem enriquecimento de IA)" in content:
                            status["obsidian_status"] = "Simples (Sem IA)"
                        elif "Resumo não disponível." in content or "Resumo não executivo disponível." in content:
                            status["obsidian_status"] = "Sem Resumo"
                        else:
                            status["obsidian_status"] = "Enriquecido"
                except Exception as e:
                    status["obsidian_status"] = "Erro ao ler"
            else:
                status["obsidian_status"] = "Não criado"

            # Classificação
            if not status["raw_exists"]:
                not_extracted.append(status)
            elif not status["processed_exists"]:
                extracted_no_ai.append(status)
            elif not status["has_ai_summary"]:
                extracted_ai_incomplete.append(status)
            else:
                ready.append(status)

    print(f"\n==========================================")
    print(f"RELATÓRIO DE CONFERÊNCIA DE AULAS & RESUMOS")
    print(f"==========================================")
    print(f"Total de aulas indexadas: {total_lessons}")
    print(f"Aulas Prontas (IA Ok + Markdown Ok): {len(ready)}")
    print(f"Aulas Não Extraídas (Sem JSON bruto): {len(not_extracted)}")
    print(f"Aulas Extraídas mas Sem Processamento de IA: {len(extracted_no_ai)}")
    print(f"Aulas com IA Processada mas Sem Resumo Válido: {len(extracted_ai_incomplete)}")
    print(f"==========================================\n")

    if not_extracted:
        print("❌ AULAS NÃO EXTRAÍDAS:")
        for item in not_extracted:
            ext_label = " (Externa)" if item["is_external"] else ""
            print(f" - [{item['modulo']}] {item['aula']}{ext_label}")
        print()

    if extracted_no_ai:
        print("⚠️ AULAS EXTRAÍDAS MAS SEM PROCESSAMENTO DE IA (Falta rodar main.py process --all):")
        for item in extracted_no_ai:
            print(f" - [{item['modulo']}] {item['aula']} (Obsidian: {item['obsidian_status']})")
        print()

    if extracted_ai_incomplete:
        print("🔍 AULAS COM IA PROCESSADA MAS SEM RESUMO VÁLIDO (Podem precisar de reprocessamento):")
        for item in extracted_ai_incomplete:
            print(f" - [{item['modulo']}] {item['aula']} (Status IA: {item['ai_summary_status']} | Obsidian: {item['obsidian_status']})")
        print()

if __name__ == "__main__":
    main()
