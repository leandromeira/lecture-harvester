import json
from urllib.parse import urlparse
from collections import Counter
from pathlib import Path

INDEX_PATH = Path("/Users/leandromeira/Dev/lecture-harvester/data/raw/course_index.json")

def find_all_external_domains():
    if not INDEX_PATH.exists():
        print("Índice não encontrado.")
        return
        
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    external_links = []
    
    for modulo in data.get("modulos", []):
        for lesson in modulo.get("aulas", []):
            url = lesson.get("url", "")
            is_external = lesson.get("is_external", False)
            
            if is_external or ("plataforma.fullcycle" not in url and url.startswith("http")):
                external_links.append({
                    "modulo": modulo.get("modulo"),
                    "titulo": lesson.get("titulo"),
                    "url": url
                })
                
    print(f"Total de links externos encontrados no índice: {len(external_links)}")
    
    # Agrupar por domínio
    domains = []
    for link in external_links:
        parsed = urlparse(link["url"])
        domains.append(parsed.netloc.lower())
        
    counter = Counter(domains)
    print("\nDomínios mais frequentes:")
    for dom, count in counter.most_common():
        print(f"  - {dom}: {count} links")
        
    print("\nLista detalhada de links externos não-GitHub/Notion/Google Drive:")
    for link in external_links:
        parsed = urlparse(link["url"])
        dom = parsed.netloc.lower()
        if not any(x in dom for x in ("github.com", "githubusercontent.com", "notion.so", "notion.site", "drive.google.com", "google.com")):
            print(f"  Módulo: {link['modulo']}")
            print(f"    Título: {link['titulo']}")
            print(f"    URL: {link['url']}")
            print("-" * 50)

if __name__ == "__main__":
    find_all_external_domains()
