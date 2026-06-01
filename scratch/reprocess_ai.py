import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from pipeline.ai_summarizer import process_lesson_ai
from pipeline.generate_markdown import generate_obsidian_markdown

files = [
    "data/raw/Desenvolvimento de aplicaes com IA/08 - Projeto prático - Workflow base - Implementação/introducao-ao-workflow-de-desenvolvimento.json",
    "data/raw/Fundamentos de IA Generativa/03 - Gen IA/introducao-as-diferencas-de-ia.json",
    "data/raw/Fundamentos de IA Generativa/03 - Gen IA/o-que-e-gen-ai.json",
    "data/raw/Fundamentos de IA Generativa/02 - Introdução/nosso-momento.json",
    "data/raw/Fundamentos de IA Generativa/02 - Introdução/introducao.json"
]

def main():
    print(f"Reprocessando as {len(files)} aulas atualizadas com IA...")
    for idx, f in enumerate(files, start=1):
        path = PROJECT_ROOT / f
        if path.exists():
            print(f"[{idx}/{len(files)}] Processando IA para: {path.name}...")
            success = process_lesson_ai(path, force=True)
            if success:
                print("  -> IA concluída. Regerando nota no Obsidian...")
                generate_obsidian_markdown(path, force=True)
                print("  -> Nota regerada com sucesso.")
            else:
                print("  -> Erro ao processar com IA.")
        else:
            print(f"[{idx}/{len(files)}] ⚠️ Arquivo não encontrado: {f}")

if __name__ == "__main__":
    main()
