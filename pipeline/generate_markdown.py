import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_processing_logger

logger = setup_processing_logger()

# Configurações carregadas via variáveis de ambiente (.env)

def clean_filename(name):
    """Remove caracteres inválidos para nomes de arquivos e diretórios."""
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def build_markdown_content(raw_data: dict, processed_data: dict = None) -> str:
    """Monta a estrutura de markdown para o Obsidian conforme o template."""
    aula_titulo = raw_data.get("aula", "Sem Título")
    resumo_original = raw_data.get("resumo_original", "Sem resumo na plataforma.")
    transcricao = raw_data.get("transcricao", "")
    
    # Se não houver dados enriquecidos por IA (Fase 2)
    if not processed_data:
        md = f"""# Aula — {aula_titulo}

> [!NOTE]
> Nota gerada em modo simples (sem enriquecimento de IA).

# Resumo da aula na plataforma
{resumo_original}

# Transcrição completa da aula
{transcricao}
"""
        return md

    # Caso tenhamos dados enriquecidos (Fase 3)
    # Formatação dos conceitos
    conceitos_md = ""
    for c in processed_data.get("conceitos", []):
        termo = c.get("termo", "")
        definicao = c.get("definicao", "")
        conceitos_md += f"- **{termo}**: {definicao}\n"
    if not conceitos_md:
        conceitos_md = "- *Nenhum conceito principal identificado.*\n"

    # Formatação dos pontos importantes
    pontos_md = ""
    for p in processed_data.get("pontos_importantes", []):
        pontos_md += f"- {p}\n"
    if not pontos_md:
        pontos_md = "- *Nenhum ponto importante listado.*\n"

    # Formatação dos exemplos
    exemplos_md = ""
    for ex in processed_data.get("exemplos_citados", []):
        exemplos_md += f"- {ex}\n"
    if not exemplos_md:
        exemplos_md = "- *Nenhum exemplo citado.*\n"

    # Formatação das perguntas de revisão
    perguntas_md = ""
    for i, p in enumerate(processed_data.get("perguntas_revisao", []), 1):
        perguntas_md += f"{i}. {p}\n"
    if not perguntas_md:
        perguntas_md = "*Nenhuma pergunta de revisão gerada.*\n"

    # Formatação dos flashcards
    flashcards_md = ""
    for fc in processed_data.get("flashcards", []):
        q = fc.get("pergunta", "")
        a = fc.get("resposta", "")
        flashcards_md += f"### Pergunta\n{q}\n\n### Resposta\n{a}\n\n"
    if not flashcards_md:
        flashcards_md = "*Nenhum flashcard gerado.*\n"

    # Relações com outras aulas (wikilinks Obsidian)
    relacoes_md = ""
    for r in processed_data.get("relacoes", []):
        relacoes_md += f"- [[{r}]]\n"
    if not relacoes_md:
        relacoes_md = "- *Sem relações mapeadas.*\n"

    # Formatação das tags
    tags_list = [f"#{t}" for t in processed_data.get("tags", [])]
    tags_md = " ".join(tags_list) if tags_list else "#aula"

    # Monta a string final baseada exatamente no template do usuário
    md = f"""# Aula — {aula_titulo}

## Resumo Executivo
{processed_data.get("resumo_executivo", "Resumo não disponível.")}

## Conceitos Principais
{conceitos_md}
## Explicação Simplificada
{processed_data.get("explicacao_simplificada", "Explicação simplificada não disponível.")}

## Pontos Importantes
{pontos_md}
## Exemplos Citados
{exemplos_md}
## Perguntas para Revisão
{perguntas_md}
## Flashcards
{flashcards_md}
## Relação com outras aulas
{relacoes_md}
## Tags
{tags_md}

# Resumo da aula na plataforma
{resumo_original}

# Transcrição completa da aula
{transcricao}
"""
    return md

def generate_obsidian_markdown(raw_json_path: Path, processed_json_path: Path = None, skip_ai=False) -> Path:
    """
    Lê o JSON bruto (e o JSON processado de IA se não for skip_ai e existir) e gera o arquivo
    Markdown dentro do Vault do Obsidian definido nas configurações.
    """
    if not raw_json_path.exists():
        logger.error(f"Arquivo JSON bruto não encontrado em: {raw_json_path}")
        return None

    # Carrega dados brutos
    with open(raw_json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # Tenta carregar dados processados pela IA se não ignorarmos a IA e o arquivo existir
    processed_data = None
    if not skip_ai:
        if processed_json_path and processed_json_path.exists():
            try:
                with open(processed_json_path, "r", encoding="utf-8") as f:
                    processed_data = json.load(f)
            except Exception as e:
                logger.error(f"Erro ao carregar JSON processado da IA: {e}")
        else:
            # Se não passado explicitamente, tenta localizar no caminho padrão
            default_processed_path = Path(__file__).resolve().parents[1] / "data" / "processed" / raw_json_path.relative_to(raw_json_path.parents[1])
            if default_processed_path.exists():
                try:
                    with open(default_processed_path, "r", encoding="utf-8") as f:
                        processed_data = json.load(f)
                except Exception as e:
                    logger.error(f"Erro ao carregar JSON processado da IA por padrão: {e}")

    # Definir caminhos no Obsidian
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH", "/Users/leandromeira/Obsidian")
    vault_path = Path(vault_path_str)
    course_name = os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    
    modulo_original = raw_data.get("modulo", "Geral")
    # Limpa nomes para pasta
    modulo_clean = clean_filename(modulo_original)
    
    # Nome do arquivo da aula no Obsidian (ex: Aula 03 - Prompt Engineering.md)
    aula_titulo = raw_data.get("aula", "Sem Título")
    aula_clean = clean_filename(aula_titulo)
    
    obsidian_dir = vault_path / course_name / modulo_clean
    obsidian_file_path = obsidian_dir / f"{aula_clean}.md"

    # Constrói o conteúdo em Markdown
    markdown_content = build_markdown_content(raw_data, processed_data)

    try:
        # Cria diretórios no Vault do Obsidian
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        
        # Salva o arquivo no vault do Obsidian
        with open(obsidian_file_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        
        # Salva também um cache local de Markdown para segurança
        local_md_dir = Path(__file__).resolve().parents[1] / "data" / "markdown" / modulo_clean
        local_md_dir.mkdir(parents=True, exist_ok=True)
        with open(local_md_dir / f"{aula_clean}.md", "w", encoding="utf-8") as f:
            f.write(markdown_content)

        logger.info(f"Markdown gerado e salvo com sucesso no Obsidian: {obsidian_file_path}")
        return obsidian_file_path
    except Exception as e:
        logger.exception(f"Erro ao salvar arquivo Markdown no vault do Obsidian: {e}")
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gera arquivo markdown para o Obsidian a partir dos caches locais.")
    parser.add_argument("raw_path", type=str, help="Caminho para o JSON bruto da aula.")
    parser.add_argument("--processed_path", type=str, default=None, help="Caminho opcional do JSON processado de IA.")
    args = parser.parse_args()

    generate_obsidian_markdown(Path(args.raw_path), Path(args.processed_path) if args.processed_path else None)
