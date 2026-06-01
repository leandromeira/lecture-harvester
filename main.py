import os
import sys
import argparse
import time
import random
from pathlib import Path
from dotenv import load_dotenv

# Carregar ambiente
load_dotenv()
sys.path.append(str(Path(__file__).resolve()))

from pipeline.logging_setup import setup_processing_logger
from scraper.login import login
from scraper.crawl_course import crawl_course
from scraper.extract_lesson import extract_lesson
from pipeline.ai_summarizer import process_lesson_ai
from pipeline.enrich_attachments import enrich_attachments_for_file, enrich_attachments_for_all
from pipeline.generate_markdown import generate_obsidian_markdown
from pipeline.generate_module_index import generate_indexes
from pipeline.reprocess_missing import reprocess_missing_content

logger = setup_processing_logger()

# Configurações carregadas via variáveis de ambiente (.env)

RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"

def run_full_pipeline(mock=False, limit=None, use_ai=False, course_id=None, skip_enrich=False, force_markdown=False):
    """
    Executa o fluxo completo do pipeline (ETL):
    1. Sincroniza o índice do curso (sync).
    2. Extrai as aulas pendentes (extract) respeitando o limite máximo definido.
    3. Enriquece os materiais de apoio se não ignorado (enrich).
    4. Enriquece com IA (process).
    5. Gera os Markdowns para Obsidian (markdown).
    6. Atualiza os índices do Obsidian (index).
    """
    logger.info(f"=== Iniciando Pipeline Completo (Mock={mock}) ===")
    
    # 1. Sync
    if mock:
        logger.info("[MOCK] Ignorando sincronização com a plataforma real.")
        # Criar dados estruturados falsos no índice se não existir
        new_lessons = [
            {
                "modulo": "Módulo 01 - Engenharia de Prompt",
                "titulo": "Aula 03 - Context Window",
                "slug": "aula-03-context-window",
                "url": "https://plataforma.exemplo.com/aulas/context-window"
            },
            {
                "modulo": "Módulo 01 - Engenharia de Prompt",
                "titulo": "Aula 04 - System Prompts",
                "slug": "aula-04-system-prompts",
                "url": "https://plataforma.exemplo.com/aulas/system-prompts"
            }
        ]
    else:
        # Tenta login automático antes de iniciar o crawl
        if not login():
            logger.error("Falha ao autenticar. Abortando pipeline.")
            return
        
        new_lessons = crawl_course(sync_mode=True, course_id=course_id)

    if not new_lessons:
        logger.info("Nenhuma aula nova detectada. Verificando se existem JSONs locais pendentes de processamento...")
    else:
        logger.info(f"Detectadas {len(new_lessons)} novas aulas para extração.")

    # 2. Extração
    max_lessons = limit or int(os.getenv("MAX_LESSONS_PER_RUN", 10))
    lessons_to_process = new_lessons[:max_lessons] if new_lessons else []

    extracted_count = 0
    if lessons_to_process:
        logger.info(f"Iniciando extração sequencial de {len(lessons_to_process)} aula(s)...")
        for lesson in lessons_to_process:
            logger.info(f"Extraindo: {lesson['titulo']} do {lesson['modulo']}")
            res = extract_lesson(
                url=lesson["url"],
                modulo_nome=lesson["modulo"],
                aula_titulo=lesson["titulo"],
                slug=lesson["slug"],
                mock=mock,
                curso_nome=lesson.get("curso"),
                subpasta=lesson.get("subpasta")
            )
            if res:
                extracted_count += 1
            
            if not mock:
                delay = random.randint(3, 7)
                logger.info(f"Pausa anti-rate-limit: aguardando {delay} segundos...")
                time.sleep(delay)

    # 3. Processamento & Markdown
    # Varre a pasta data/raw para encontrar arquivos não processados
    logger.info("Varrendo arquivos locais para processamento de IA e Markdown...")
    raw_files = list(RAW_DIR.glob("**/*.json"))
    # Ignora o arquivo do índice
    raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]

    processed_count = 0
    markdown_count = 0

    for rf in raw_files:
        # Caminho relativo para manter a estrutura de subpastas
        rel_path = rf.relative_to(RAW_DIR)
        pf = PROCESSED_DIR / rel_path

        # 3. Enriquece os materiais de apoio se não ignorado (Notion/GitHub)
        if not skip_enrich:
            enrich_attachments_for_file(rf, use_ai=use_ai, force=False)

        # Roda IA se use_ai for True e o arquivo processado não existir
        if use_ai and not pf.exists():
            success = process_lesson_ai(rf)
            if success:
                processed_count += 1
        
        # Gera o markdown para o Obsidian
        md_file = generate_obsidian_markdown(rf, use_ai=use_ai, force=force_markdown)
        if md_file:
            markdown_count += 1

    # 4. Geração dos Índices
    generate_indexes()

    logger.info("=== Pipeline concluído com sucesso! ===")
    logger.info(f"Aulas extraídas: {extracted_count}")
    logger.info(f"Aulas enriquecidas por IA: {processed_count}")
    logger.info(f"Notas Markdown criadas/atualizadas: {markdown_count}")

