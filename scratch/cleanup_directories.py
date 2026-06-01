import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

def merge_folders(src_dir: Path, dest_dir: Path):
    if not src_dir.exists():
        return
    
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    for item in src_dir.iterdir():
        dest_item = dest_dir / item.name
        if item.is_dir():
            merge_folders(item, dest_item)
        else:
            # Se já existir o arquivo no destino, manter o que for maior (geralmente contém mais dados extraídos)
            if dest_item.exists():
                src_size = item.stat().st_size
                dest_size = dest_item.stat().st_size
                if src_size > dest_size:
                    print(f"Substituindo {dest_item} por arquivo maior de {src_dir}")
                    shutil.copy2(item, dest_item)
                else:
                    print(f"Mantendo {dest_item} (destino é maior ou igual: {dest_size} >= {src_size})")
            else:
                print(f"Movendo {item.name} para {dest_dir}")
                shutil.copy2(item, dest_item)

def main():
    course_dir = RAW_DIR / "Desenvolvimento de aplicaes com IA"
    
    if not course_dir.exists():
        print("Diretório do curso não encontrado.")
        return
        
    # 1. Mesclar Introduo -> Introdução
    intro_src = course_dir / "01 - Introduo"
    intro_dest = course_dir / "01 - Introdução"
    print(f"Mesclando {intro_src.name} -> {intro_dest.name}...")
    merge_folders(intro_src, intro_dest)
    
    # 2. Mesclar Projeto prtico -> Projeto prático
    proj_src = course_dir / "07 - Projeto prtico - Workflow base - Fundamentos"
    proj_dest = course_dir / "07 - Projeto prático - Workflow base - Fundamentos"
    print(f"Mesclando {proj_src.name} -> {proj_dest.name}...")
    merge_folders(proj_src, proj_dest)
    
    # 3. Remover diretórios antigos se vazios
    for src in [intro_src, proj_src]:
        if src.exists():
            try:
                shutil.rmtree(src)
                print(f"Diretório antigo {src.name} removido com sucesso.")
            except Exception as e:
                print(f"Erro ao remover {src.name}: {e}")

if __name__ == "__main__":
    main()
