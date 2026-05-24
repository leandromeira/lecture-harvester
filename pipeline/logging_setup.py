import sys
from pathlib import Path
from loguru import logger

# Garantir que o diretório de logs existe
logs_dir = Path(__file__).resolve().parents[1] / "logs"
logs_dir.mkdir(exist_ok=True)

# Limpar configurações padrão
logger.remove()

# Adicionar saída do console (info e acima)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:7}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Adicionar log de erros geral (error e acima)
logger.add(
    logs_dir / "errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {name}:{line} - {message}",
    level="ERROR",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8"
)

# Criar wrappers para logs específicos de extração e processamento
def setup_extraction_logger():
    """Configura logger direcionado a logs/extraction.log"""
    extraction_log = logs_dir / "extraction.log"
    logger.add(
        extraction_log,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {name}:{line} - {message}",
        level="DEBUG",
        filter=lambda record: "extraction" in record["extra"] or record["level"].name == "ERROR",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8"
    )
    return logger.bind(extraction=True)

def setup_processing_logger():
    """Configura logger direcionado a logs/processing.log"""
    processing_log = logs_dir / "processing.log"
    logger.add(
        processing_log,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {name}:{line} - {message}",
        level="DEBUG",
        filter=lambda record: "processing" in record["extra"] or record["level"].name == "ERROR",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8"
    )
    return logger.bind(processing=True)
