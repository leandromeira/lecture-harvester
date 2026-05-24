import os
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_processing_logger

logger = setup_processing_logger()

# Configurações carregadas via variáveis de ambiente (.env)

def extract_number(text):
    """Extrai o primeiro número de uma string para ordenação correta."""
    match = re.search(r'\d+', text)
    return int(match.group()) if match else 9999

def generate_indexes():
    """
    Varre o vault do Obsidian na pasta do curso e gera arquivos de índices:
    1. Um índice para cada módulo (salvo dentro da pasta do módulo).
    2. Um índice geral do curso (salvo no root do curso).
    """
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH", "/Users/leandromeira/Obsidian")
    vault_path = Path(vault_path_str)
    course_name = os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    
    course_dir = vault_path / course_name
    if not course_dir.exists():
        logger.warning(f"Diretório do curso no vault não existe: {course_dir}. Não há o que indexar.")
        return False

    logger.info("Iniciando geração de índices automáticos...")
    
    # Encontra todas as subpastas (módulos) no curso
    module_dirs = sorted([d for d in course_dir.iterdir() if d.is_dir() and not d.name.startswith(".")])
    
    global_index_lines = [f"# {course_name} — Índice Geral\n"]

    for m_dir in module_dirs:
        modulo_name = m_dir.name
        
        # Encontra todos os arquivos markdown na pasta do módulo, exceto outros índices
        lesson_files = []
        for f in m_dir.glob("*.md"):
            if f.name.startswith("00 -") or f.name.startswith("_"):
                continue
            lesson_files.append(f)
            
        # Ordena as aulas com base no número (ex: Aula 01 antes de Aula 10)
        lesson_files.sort(key=lambda x: extract_number(x.stem))
        
        # Gera o conteúdo do índice do módulo
        module_index_name = f"00 - Índice - {modulo_name}"
        module_index_file = m_dir / f"{module_index_name}.md"
        
        index_content = f"# {modulo_name}\n\n"
        for lf in lesson_files:
            # Obsidian wikilink: [[Nome do Arquivo]] (sem extensão)
            index_content += f"- [[{lf.stem}]]\n"
            
        try:
            with open(module_index_file, "w", encoding="utf-8") as f:
                f.write(index_content)
            logger.info(f"Índice do módulo '{modulo_name}' gerado com sucesso!")
            
            # Adiciona linha no índice geral (apontando para o índice do módulo)
            global_index_lines.append(f"## [[{module_index_name}|{modulo_name}]]")
            for lf in lesson_files:
                global_index_lines.append(f"- [[{lf.stem}]]")
            global_index_lines.append("") # Quebra de linha
            
        except Exception as e:
            logger.error(f"Erro ao salvar índice do módulo {modulo_name}: {e}")

    # Salva o índice geral
    global_index_file = course_dir / "00 - Índice Geral.md"
    try:
        with open(global_index_file, "w", encoding="utf-8") as f:
            f.write("\n".join(global_index_lines))
        logger.info(f"Índice geral do curso gerado com sucesso em: {global_index_file}")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar índice geral do curso: {e}")
        return False

if __name__ == "__main__":
    generate_indexes()
