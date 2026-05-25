import os
import sys
import json
import re
import time
import random
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.append(str(Path(__file__).resolve().parents[1]))
from pipeline.logging_setup import setup_processing_logger
from pipeline.clean_transcript import clean_transcript
from pipeline.cost_tracker import log_cost_event

logger = setup_processing_logger()

# Configurações carregadas via variáveis de ambiente (.env)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PROCESSED_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

def extract_json_block(text: str) -> dict:
    """Extrai e valida um bloco JSON de uma resposta de texto da IA."""
    # Procura blocos marcados com ```json ... ``` ou apenas ``` ... ```
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # Se não houver blocos de código, tenta achar qualquer coisa entre chaves { e }
        match_raw = re.search(r'(\{.*\})', text, re.DOTALL)
        if match_raw:
            json_str = match_raw.group(1)
        else:
            json_str = text

    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar JSON da resposta: {e}\nTexto original:\n{text}")
        # Retorna dicionário vazio para não quebrar a execução
        return {}

def get_ai_client(provider: str):
    """Inicializa o cliente do SDK correspondente."""
    if provider == "openai":
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY não definida no ambiente.")
        return OpenAI(api_key=api_key)
        
    elif provider == "anthropic":
        from anthropic import Anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY não definida no ambiente.")
        return Anthropic(api_key=api_key)
        
    elif provider == "gemini":
        from google import genai
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY não definida no ambiente.")
        return genai.Client(api_key=api_key)
        
    else:
        raise ValueError(f"Provedor '{provider}' não suportado.")

def call_ai(provider: str, model: str, prompt: str, client, temperature: float = 0.2, call_context: str = "unknown") -> str:
    """Faz a chamada da API do provedor selecionado de forma direta usando o SDK, com retry automático e backoff exponencial."""
    max_retries = 5
    base_delay = 2.0

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(f"Fazendo chamada de IA ({provider} - {model} com temperatura {temperature}), tentativa {attempt}/{max_retries}...")
            
            if provider == "openai":
                response = client.chat.completions.create(
                    model=model,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": "Você é um assistente especializado em formatação JSON. Sempre responda em formato JSON válido."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature
                )
                log_cost_event(provider, model, call_context, response=response, status="success")
                return response.choices[0].message.content
                
            elif provider == "anthropic":
                response = client.messages.create(
                    model=model,
                    max_tokens=4000,
                    temperature=temperature,
                    system="Você é um assistente especializado em formatação JSON.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                log_cost_event(provider, model, call_context, response=response, status="success")
                return response.content[0].text
                
            elif provider == "gemini":
                # Usando o SDK google-genai com configuração de temperatura e formato JSON
                from google import genai
                config = genai.types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json"
                )
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config
                )
                log_cost_event(provider, model, call_context, response=response, status="success")
                return response.text
                
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = "rate limit" in error_msg or "429" in error_msg or "too many requests" in error_msg
            log_cost_event(provider, model, call_context, response=None, status="error", error_message=str(e))
            
            if attempt == max_retries:
                logger.error(f"Falha definitiva após {max_retries} tentativas na chamada de IA: {e}")
                raise e
            
            # Calcular delay com backoff exponencial + jitter
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.1, 1.0)
            
            if is_rate_limit:
                logger.warning(f"[Rate Limit] Limite de requisições atingido. Tentativa {attempt}/{max_retries} falhou. Retrying em {delay:.2f}s... Erro: {e}")
            else:
                logger.warning(f"[Erro de API] Tentativa {attempt}/{max_retries} falhou. Retrying em {delay:.2f}s... Erro: {e}")
                
            time.sleep(delay)
            
    return ""

def format_prompt(template: str, context: dict) -> str:
    """Substitui os placeholders do tipo {chave} no template sem quebrar chaves de JSON literais."""
    result = template
    for key, value in context.items():
        result = result.replace(f"{{{key}}}", str(value))
    return result

