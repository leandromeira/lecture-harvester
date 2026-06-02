# Lecture Harvester Scraper

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Playwright Version](https://img.shields.io/badge/playwright-%E2%9C%93-2EAD5C?logo=playwright&logoColor=white)
![Obsidian Compatibility](https://img.shields.io/badge/Obsidian-Ready-8B6DDF?logo=obsidian&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Donate-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/leandromeira)

</div>

---

O **Lecture Harvester** é um pipeline de ETL automatizado em **Python** e **Playwright** para extrair, processar e organizar aulas e materiais de apoio da plataforma de ensino Full Cycle, convertendo-os em notas de estudo estruturadas no **Obsidian**.

---

## ⚡ TL;DR — Como começar rápido e sincronizar tudo?

1. **Instale e configure:** Clone o repositório, instale as dependências e crie o `.env` com suas credenciais, ID do curso e o caminho para o vault do Obsidian.
2. **Faça o login:** Execute o script para abrir a janela do navegador e logar na plataforma:
   ```bash
   venv/bin/python scraper/login.py
   ```
3. **Mande sincronizar e gerar tudo:**
   ```bash
   venv/bin/python main.py pipeline --limit 999
   ```
   *(Adicione a flag `--use-ai` caso queira consumir tokens de IA e gerar resumos/flashcards).*

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
   COURSE_NAME=
   IGNORE_MODULES=

   # Integração com Obsidian
   OBSIDIAN_VAULT_PATH=

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
Para varrer o curso, extrair as aulas pendentes, baixar e organizar os arquivos de apoio e salvar no Obsidian de forma segura (sem gastar tokens de IA), basta executar um único comando:
```bash
venv/bin/python main.py pipeline
```
Para habilitar o enriquecimento e resumos por IA, adicione a flag `--use-ai`:
```bash
venv/bin/python main.py pipeline --use-ai
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
  * `--use-ai`: Executa a etapa de processamento por IA, enriquecendo as notas com resumos estruturados e flashcards.
  * `--skip-enrich`: Pula a etapa de enriquecimento de anexos (clonagem do GitHub, snapshots de Notion e downloads do Google Drive).
  * `--course-id <ID>`: ID específico do curso a sincronizar, pulando a detecção automática por nome.
  * `--force-markdown`: Força a regeneração de todas as notas do Obsidian, mesmo que os dados brutos de entrada não tenham sido alterados.

### 2. `login` (Autenticação manual/forçada)
Abre uma nova janela headed do navegador para realizar o login manual e atualizar os cookies de sessão de forma segura.
```bash
venv/bin/python main.py login
```

### 3. `list-courses` (Listar Cursos)
Lista todos os cursos disponíveis na sua conta com seus respectivos IDs (útil para descobrir o `course-id` de um curso).
```bash
venv/bin/python main.py list-courses
```

### 4. `sync` (Sincronização de Estrutura)
Sincroniza apenas a listagem de aulas e módulos, gerando o arquivo local `data/raw/course_index.json`.
```bash
venv/bin/python main.py sync [flags]
```
* **Flags Opcionais:**
  * `--course-id <ID>`: Mapeia um curso específico pelo ID fornecido.
  * `--list-courses`: Apenas lista todos os cursos disponíveis na conta com seus respectivos IDs (legado).

### 5. `extract` (Extração Individual)
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

### 6. `attachments-enrich` (Enriquecimento Isolado)
Processa materiais de apoio (clona/zipa repositórios do GitHub, faz snapshot textual de Notion e realiza download de arquivos públicos do Google Drive).
```bash
venv/bin/python main.py attachments-enrich [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Processa apenas o arquivo JSON bruto de uma aula específica.
  * `--all`: Processa materiais de todas as aulas presentes na pasta `data/raw`.
  * `--use-ai`: Ativa a sumarização por IA dos repositórios GitHub e páginas do Notion.
  * `--force`: Força re-enriquecer materiais que já possuem o status de enriquecidos/baixados.
  * `--limit <N>`: Limita a quantidade de aulas enriquecidas de cada vez.

### 7. `process` (Enriquecimento IA da Aula)
Roda o prompt consolidado de IA (resumo executivo, conceitos e flashcards) em uma chamada única no JSON bruto (economizando cerca de 66% de tokens de entrada).
```bash
venv/bin/python main.py process [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Processa apenas uma aula específica.
  * `--all`: Enriquece todas as aulas brancas pendentes locais.
  * `--force`: Força reprocessar a IA de aulas já enriquecidas no cache local.

### 8. `markdown` (Geração de Notas)
Gera os arquivos markdown e os copia junto dos anexos para o Obsidian usando build incremental (só regera notas se os arquivos de dados brutos ou processados forem mais recentes que a nota do Obsidian).
```bash
venv/bin/python main.py markdown [flags]
```
* **Flags Opcionais:**
  * `--file <CAMINHO>`: Gera a nota markdown de uma aula específica.
  * `--all`: Gera a nota markdown de todas as aulas em cache.
  * `--use-ai`: Gera as notas incluindo o conteúdo processado por IA (resumos, flashcards).
  * `--force`: Força a regeneração de todas as notas do Obsidian, ignorando a data de modificação.

### 9. `index` (Geração de Índices)
Reconstrói os arquivos `00 - Índice - <Módulo>.md` e `00 - Índice Geral.md` no Obsidian de forma organizada por módulo e numeração de aula.
```bash
venv/bin/python main.py index
```

### 10. `reprocess` (Reprocessamento de Notas Incompletas)
Varre o vault do Obsidian buscando notas `.md` que estejam sem resumo da plataforma ou sem transcrição. A partir do URL da nota, o script localiza o respectivo JSON no cache bruto local, navega até a plataforma Full Cycle para extrair os dados faltantes via Playwright e atualiza os arquivos.
```bash
venv/bin/python main.py reprocess [flags]
```
* **Flags Opcionais:**
  * `--use-ai`: Além de re-extrair e preencher os dados brutos de resumo e transcrição, executa o processamento de enriquecimento IA (`process_lesson_ai`) nas notas atualizadas antes de recriá-las no Obsidian.

---

## 📈 Rastreamento de Custos e Tokens

Toda chamada de IA (pipeline de resumos e enriquecimento de anexos) é auditada. O consumo detalhado é salvo em:
- `logs/cost_tracker.csv`

Campos monitorados:
- `timestamp_utc`, `provider`, `model`, `call_context`, `status`
- `input_tokens`, `output_tokens`, `total_tokens`
- `input_cost_usd`, `output_cost_usd`, `total_cost_usd`
- `error_message`

---

## ❓ Perguntas Frequentes (FAQ)

### 1. Começando do zero: como popular o vault inteiro de uma vez?
1. Execute o login: `venv/bin/python scraper/login.py`
2. Rode o pipeline completo sem limites de aulas:
   * **Sem IA:** `venv/bin/python main.py pipeline --limit 999`
   * **Com IA:** `venv/bin/python main.py pipeline --use-ai --limit 999`

### 2. E se faltou alguma aula no meio?
* Se a aula **não existe no vault**: rode `venv/bin/python main.py pipeline` (ou com `--use-ai`). O pipeline incremental trará apenas a aula ausente.
* Se a nota **existe mas está incompleta** (sem resumo/transcrição): rode `venv/bin/python main.py reprocess` (ou com `--use-ai`).

### 3. E se não veio algum anexo específico?
1. Force a re-extração do anexo da aula:
   `venv/bin/python main.py attachments-enrich --file "data/raw/XX - Nome do Módulo/YY - Capítulo/aula.json" --force`
2. Force a regeração da nota Markdown correspondente:
   `venv/bin/python main.py markdown --file "data/raw/XX - Nome do Módulo/YY - Capítulo/aula.json" --force`

### 4. Como sincronizar novas aulas lançadas no curso?
Rode novamente o pipeline principal. Ele detectará apenas as novas aulas inseridas na plataforma e fará o download incremental:
`venv/bin/python main.py pipeline` (ou com `--use-ai`).