def main():
    parser = argparse.ArgumentParser(
        description="Lecture Harvester - Pipeline de Extração e Organização de Aulas para Obsidian",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Comando para executar")
    
    # Subcomando: login
    subparsers.add_parser("login", help="Executa o login automático e salva a sessão")
    
    # Subcomando: sync
    parser_sync = subparsers.add_parser("sync", help="Sincroniza o mapeamento de aulas do curso")
    parser_sync.add_argument("--course-id", type=str, help="ID do curso na plataforma para sincronizar")
    parser_sync.add_argument("--list-courses", action="store_true", help="Lista os cursos disponíveis na plataforma")
    
    # Subcomando: list-courses
    subparsers.add_parser("list-courses", help="Lista os cursos disponíveis na plataforma")
    
    # Subcomando: extract
    parser_extract = subparsers.add_parser("extract", help="Extrai o conteúdo de uma aula")
    parser_extract.add_argument("--url", type=str, help="URL da aula")
    parser_extract.add_argument("--modulo", type=str, help="Nome do módulo")
    parser_extract.add_argument("--aula", type=str, help="Título da aula")
    parser_extract.add_argument("--slug", type=str, help="Slug para o arquivo")
    parser_extract.add_argument("--curso", type=str, help="Nome do curso para salvar no JSON da aula")
    parser_extract.add_argument("--mock", action="store_true", help="Gera dados simulados para teste")

    # Subcomando: process
    parser_process = subparsers.add_parser("process", help="Enriquece aulas extraídas utilizando IA")
    parser_process.add_argument("--file", type=str, help="Caminho do arquivo JSON bruto")
    parser_process.add_argument("--all", action="store_true", help="Processa todas as aulas brancas pendentes")
    parser_process.add_argument("--force", action="store_true", help="Força reprocessamento de IA")

    # Subcomando: markdown
    parser_md = subparsers.add_parser("markdown", help="Gera arquivos markdown para o Obsidian")
    parser_md.add_argument("--file", type=str, help="Caminho do arquivo JSON bruto")
    parser_md.add_argument("--all", action="store_true", help="Gera markdown para todas as aulas no cache")
    parser_md.add_argument("--use-ai", action="store_true", help="Gera notas incluindo o conteúdo processado de IA")
    parser_md.add_argument("--force", action="store_true", help="Força a regeneração de todas as notas do Obsidian")

    # Subcomando: attachments-enrich
    parser_att = subparsers.add_parser("attachments-enrich", help="Enriquece materiais de apoio (Notion/GitHub)")
    parser_att.add_argument("--file", type=str, help="Arquivo JSON bruto da aula")
    parser_att.add_argument("--all", action="store_true", help="Enriquece materiais de todas as aulas do cache bruto")
    parser_att.add_argument("--use-ai", action="store_true", help="Ativa sumarização por IA no enriquecimento")
    parser_att.add_argument("--force", action="store_true", help="Força reprocessamento de materiais já enriquecidos")
    parser_att.add_argument("--limit", type=int, help="Limite de aulas para processar com --all")

    # Subcomando: index
    subparsers.add_parser("index", help="Reconstrói os índices de módulos e geral no Obsidian")

    # Subcomando: reprocess
    parser_reprocess = subparsers.add_parser("reprocess", help="Varre o vault do Obsidian por notas incompletas e as re-extrai da plataforma")
    parser_reprocess.add_argument("--use-ai", action="store_true", help="Enriquece as notas reprocessadas usando a API de IA")

    # Subcomando: pipeline (Orquestração completa)
    parser_pipe = subparsers.add_parser("pipeline", help="Executa todo o pipeline (Sync -> Extract -> Process -> MD -> Index)")
    parser_pipe.add_argument("--mock", action="store_true", help="Usa dados simulados para teste (sem requisições reais à plataforma)")
    parser_pipe.add_argument("--limit", type=int, help="Limite de aulas a serem processadas nesta execução")
    parser_pipe.add_argument("--use-ai", action="store_true", help="Executa a etapa de enriquecimento de IA")
    parser_pipe.add_argument("--skip-enrich", action="store_true", help="Pula a etapa de enriquecimento de materiais de apoio (Notion/GitHub)")
    parser_pipe.add_argument("--course-id", type=str, help="ID do curso na plataforma para sincronizar no pipeline")
    parser_pipe.add_argument("--force-markdown", action="store_true", help="Força a regeneração de todas as notas do Obsidian no pipeline")

    args = parser.parse_args()

    if args.command == "login":
        success = login(force=True)
        sys.exit(0 if success else 1)
        
    elif args.command == "sync":
        if not login():
            logger.error("Não foi possível autenticar para realizar o Sync.")
            sys.exit(1)
        if args.list_courses:
            courses = crawl_course(sync_mode=False, list_courses=True)
            if not courses:
                logger.error("Nenhum curso encontrado para listagem.")
                sys.exit(1)
            print("\nCursos disponíveis:")
            for course in courses:
                print(f"- ID {course['id']}: {course['name']}")
        else:
            crawl_course(sync_mode=True, course_id=args.course_id)
            
    elif args.command == "list-courses":
        if not login():
            logger.error("Não foi possível autenticar para listar os cursos.")
            sys.exit(1)
        courses = crawl_course(sync_mode=False, list_courses=True)
        if not courses:
            logger.error("Nenhum curso encontrado para listagem.")
            sys.exit(1)
        print("\nCursos disponíveis:")
        for course in courses:
            print(f"- ID {course['id']}: {course['name']}")
        
    elif args.command == "extract":
        if not args.mock and not args.url:
            parser_extract.error("A --url é obrigatória caso --mock não esteja ativo.")
        extract_lesson(args.url, args.modulo, args.aula, args.slug, mock=args.mock, curso_nome=args.curso)
        
    elif args.command == "process":
        if args.file:
            success = process_lesson_ai(Path(args.file), force=args.force)
            sys.exit(0 if success else 1)
        elif args.all:
            raw_files = list(RAW_DIR.glob("**/*.json"))
            raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]
            success_count = 0
            for rf in raw_files:
                if process_lesson_ai(rf, force=args.force):
                    success_count += 1
            logger.info(f"Concluído: {success_count} de {len(raw_files)} arquivos processados.")
        else:
            parser_process.print_help()
            
    elif args.command == "markdown":
        if args.file:
            md_file = generate_obsidian_markdown(Path(args.file), use_ai=args.use_ai, force=args.force)
            sys.exit(0 if md_file else 1)
        elif args.all:
            raw_files = list(RAW_DIR.glob("**/*.json"))
            raw_files = [rf for rf in raw_files if rf.name != "course_index.json"]
            count = 0
            for rf in raw_files:
                if generate_obsidian_markdown(rf, use_ai=args.use_ai, force=args.force):
                    count += 1
            logger.info(f"Concluído: {count} arquivos Markdown processados no vault.")
        else:
            parser_md.print_help()

    elif args.command == "attachments-enrich":
        use_ai = args.use_ai
        if args.file:
            success = enrich_attachments_for_file(Path(args.file), use_ai=use_ai, force=args.force)
            sys.exit(0 if success else 1)
        elif args.all:
            success_count, total = enrich_attachments_for_all(use_ai=use_ai, force=args.force, limit=args.limit)
            logger.info(f"Enriquecimento de materiais concluído: {success_count} de {total} aulas.")
            sys.exit(0 if success_count == total else 1)
        else:
            parser_att.print_help()
            
    elif args.command == "index":
        success = generate_indexes()
        sys.exit(0 if success else 1)
        
    elif args.command == "reprocess":
        success = reprocess_missing_content(use_ai=args.use_ai)
        sys.exit(0 if success else 1)
        
    elif args.command == "pipeline":
        run_full_pipeline(
            mock=args.mock,
            limit=args.limit,
            use_ai=args.use_ai,
            course_id=args.course_id,
            skip_enrich=args.skip_enrich,
            force_markdown=args.force_markdown
        )
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
