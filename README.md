# Lecture Harvester Scraper

O **Lecture Harvester** é um pipeline robusto de ETL automatizado em **Python** e **Playwright** para extrair, processar e organizar aulas e materiais de apoio da plataforma de ensino Full Cycle, convertendo-os em notas de estudo estruturadas no **Obsidian** (segundo cérebro).

---

## 🛠️ Configuração do Ambiente

1. **Instalação das Dependências:**
   Configure seu ambiente virtual e instale os pacotes necessários:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Arquivo `.env`:**
   Crie ou configure o arquivo `.env` na raiz do projeto:
   ```env
   # Credenciais e URLs
   PLATFORM_URL=https://plataforma.fullcycle.com.br/login
   COURSE_NAME=MBA em Engenharia de Software com IA
   IGNORE_MODULES=Comece por aqui, Bônus MBA, Encontros Ao Vivo, Desafios Técnicos - MBA IA

   # Integração com Obsidian
   OBSIDIAN_VAULT_PATH=/Users/leandromeira/Obsidian

   # Configurações de IA (openai, anthropic ou gemini)
   AI_PROVIDER=openai
   AI_MODEL=gpt-4o
   AI_TEMPERATURE=0.2

   # Chaves de API de IA (Conforme o provedor escolhido)
   OPENAI_API_KEY=sua-chave-openai
   GEMINI_API_KEY=sua-chave-gemini
   ANTHROPIC_API_KEY=sua-chave-anthropic

   # Configurações de Execução do Scraper
   MAX_LESSONS_PER_RUN=10
   PLAYWRIGHT_HEADLESS=true
   PLAYWRIGHT_TIMEOUT=30000
   EXTRACTION_WORKERS=4
   ```

---

## 🚀 Guia de Uso Passo a Passo

Para utilizar o sistema de ponta a ponta de forma simples e rápida, siga estas 3 etapas:

### Passo 1: Login Inicial na Plataforma
Como a plataforma possui mecanismos de segurança, o login inicial é feito em modo interativo visual. Execute:
```bash
venv/bin/python scraper/login.py
```
Isso abrirá o navegador. Faça o login manualmente. Assim que entrar no painel do aluno, o script salvará os cookies de sessão de forma segura em `config/storage_state.json` e fechará a janela. Os próximos comandos usarão essa sessão em modo headless.

### Passo 2: Executar o Pipeline Completo (ETL)
Para varrer o curso, extrair as aulas pendentes, baixar arquivos de apoio, enriquecê-los (Notion/GitHub), processar os resumos por IA e salvar no Obsidian, basta executar um único comando:
```bash
venv/bin/python main.py pipeline
```

### Passo 3: Abrir no Obsidian
As notas de aula serão organizadas em pastas por módulo dentro do seu Vault do Obsidian, contendo o índice do módulo (`00 - Índice - <Módulo>.md`), anexos locais copiados na pasta `/attachments` de cada módulo e as conexões (`[[Wikilinks]]`) para navegação facilitada.

---

## ⚙️ Comandos Detalhados da CLI e Flags Opcionais

O Lecture Harvester é controlado por subcomandos através do arquivo `main.py`.

### 1. `pipeline` (Orquestração Completa)
Executa todo o fluxo de ponta a ponta de forma sequencial.
```bash
venv/bin/python main.py pipeline [flags]
```
* **Flags Opcionais:**
  * `--mock`: Roda o pipeline simulando dados de teste fictícios (sem fazer requisições reais ou gastar tokens).
  * `--limit <N>`: Limita a quantidade de novas aulas a extrair nesta execução. Sobrescreve `MAX_LESSONS_PER_RUN`.
  * `--skip-ai`: Pula a sumarização avançada da IA. Gera notas mais simples com resumo da plataforma e transcrição.
  * `--skip-enrich`: Pula a etapa de enriquecimento de anexos (clonagem do GitHub e snapshots de Notion).
  * `--course-id <ID>`: ID específico do curso a sincronizar, pulando a detecção automática por nome.

### 2. `login` (Autenticação manual/forçada)
```bash
venv/bin/python main.py login [flags]
```
* **Flags Opcionais:**
  * `--force`: Ignora qualquer sessão anterior e força a abertura de uma nova janela headed para login.

### 3. `sync` (Sincronização de Estrutura)
Sincroniza apenas a listagem de aulas e módulos, gerando o arquivo local `data/raw/course_index.json`.
```bash
venv/bin/python main.py sync [flags]
```
* **Flags Opcionais:**
  * `--list-courses`: Apenas lista todos os cursos disponíveis na conta com seus respectivos IDs e encerra.
  * `--course-id <ID>`: Mapeia um curso específico pelo ID fornecido.

### 4. `extract` (Extração Individual)
Extrai o conteúdo bruto de uma única aula e salva o JSON em `data/raw`.
```bash
venv/bin/python main.py extract --url <URL> --modulo <NOME> --aula <TITULO> --slug <SLUG> [flags]
```
* **Flags Requeridas:**
  * `--url`: URL da aula na plataforma.
  * `--modulo`: Nome do módulo correspondente.
  * `--aula`: Título da aula.
  * `--slug`: Nome amigável de arquivo a ser salvo (ex: `introducao-a-tokens`).
* **Flags Opcionais:**
  * `--curso <NOME>`: Nome do curso (padrão é o configurado no `.env`).
  * `--mock`: Salva dados simulados de teste.

### 5. `attachments-enrich` (Enriquecimento Isolado)
Processa materiais de apoio (clona/zipa repositórios do GitHub, faz snapshot textual de Notion e gera resumos com IA).
```bash
venv/bin/python main.py attachments-enrich [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Processa apenas o arquivo JSON bruto de uma aula específica.
  * `--all`: Processa materiais de todas as aulas presentes na pasta `data/raw`.
  * `--no-ai`: Desativa a sumarização dos anexos por IA (apenas faz o clone/snapshot e zip).
  * `--force`: Força re-enriquecer materiais que já possuem o status de enriquecidos.
  * `--limit <N>`: Limita a quantidade de aulas enriquecidas de cada vez.

### 6. `process` (Enriquecimento IA da Aula)
Roda os prompts de IA de resumo executivo, conceitos e flashcards no JSON bruto.
```bash
venv/bin/python main.py process [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Processa apenas uma aula específica.
  * `--all`: Enriquece todas as aulas brancas pendentes locais.
  * `--force`: Força reprocessar a IA de aulas já enriquecidas no cache local.

### 7. `markdown` (Geração de Notas)
Gera os arquivos markdown e os copia junto dos anexos para o Obsidian.
```bash
venv/bin/python main.py markdown [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Gera a nota markdown de uma aula específica.
  * `--all`: Gera a nota markdown de todas as aulas em cache.
  * `--skip-ai`: Gera a nota sem incluir o conteúdo da IA.

### 8. `index` (Geração de Índices)
Reconstrói os arquivos `00 - Índice - <Módulo>.md` e `00 - Índice Geral.md` no Obsidian de forma organizada por módulo e numeração de aula.
```bash
venv/bin/python main.py index
```

---

## 📈 Rastreamento de Custos e Tokens

Toda chamada de IA (pipeline de resumos e enriquecimento de anexos) é auditada. O consumo detalhado é salvo em:
- `logs/cost_tracker.csv`

Campos monitorados:
- `timestamp_utc`, `provider`, `model`, `call_context`, `status`
- `input_tokens`, `output_tokens`, `total_tokens`
- `input_cost_usd`, `output_cost_usd`, `total_cost_usd`
- `error_message`
