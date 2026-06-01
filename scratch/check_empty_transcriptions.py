import os
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

def main():
    raw_files = list(RAW_DIR.glob("**/*.json"))
    raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]
    
    empty_transcriptions = []
    
    from urllib.parse import urlparse
    for rf in raw_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            url = data.get("url", "")
            is_external = "plataforma.fullcycle.com.br" not in urlparse(url).netloc.lower() if url else False
            lesson_title = data.get("aula", "")
            transcricao = data.get("transcricao", "").strip()
            
            if is_external:
                continue
                
            if not transcricao:
                title_lower = lesson_title.lower()
                # Marcar se parece ser aula de leitura/links/slides/código fonte
                is_text_only = any(keyword in title_lower for keyword in ["material", "slides", "código fonte", "codigo-fonte", "código-fonte", "templates", "guidelines", "github", "desafio"])
                
                empty_transcriptions.append({
                    "file_path": rf.relative_to(PROJECT_ROOT).as_posix(),
                    "modulo": data.get("modulo", ""),
                    "aula": lesson_title,
                    "url": data.get("url", ""),
                    "is_text_only": is_text_only
                })
        except Exception as e:
            print(f"Erro ao ler {rf.name}: {e}")
            
    print(f"\n==========================================")
    print(f"AULAS SEM TRANSCRIÇÃO")
    print(f"==========================================")
    print(f"Total de JSONs analisados: {len(raw_files)}")
    
    regular_lessons = [t for t in empty_transcriptions if not t["is_text_only"]]
    text_only = [t for t in empty_transcriptions if t["is_text_only"]]
    
    print(f"Aulas regulares (vídeos) sem transcrição: {len(regular_lessons)}")
    print(f"Aulas de materiais/slides sem transcrição: {len(text_only)}")
    print(f"==========================================\n")
    
    if regular_lessons:
        print("❌ AULAS REGULARES SEM TRANSCRIÇÃO:")
        for item in regular_lessons:
            print(f" - [{item['modulo']}] {item['aula']}")
            print(f"   Path: {item['file_path']}")
            print(f"   URL: {item['url']}")
        print()
        
    if text_only:
        print("ℹ️ MATERIAIS/SLIDES SEM TRANSCRIÇÃO (Normalmente esperado ser vazio):")
        for item in text_only:
            print(f" - [{item['modulo']}] {item['aula']}")
        print()

if __name__ == "__main__":
    main()
