import os
import re
import json
import shutil
from pathlib import Path

def migrate():
    project_root = Path(__file__).resolve().parent.parent
    raw_dir = project_root / "data" / "raw"
    processed_dir = project_root / "data" / "processed"
    index_path = raw_dir / "course_index.json"

    if not index_path.exists():
        print(f"Index not found at: {index_path}")
        return

    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)

    print("Iniciando migração de arquivos planos para capítulos estruturados...")

    migrated_raw = 0
    migrated_processed = 0
    migrated_attachments = 0

    for modulo_data in index_data.get("modulos", []):
        modulo_name = modulo_data.get("modulo")
        # Limpar o nome do módulo
        mod_clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', modulo_name or "").strip()
        
        for lesson in modulo_data.get("aulas", []):
            slug = lesson.get("slug")
            subpasta = lesson.get("subpasta")
            
            if not subpasta:
                continue
                
            sub_clean = re.sub(r'[\\/*?:"<>|]', '', subpasta).strip()
            
            # --- 1. Migrar RAW JSON ---
            old_raw_path = raw_dir / mod_clean / f"{slug}.json"
            new_raw_dir = raw_dir / mod_clean / sub_clean
            new_raw_path = new_raw_dir / f"{slug}.json"
            
            if old_raw_path.exists():
                new_raw_dir.mkdir(parents=True, exist_ok=True)
                # Atualizar metadados do JSON bruto (adicionar subpasta e título numerado)
                try:
                    with open(old_raw_path, "r", encoding="utf-8") as rf:
                        raw_content = json.load(rf)
                    raw_content["subpasta"] = subpasta
                    raw_content["aula"] = lesson.get("titulo")
                    with open(old_raw_path, "w", encoding="utf-8") as wf:
                        json.dump(raw_content, wf, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Erro ao atualizar JSON bruto {old_raw_path}: {e}")
                
                # Mover o arquivo
                shutil.move(str(old_raw_path), str(new_raw_path))
                migrated_raw += 1

            # --- 2. Migrar PROCESSED JSON ---
            old_processed_path = processed_dir / mod_clean / f"{slug}.json"
            new_processed_dir = processed_dir / mod_clean / sub_clean
            new_processed_path = new_processed_dir / f"{slug}.json"
            
            if old_processed_path.exists():
                new_processed_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_processed_path), str(new_processed_path))
                migrated_processed += 1

            # --- 3. Migrar ATTACHMENTS ---
            old_attach_dir = raw_dir / mod_clean / "attachments" / slug
            new_attach_dir = raw_dir / mod_clean / sub_clean / "attachments" / slug
            
            if old_attach_dir.exists() and old_attach_dir.is_dir():
                new_attach_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_attach_dir), str(new_attach_dir))
                migrated_attachments += 1

    print(f"Migração concluída com sucesso!")
    print(f"- JSONs brutos migrados: {migrated_raw}")
    print(f"- JSONs processados migrados: {migrated_processed}")
    print(f"- Pastas de anexos migradas: {migrated_attachments}")

    # Limpar pastas vazias de attachments da raiz antiga
    old_root_attachments = raw_dir / mod_clean / "attachments"
    if old_root_attachments.exists() and old_root_attachments.is_dir():
        try:
            # Se a pasta attachments estiver vazia, remove
            if not any(old_root_attachments.iterdir()):
                old_root_attachments.rmdir()
                print("Diretório de attachments da raiz antiga removido (estava vazio).")
        except Exception:
            pass

if __name__ == "__main__":
    migrate()
