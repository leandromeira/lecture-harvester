# Lecture Harvester Scraper

Este diretório contém os scripts de automação baseados em **Playwright** para realizar o login e mapear os módulos e aulas da plataforma de ensino Full Cycle.

## Configuração do Ambiente (`.env`)

Crie ou atualize o arquivo `.env` na raiz do projeto com as seguintes chaves de configuração:

```env
# URL base de autenticação da plataforma
PLATFORM_URL=https://plataforma.fullcycle.com.br/login

# Nome do curso que você deseja indexar/varrer (deve coincidir com o nome do curso na plataforma)
COURSE_NAME=MBA em Engenharia de Software com IA

# Módulos do curso que você quer que o crawler ignore (separados por vírgula)
# Exemplo: IGNORE_MODULES=Comece por aqui,Bônus MBA
IGNORE_MODULES=Comece por aqui

# Caminho para o seu vault do Obsidian (onde as notas de aula serão geradas)
OBSIDIAN_VAULT_PATH=/Users/leandromeira/Obsidian

# Modelo de IA que será usado no summarize.py
AI_MODEL=gpt-4o

# Temperatura criativa do modelo de IA (entre 0.0 e 1.0)
AI_TEMPERATURE=0.2
```

## Como Usar

### 1. Autenticação e Login Inicial
Para iniciar a sessão de forma segura e visual:
```bash
venv/bin/python scraper/interactive_login.py
```
Isso abrirá uma janela visível do navegador. Complete o login manualmente na plataforma. Assim que você entrar no painel de controle do aluno, o script detectará automaticamente o sucesso, salvará os cookies de sessão no arquivo `config/storage_state.json` e fechará o navegador.

### 2. Mapear o Curso (Crawl)
Para indexar os módulos e aulas do curso configurado na variável `COURSE_NAME`:
```bash
venv/bin/python scraper/crawl_course.py
```
O script gerará ou atualizará de forma incremental (Sync Mode) o arquivo de índice em `data/raw/course_index.json`.

Para listar os cursos disponíveis na conta:
```bash
venv/bin/python main.py sync --list-courses
```

Para sincronizar um curso específico pelo ID:
```bash
venv/bin/python main.py sync --course-id <ID_DO_CURSO>
```

### 3. Reindexar Tudo (Sobrescrever o Índice)
Se você precisar reconstruir ou reindexar totalmente o arquivo de índice desabilitando o modo incremental:
```bash
venv/bin/python scraper/crawl_course.py --no-sync
```
Isso ignorará o índice anterior e gerará uma nova lista do zero contendo apenas o estado atualizado das aulas.

### 4. Materiais de Apoio
Durante a extração de aula, links de materiais são detectados e classificados (`direct_file`, `github_repo`, `notion_page`, `external_link`).

Arquivos diretos (`direct_file`) são baixados para:
- `data/raw/<módulo>/attachments/<slug-da-aula>/`

Todos os materiais são registrados no JSON bruto em `materiais_apoio` com status de enriquecimento.

Para enriquecer links de GitHub/Notion (clonar/zipar repositório, snapshot de página e resumo opcional com IA):
```bash
venv/bin/python main.py attachments-enrich --file "data/raw/<modulo>/<aula>.json"
```

Processando todas as aulas:
```bash
venv/bin/python main.py attachments-enrich --all
```

Sem IA (apenas captura de artefatos):
```bash
venv/bin/python main.py attachments-enrich --all --no-ai
```

Após enriquecer, gere/atualize a nota:
```bash
venv/bin/python main.py markdown --file "data/raw/<modulo>/<aula>.json" --skip-ai
```

A nota Markdown inclui os links de materiais e os artefatos locais, que também são copiados para a pasta `attachments/` do módulo no Obsidian.

### 5. Auditoria de Custos e Tokens
Toda chamada de IA (pipeline de resumo e enriquecimento de materiais) registra consumo e custo estimado em:
- `logs/cost_tracker.csv`

Campos registrados:
- `provider`, `model`, `call_context`, `status`
- `input_tokens`, `output_tokens`, `total_tokens`
- `input_cost_usd`, `output_cost_usd`, `total_cost_usd`

Exemplo para visualizar os últimos registros:
```bash
tail -n 20 logs/cost_tracker.csv
```
