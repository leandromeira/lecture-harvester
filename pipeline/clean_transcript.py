import re

def clean_transcript(text: str) -> str:
    """
    Limpa ruídos e metadados comuns de transcrições e legendas.
    Remove cabeçalhos WebVTT, timestamps de diversos formatos e linhas vazias.
    """
    if not text:
        return ""

    # Dividir em linhas para processamento
    lines = text.split("\n")
    cleaned_lines = []

    # Regex para timestamps comuns:
    # 1. SRT / WebVTT (ex: 00:00:01.000 --> 00:00:04.000 ou 00:12:30.400)
    vtt_timestamp_pattern = re.compile(r'\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}')
    # 2. Timestamps simples (ex: [00:12], 01:23, (12:34))
    simple_timestamp_pattern = re.compile(r'^[\[\(]?\d{1,2}:\d{2}(:\d{2})?[\]\)]?')
    # 3. Números isolados de linhas de SRT (ex: 1, 2, 3...)
    srt_number_pattern = re.compile(r'^\d+$')

    for line in lines:
        line_strip = line.strip()
        
        # Ignorar marcadores de WebVTT
        if line_strip.upper() in ["WEBVTT", "KIND: CAPTIONS", "LANGUAGE: PT-BR", "LANGUAGE: PT", "LANGUAGE: EN"]:
            continue
        
        # Ignorar timestamps de tempo de tela e números de legenda SRT
        if vtt_timestamp_pattern.search(line_strip):
            continue
        if srt_number_pattern.match(line_strip):
            continue

        # Remover timestamps internos no meio da fala (ex: "Olá [00:12] hoje vamos...")
        # Substitui padrões de timestamp por string vazia
        line_clean = re.sub(r'[\[\(]?\d{1,2}:\d{2}(:\d{2})?[\]\)]?', '', line_strip)
        line_clean = line_clean.strip()

        if line_clean:
            cleaned_lines.append(line_clean)

    # Junta as falas. Se as linhas parecerem pequenas, podemos juntar com espaço,
    # caso contrário, mantemos quebras de linha normais para parágrafos.
    final_text = "\n".join(cleaned_lines)
    
    # Remover múltiplos espaços seguidos
    final_text = re.sub(r' +', ' ', final_text)
    # Remover múltiplas quebras de linha consecutivas
    final_text = re.sub(r'\n+', '\n', final_text)
    
    return final_text.strip()

if __name__ == "__main__":
    # Teste rápido
    sample = """
    WEBVTT
    Kind: captions
    Language: pt

    1
    00:00:01.200 --> 00:00:04.500
    [00:01] Olá a todos!

    2
    00:00:04.500 --> 00:00:08.100
    Esta é uma aula de (00:04) teste.
    """
    print("=== Original ===")
    print(sample)
    print("=== Limpo ===")
    print(clean_transcript(sample))
