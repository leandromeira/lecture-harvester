import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

def main():
    raw_files = list(RAW_DIR.glob("**/*.json"))
    raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]
    
    missing_summaries = []
    
    for rf in raw_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            is_external = data.get("is_external", False)
            lesson_title = data.get("aula", "")
            resumo = data.get("resumo_original", "").strip()
            
            # Pular se for externo
            if is_external:
                continue
                
            # Identificar se é aula de material/slides/código fonte
            title_lower = lesson_title.lower()
            is_material = any(keyword in title_lower for keyword in ["material", "slides", "código fonte", "codigo-fonte", "código-fonte"])
            
            if not resumo:
                missing_summaries.append({
                    "file_path": rf.relative_to(PROJECT_ROOT).as_posix(),
                    "modulo": data.get("modulo", ""),
                    "aula": lesson_title,
                    "is_material": is_material
                })
        except Exception as e:
            print(f"Erro ao ler {rf.name}: {e}")
            
    print(f"\n==========================================")
    print(f"AULAS SEM RESUMO ORIGINAL DA PLATAFORMA")
    print(f"==========================================")
    print(f"Total de JSONs analisados: {len(raw_files)}")
    
    # Filtrar por não materiais
    non_materials = [m for m in missing_summaries if not m["is_material"]]
    materials = [m for m in missing_summaries if m["is_material"]]
    
    print(f"Aulas normais sem resumo: {len(non_materials)}")
    print(f"Materiais/Slides sem resumo: {len(materials)}")
    print(f"==========================================\n")
    
    if non_materials:
        print("❌ AULAS NORMAIS SEM RESUMO:")
        for item in non_materials:
            print(f" - [{item['modulo']}] {item['aula']}")
            print(f"   Caminho: {item['file_path']}")
        print()
        
    if materials:
        print("ℹ️ MATERIAIS/SLIDES SEM RESUMO (Normalmente esperado ser vazio):")
        for item in materials:
            print(f" - [{item['modulo']}] {item['aula']}")
            print(f"   Caminho: {item['file_path']}")
        print()

if __name__ == "__main__":
    main()
