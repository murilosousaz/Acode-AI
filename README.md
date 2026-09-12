# AcodeAI

Bot de estudos para Discord que responde dúvidas de vestibular (ENEM, FUVEST
etc.) usando RAG (Retrieval-Augmented Generation): materiais em PDF são
indexados como embeddings no MongoDB Atlas Vector Search e usados como
contexto para respostas geradas pela OpenAI.

## Arquitetura

O projeto segue princípios de DDD, dividido em camadas:

```
src/
├── domain/          # Entidades, value objects, contratos de repositório e
│                     # regras de negócio puras (não dependem de infra).
├── app/              # Casos de uso que orquestram o domínio.
├── infrastructure/    # Implementações concretas: OpenAI, MongoDB, PyMuPDF,
│                     # rate limiter, configurações.
└── presentation/      # Adaptador de entrada: bot e comandos do Discord.
```

## Funcionalidades

- `/duvida [pergunta] [materia]` — pergunta ao tutor, com histórico de
  conversa por usuário e filtro opcional por matéria.
- `/limpar_historico` — reseta o histórico de conversa do usuário.
- `/ingest_pdf` (admin) — envia um PDF pelo Discord para ser indexado.
- `scripts/ingest_cli.py` e `scripts/ingest_bulks_pdf.py` — ingestão de PDFs
  via linha de comando (individual ou em lote a partir de `data/raw_pdfs/`).

## Pré-requisitos

- Python 3.13+ e [uv](https://docs.astral.sh/uv/)
- Uma instância do MongoDB com suporte a Atlas Vector Search (o
  `docker-compose.yml` já sobe `mongodb-atlas-local` para desenvolvimento)
- Uma chave de API da OpenAI
- Um bot criado no [Discord Developer Portal](https://discord.com/developers/applications)
  com o intent `MESSAGE CONTENT` habilitado

## Configuração

1. Copie `.env.example` para `.env` e preencha as variáveis:

   ```bash
   cp .env.example .env
   ```

2. Instale as dependências:

   ```bash
   uv sync
   ```

3. Suba o MongoDB local (ou aponte `MONGO_URI` para um cluster Atlas real):

   ```bash
   docker compose up -d mongodb
   ```

4. Crie o índice de busca vetorial (necessário antes da primeira ingestão):

   ```bash
   uv run python -m scripts.create_vector_index
   ```

5. Ingira algum material de estudo:

   ```bash
   uv run python -m scripts.ingest_cli caminho/para/arquivo.pdf Fisica "Cinemática - Cap. 1"
   ```

   Ou, para ingestão em lote, coloque os PDFs em `data/raw_pdfs/` (nomeados
   como `Materia_Descricao.pdf`) e rode:

   ```bash
   uv run python -m scripts.ingest_bulks_pdf
   ```

6. Rode o bot:

   ```bash
   uv run python -m src.presentation.discord.main
   ```

## Rodando com Docker

```bash
docker compose up -d --build
```

Isso sobe o MongoDB e o bot juntos, lendo as variáveis do `.env`.

## Variáveis de ambiente

| Variável                     | Obrigatória | Descrição                                                |
|------------------------------|:-----------:|-----------------------------------------------------------|
| `DISCORD_BOT_TOKEN`          | ✅          | Token do bot no Discord Developer Portal                  |
| `MONGO_URI`                  | ✅          | String de conexão do MongoDB                               |
| `MONGO_DB_NAME`              |             | Nome do banco (padrão: `vestibot`)                         |
| `OPENAI_API_KEY`             | ✅          | Chave de API da OpenAI                                      |
| `OPENAI_CHAT_MODEL`          |             | Modelo de chat (padrão: `gpt-4o-mini`)                      |
| `OPENAI_EMBEDDING_MODEL`     |             | Modelo de embeddings (padrão: `text-embedding-3-small`)     |
| `RATE_LIMIT_REQUESTS`        |             | Máx. de perguntas por usuário na janela (padrão: 5)         |
| `RATE_LIMIT_WINDOW_SECONDS`  |             | Duração da janela de rate limit em segundos (padrão: 60)    |
| `MONGO_ROOT_USERNAME`        |             | Usuário admin do container Mongo local (docker-compose)     |
| `MONGO_ROOT_PASSWORD`        |             | Senha admin do container Mongo local (docker-compose)       |

## Limitações conhecidas / próximos passos

- O rate limiter é em memória por processo; em um deploy com múltiplas
  réplicas, o controle deveria migrar para um armazenamento compartilhado
  (Redis, por exemplo).
- Não há suite de testes automatizados ainda.
- `PyMuPDFAdapter` não faz OCR: PDFs digitalizados (imagem) não terão texto
  extraído.
