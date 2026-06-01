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
    report_data = []

    print("Iniciando auditoria profunda...")

    for mod_idx, mod in enumerate(modules):
        m_title = mod.get("modulo", "")
        mod_clean_raw = re.sub(r'[^a-zA-Z0-9\s_-]', '', m_title or "").strip()
        mod_clean_md = clean_filename(m_title)
        
        aulas = mod.get("aulas", [])
        for lesson_idx, lesson in enumerate(aulas):
            total_lessons += 1
            lesson_title = lesson.get("titulo", "")
            lesson_slug = lesson.get("slug", "")
            subpasta = lesson.get("subpasta", "")
            is_external = lesson.get("is_external", False)
            
            # Localizar caminhos dos arquivos de dados
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
                obsidian_dir = vault_path / course_name_env / mod_clean_md / subpasta_clean
            else:
                obsidian_dir = vault_path / course_name_env / mod_clean_md
            obsidian_file = obsidian_dir / f"{aula_clean}.md"

            # Dicionário de auditoria da aula
            audit = {
                "modulo": m_title,
                "aula": lesson_title,
                "is_external": is_external,
                # Status de arquivos locais
                "raw_json_exists": raw_file.exists(),
                "processed_json_exists": processed_file.exists(),
                "obsidian_md_exists": obsidian_file.exists(),
                # Conteúdo no Obsidian
                "obsidian_has_original_summary": "N/A",
                "obsidian_has_transcription": "N/A",
                "obsidian_has_ai_summary": "N/A",
                "simple_mode_only": False,
                # Detalhes de anexos
                "attachments_status": [], # Lista de dicionários com status de cada anexo
                "errors": []
            }

            # 1. Analisar JSON bruto
            raw_data = {}
            if audit["raw_json_exists"]:
                try:
                    with open(raw_file, "r", encoding="utf-8") as rf:
                        raw_data = json.load(rf)
                        audit["is_external"] = raw_data.get("is_external", False)
                except Exception as e:
                    audit["errors"].append(f"Erro ao ler JSON bruto: {e}")
            else:
                audit["errors"].append("JSON bruto ausente localmente.")

            # 2. Analisar JSON processado (IA)
            processed_data = {}
            if audit["processed_json_exists"]:
                try:
                    with open(processed_file, "r", encoding="utf-8") as pf:
                        processed_data = json.load(pf)
                except Exception as e:
                    audit["errors"].append(f"Erro ao ler JSON processado da IA: {e}")

            # 3. Analisar Nota no Obsidian
            if audit["obsidian_md_exists"]:
                try:
                    with open(obsidian_file, "r", encoding="utf-8") as of:
                        md_content = of.read()
                        
                        # Verificar se está em modo simples
                        if "Nota gerada em modo simples (sem enriquecimento de IA)" in md_content:
                            audit["simple_mode_only"] = True

                        # Verificar se contém o resumo da plataforma
                        # Geralmente fica abaixo de "# Resumo da aula na plataforma"
                        resumo_plat_header = "# Resumo da aula na plataforma"
                        if resumo_plat_header in md_content:
                            pos = md_content.find(resumo_plat_header) + len(resumo_plat_header)
                            # Pega o texto abaixo até o próximo cabeçalho principal
                            text_after = md_content[pos:].split("#")[0].strip()
                            if text_after and "Sem resumo na plataforma." not in text_after:
                                audit["obsidian_has_original_summary"] = "OK"
                            else:
                                audit["obsidian_has_original_summary"] = "Vazio"
                        else:
                            audit["obsidian_has_original_summary"] = "Seção Ausente"

                        # Verificar se contém transcrição
                        transcricao_header = "# Transcrição completa da aula"
                        if transcricao_header in md_content:
                            pos = md_content.find(transcricao_header) + len(transcricao_header)
                            text_after = md_content[pos:].split("#")[0].strip()
                            if text_after:
                                audit["obsidian_has_transcription"] = "OK"
                            else:
                                audit["obsidian_has_transcription"] = "Vazia"
                        else:
                            audit["obsidian_has_transcription"] = "Seção Ausente"

                        # Verificar se contém resumo de IA
                        ai_summary_header = "## Resumo Executivo"
                        if ai_summary_header in md_content:
                            pos = md_content.find(ai_summary_header) + len(ai_summary_header)
                            text_after = md_content[pos:].split("##")[0].strip()
                            if text_after and "Resumo não disponível." not in text_after and "Resumo não executivo disponível." not in text_after:
                                audit["obsidian_has_ai_summary"] = "OK"
                            else:
                                audit["obsidian_has_ai_summary"] = "Vazio"
                        else:
                            # Se for externa, pode não requerer IA se configurado, mas no fluxo padrão todas as internas requerem
                            if audit["simple_mode_only"]:
                                audit["obsidian_has_ai_summary"] = "Pendente (Modo Simples)"
                            else:
                                audit["obsidian_has_ai_summary"] = "Seção Ausente"

                except Exception as e:
                    audit["errors"].append(f"Erro ao ler nota do Obsidian: {e}")
                    audit["obsidian_has_original_summary"] = "Erro"
                    audit["obsidian_has_transcription"] = "Erro"
                    audit["obsidian_has_ai_summary"] = "Erro"
            else:
                audit["obsidian_has_original_summary"] = "Ausente"
                audit["obsidian_has_transcription"] = "Ausente"
                audit["obsidian_has_ai_summary"] = "Ausente"
                audit["errors"].append("Nota Markdown ausente no Obsidian.")

            # 4. Analisar Anexos (materiais_apoio)
            materiais = raw_data.get("materiais_apoio", [])
            for mat in materiais:
                titulo = mat.get("titulo", "Material")
                local_path = mat.get("arquivo_local")
                baixado = mat.get("baixado", False)
                artefatos = mat.get("artefatos_locais", [])

                candidates = []
                if local_path and baixado:
                    candidates.append(local_path)
                for art in artefatos:
                    candidates.append(art)

                for cand in candidates:
                    cand_path = Path(cand)
                    filename = cand_path.name
                    
                    project_file_exists = (PROJECT_ROOT / cand_path).exists()
                    obsidian_att_exists = (obsidian_dir / "attachments" / filename).exists()
                    
                    # Verificar se está linkado no Markdown do Obsidian
                    referenced_in_md = False
                    if audit["obsidian_md_exists"]:
                        try:
                            with open(obsidian_file, "r", encoding="utf-8") as of:
                                md_content = of.read()
                                referenced_in_md = f"[[attachments/{filename}" in md_content or f"attachments/{filename}" in md_content
                        except:
                            pass

                    mat_status = {
                        "titulo": titulo,
                        "arquivo": filename,
                        "existe_no_projeto": project_file_exists,
                        "existe_no_obsidian": obsidian_att_exists,
                        "linkado_no_obsidian": referenced_in_md
                    }
                    audit["attachments_status"].append(mat_status)
                    
                    # Se houver inconsistência nos anexos, registra erro
                    if not project_file_exists:
                        audit["errors"].append(f"Anexo local '{filename}' não encontrado na pasta do projeto.")
                    if not obsidian_att_exists:
                        audit["errors"].append(f"Anexo '{filename}' não copiado para a pasta attachments do Obsidian.")
                    if audit["obsidian_md_exists"] and not referenced_in_md:
                        audit["errors"].append(f"Anexo '{filename}' existe mas não está linkado na nota do Obsidian.")

            report_data.append(audit)

    # 5. Gerar Relatório Markdown
    report_file = PROJECT_ROOT / "scratch" / "audit_report.md"
    
    total_ok = 0
    total_missing_note = 0
    total_simple_mode = 0
    total_missing_fields = 0
    total_attachment_errors = 0
    
    # Detalhar itens com problemas
    issues_lines = []
    
    for item in report_data:
        has_issue = False
        issue_desc = []
        
        if not item["obsidian_md_exists"]:
            total_missing_note += 1
            has_issue = True
            issue_desc.append("- Nota Markdown não foi criada no Obsidian.")
        else:
            if item["simple_mode_only"]:
                total_simple_mode += 1
                # Modo simples não é necessariamente um "erro" fatal, mas é incompleto (sem IA)
                issue_desc.append("- Nota gerada em **Modo Simples** (sem enriquecimento de IA).")
            else:
                if item["obsidian_has_ai_summary"] != "OK":
                    total_missing_fields += 1
                    has_issue = True
                    issue_desc.append(f"- Resumo Executivo da IA está: `{item['obsidian_has_ai_summary']}`")
            
            if not item["is_external"] and item["obsidian_has_transcription"] != "OK":
                total_missing_fields += 1
                has_issue = True
                issue_desc.append(f"- Transcrição da aula está: `{item['obsidian_has_transcription']}`")
                
            if item["obsidian_has_original_summary"] != "OK" and not item["is_external"]:
                # Se não tem resumo da plataforma, mas tem transcrição e IA tá ok, é um aviso secundário
                issue_desc.append(f"- Resumo original da plataforma está: `{item['obsidian_has_original_summary']}`")

        # Verificar anexos
        att_errors = []
        for att in item["attachments_status"]:
            if not att["existe_no_obsidian"]:
                att_errors.append(f"Anexo `{att['arquivo']}` ausente no Obsidian.")
            if not att["linkado_no_obsidian"] and item["obsidian_md_exists"]:
                att_errors.append(f"Anexo `{att['arquivo']}` não está linkado na nota.")
                
        if att_errors:
            total_attachment_errors += 1
            has_issue = True
            for ae in att_errors:
                issue_desc.append(f"- Anexo: {ae}")

        if not has_issue and not item["simple_mode_only"]:
            total_ok += 1
        else:
            # Adicionar ao relatório detalhado
            issues_lines.append(f"### Aula: {item['aula']}")
            issues_lines.append(f"**Módulo**: {item['modulo']} | **Tipo**: {'Externa' if item['is_external'] else 'Interna'}")
            issues_lines.append("\n".join(issue_desc))
            issues_lines.append("")

    # Escrever no arquivo
    with open(report_file, "w", encoding="utf-8") as f_rep:
        f_rep.write(f"# Relatório de Auditoria Profunda do Obsidian\n\n")
        f_rep.write(f"Este relatório foi gerado automaticamente para auditar a sincronização e integridade das notas do curso no Obsidian.\n\n")
        
        f_rep.write(f"## Resumo Geral\n")
        f_rep.write(f"- **Total de Aulas Mapeadas**: {total_lessons}\n")
        f_rep.write(f"- **Aulas 100% Completas (IA + Transcrição + Anexos Ok)**: {total_ok}\n")
        f_rep.write(f"- **Aulas em Modo Simples (Sem IA)**: {total_simple_mode}\n")
        f_rep.write(f"- **Notas Faltando no Obsidian**: {total_missing_note}\n")
        f_rep.write(f"- **Notas com Campos Faltantes (Sem Transcrição ou Sem IA)**: {total_missing_fields}\n")
        f_rep.write(f"- **Notas com Inconsistência nos Anexos**: {total_attachment_errors}\n\n")
        
        f_rep.write(f"## Detalhes das Aulas com Pendências ou Inconsistências\n\n")
        if issues_lines:
            f_rep.write("\n".join(issues_lines))
        else:
            f_rep.write("🎉 Nenhuma pendência ou inconsistência encontrada! Todas as aulas estão 100% sincronizadas e completas.")

    print(f"\n==========================================")
    print(f"AUDITORIA CONCLUÍDA")
    print(f"==========================================")
    print(f"Total de Aulas Mapeadas: {total_lessons}")
    print(f"Aulas Completas (Enriquecidas por IA): {total_ok}")
    print(f"Aulas em Modo Simples (Sem IA): {total_simple_mode}")
    print(f"Notas Faltando no Obsidian: {total_missing_note}")
    print(f"Inconsistências em Transcrições/Resumos: {total_missing_fields}")
    print(f"Inconsistências em Anexos/Materiais: {total_attachment_errors}")
    print(f"==========================================")
    print(f"Relatório detalhado gerado em: scratch/audit_report.md")
    print(f"==========================================\n")

if __name__ == "__main__":
    main()
