import os
import sys
import json
import shutil
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))
load_dotenv()

# Pasta de dados do Harvester
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MARKDOWN_DIR = PROJECT_ROOT / "data" / "markdown"

# Mapeamento oficial dos módulos (com acentuação correta para o novo formato)
MAPPING = {
    "Fundamentos de IA Generativa": "01 - Fundamentos de IA Generativa",
    "Prompt Engineering": "02 - Prompt Engineering",
    "Design Docs com IA": "03 - Design Docs com IA",
    "Desenvolvimento de aplicações com IA": "04 - Desenvolvimento de aplicações com IA",
    "Desenvolvimento de aplicaes com IA": "04 - Desenvolvimento de aplicações com IA", # Variação sem acentos
    "Desenvolvimento em modo agente": "05 - Desenvolvimento em modo agente"
}

def clean_filename(name):
    import re
    return re.sub(r'[\\/*?:"<>|]', '', name).strip()

def migrate_json_files(directory):
    """Atualiza o campo 'modulo' dentro de todos os arquivos JSON."""
    if not directory.exists():
        return
    for rf in directory.glob("**/*.json"):
        if rf.name == "course_index.json":
            continue
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            old_mod = data.get("modulo")
            if old_mod in MAPPING:
                data["modulo"] = MAPPING[old_mod]
                with open(rf, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Atualizado JSON da aula '{rf.name}': {old_mod} -> {MAPPING[old_mod]}")
        except Exception as e:
            print(f"Erro ao processar JSON {rf}: {e}")

def rename_directories(base_dir):
    """Renomeia as pastas físicas dos módulos no cache local."""
    if not base_dir.exists():
        return
    for path in list(base_dir.iterdir()):
        if path.is_dir():
            dir_name = path.name
            if dir_name in MAPPING:
                new_name = clean_filename(MAPPING[dir_name])
                new_path = base_dir / new_name
                if new_path.exists() and new_path != path:
                    # Se a pasta destino já existe, mescla os conteúdos
                    print(f"Mesclando {path} em {new_path}...")
                    for item in path.iterdir():
                        dest = new_path / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                            shutil.rmtree(item)
                        else:
                            shutil.copy2(item, dest)
                            item.unlink()
                    path.rmdir()
                else:
                    path.rename(new_path)
                print(f"Renomeada pasta local em {base_dir.name}: {dir_name} -> {new_name}")

def main():
    print("=== INICIANDO MIGRAÇÃO DOS MÓDULOS ===")

    # 1. Atualizar o course_index.json
    index_path = RAW_DIR / "course_index.json"
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            for mod in index_data.get("modulos", []):
                old_mod = mod.get("modulo")
                if old_mod in MAPPING:
                    mod["modulo"] = MAPPING[old_mod]
                    
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
            print("course_index.json atualizado com sucesso.")
        except Exception as e:
            print(f"Erro ao atualizar course_index.json: {e}")

    # 2. Atualizar campo 'modulo' nos arquivos JSON das aulas
    print("\nAtualizando metadados dos JSONs brutos...")
    migrate_json_files(RAW_DIR)
    
    # 3. Renomear pastas no cache do projeto
    print("\nRenomeando pastas de cache local...")
    rename_directories(RAW_DIR)
    rename_directories(PROCESSED_DIR)
    rename_directories(MARKDOWN_DIR)

    # 4. Renomear pastas no vault do Obsidian
    vault_path_str = os.getenv("OBSIDIAN_VAULT_PATH")
    course_name = os.getenv("COURSE_NAME", "MBA em Engenharia de Software com IA")
    if vault_path_str:
        vault_course_dir = Path(vault_path_str) / course_name
        if vault_course_dir.exists():
            print(f"\nRenomeando pastas no vault do Obsidian: {vault_course_dir}...")
            # Renomear pastas no vault
            for path in list(vault_course_dir.iterdir()):
                if path.is_dir() and path.name != "attachments":
                    dir_name = path.name
                    if dir_name in MAPPING:
                        new_name = clean_filename(MAPPING[dir_name])
                        new_path = vault_course_dir / new_name
                        if new_path.exists() and new_path != path:
                            print(f"Mesclando pasta do vault {path} em {new_path}...")
                            for item in path.iterdir():
                                dest = new_path / item.name
                                if item.is_dir():
                                    shutil.copytree(item, dest, dirs_exist_ok=True)
                                    shutil.rmtree(item)
                                else:
                                    shutil.copy2(item, dest)
                                    item.unlink()
                            path.rmdir()
                        else:
                            path.rename(new_path)
                        print(f"Renomeada pasta no vault: {dir_name} -> {new_name}")
        else:
            print(f"\nAviso: Pasta do curso no vault '{vault_course_dir}' não encontrada.")
    else:
        print("\nAviso: OBSIDIAN_VAULT_PATH não configurado no .env.")

    print("\n=== MIGRAÇÃO CONCLUÍDA ===")

if __name__ == "__main__":
    main()