def process_lesson_ai(raw_json_path: Path, force=False) -> bool:
    """
    Carrega o JSON bruto da aula, roda os três prompts na IA,
    mescla os resultados estruturados e salva na pasta data/processed/.
    """
    if not raw_json_path.exists():
        logger.error(f"Arquivo bruto não encontrado: {raw_json_path}")
        return False

    # Define caminho de saída
    relative_path = raw_json_path.relative_to(raw_json_path.parents[1])
    output_path = PROCESSED_DATA_DIR / relative_path

    # Se já existir e não forçar, ignora (cache local)
    if output_path.exists() and not force:
        logger.info(f"Aula já enriquecida no cache local: {output_path.name}. Pulando...")
        return True

    logger.info(f"Processando enriquecimento IA para: {raw_json_path.name}")

    # Carrega dados brutos
    with open(raw_json_path, "r", encoding="utf-8") as f:
        lesson_data = json.load(f)

    # Limpa transcrição
    raw_transcript = lesson_data.get("transcricao", "")
    cleaned = clean_transcript(raw_transcript)
    
    # Se a transcrição limpa for vazia, usa o resumo original como base
    if not cleaned:
        logger.warning(f"Transcrição vazia após limpeza para {raw_json_path.name}. Usando resumo original como contexto.")
        cleaned = f"Sem transcrição disponível. Resumo Original: {lesson_data.get('resumo_original', '')}"

    # Carrega prompts
    try:
        with open(PROMPTS_DIR / "summarize.txt", "r", encoding="utf-8") as f:
            prompt_sum_tmpl = f.read()
        with open(PROMPTS_DIR / "concepts.txt", "r", encoding="utf-8") as f:
            prompt_con_tmpl = f.read()
        with open(PROMPTS_DIR / "flashcards.txt", "r", encoding="utf-8") as f:
            prompt_fla_tmpl = f.read()
    except Exception as e:
        logger.error(f"Erro ao ler arquivos de prompt em '{PROMPTS_DIR}': {e}")
        return False

    # Configura parâmetros de IA
    provider = os.getenv("AI_PROVIDER", "openai")
    model = os.getenv("AI_MODEL", "gpt-4o")

    # Carrega temperatura
    temp_str = os.getenv("AI_TEMPERATURE")
    try:
        temperature = float(temp_str) if temp_str is not None else 0.2
    except ValueError:
        logger.warning(f"Temperatura inválida no env: '{temp_str}'. Usando valor padrão 0.2.")
        temperature = 0.2

    # Dados comuns para formatação dos prompts
    context = {
        "curso": lesson_data.get("curso", "MBA IA"),
        "modulo": lesson_data.get("modulo", "Geral"),
        "aula": lesson_data.get("aula", "Aula"),
        "resumo_original": lesson_data.get("resumo_original", "Sem resumo na plataforma."),
        "transcricao": cleaned
    }

    # Executar as 3 chamadas em paralelo e converter em JSON
    try:
        p_sum = format_prompt(prompt_sum_tmpl, context)
        p_con = format_prompt(prompt_con_tmpl, context)
        p_fla = format_prompt(prompt_fla_tmpl, context)

        def run_prompt(prompt_name: str, prompt_text: str) -> dict:
            logger.info(f"Executando prompt de {prompt_name}...")
            client = get_ai_client(provider)
            response_text = call_ai(
                provider,
                model,
                prompt_text,
                client,
                temperature=temperature,
                call_context=f"summarize:{prompt_name.lower()}"
            )
            return extract_json_block(response_text)

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                "sum": executor.submit(run_prompt, "Resumo", p_sum),
                "con": executor.submit(run_prompt, "Conceitos", p_con),
                "fla": executor.submit(run_prompt, "Flashcards", p_fla),
            }
            res_sum = futures["sum"].result()
            res_con = futures["con"].result()
            res_fla = futures["fla"].result()

    except Exception as e:
        logger.exception(f"Erro nas chamadas de API de IA: {e}")
        return False

    # Mesclar resultados de IA
    enriched_data = {
        "curso": lesson_data.get("curso"),
        "modulo": lesson_data.get("modulo"),
        "aula": lesson_data.get("aula"),
        "url": lesson_data.get("url"),
        "resumo_executivo": res_sum.get("resumo_executivo", "Não gerado."),
        "pontos_importantes": res_sum.get("pontos_importantes", []),
        "tags": res_sum.get("tags", []),
        "relacoes": res_sum.get("relacoes", []),
        "conceitos": res_con.get("conceitos", []),
        "explicacao_simplificada": res_con.get("explicacao_simplificada", "Não gerada."),
        "exemplos_citados": res_con.get("exemplos_citados", []),
        "perguntas_revisao": res_fla.get("perguntas_revisao", []),
        "flashcards": res_fla.get("flashcards", [])
    }

    # Salva o arquivo enriquecido
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Sucesso: Aula processada e salva em {output_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enriquece JSON de aula usando IA.")
    parser.add_argument("file_path", type=str, help="Caminho para o JSON bruto da aula.")
    parser.add_argument("--force", action="store_true", help="Força reprocessamento mesmo que já exista no cache.")
    args = parser.parse_args()

    success = process_lesson_ai(Path(args.file_path), force=args.force)
    sys.exit(0 if success else 1)
