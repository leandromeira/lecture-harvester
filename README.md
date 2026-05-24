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

### 3. Reindexar Tudo (Sobrescrever o Índice)
Se você precisar reconstruir ou reindexar totalmente o arquivo de índice desabilitando o modo incremental:
```bash
venv/bin/python scraper/crawl_course.py --no-sync
```
Isso ignorará o índice anterior e gerará uma nova lista do zero contendo apenas o estado atualizado das aulas.
