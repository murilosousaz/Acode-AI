# AcodeAI

API REST de um tutor para vestibular (ENEM, FUVEST etc.) que usa RAG
(Retrieval-Augmented Generation): materiais em PDF são indexados como
embeddings no MongoDB Atlas Vector Search e usados como contexto para
respostas geradas por modelos gratuitos rodando localmente via
[Ollama](https://ollama.com). Feita para ser consumida por um frontend.

## Arquitetura

DDD em camadas; as dependências apontam sempre para dentro:

```
src/
├── domain/          # Entidades, value objects, portas (EmbeddingGenerator,
│                    # ChatCompleter), contratos de repositório e regras puras.
├── app/             # Casos de uso e DTOs (responder dúvida, ingerir PDF,
│                    # histórico de conversa). Dependem só do domínio.
├── infrastructure/  # Ollama, MongoDB, PyMuPDF, rate limiter, settings.
├── bootstrap.py     # Raiz de composição: monta o Container de dependências.
└── presentation/
    └── api/         # FastAPI: routers, schemas, dependências, tratamento de erros.
```

## Endpoints

Documentação interativa (Swagger) em `http://localhost:8000/docs`; o
OpenAPI em `/openapi.json` serve para gerar um client tipado no frontend.

| Método | Rota                              | Descrição                                           |
|--------|-----------------------------------|-----------------------------------------------------|
| POST   | `/api/v1/chat/messages`           | Envia uma dúvida e recebe a resposta + fontes        |
| GET    | `/api/v1/chat/sessions/{id}`      | Histórico da conversa                                |
| DELETE | `/api/v1/chat/sessions/{id}`      | Apaga o histórico da conversa (204)                  |
| GET    | `/api/v1/subjects`                | Matérias válidas para o filtro (`value` + `label`)   |
| POST   | `/api/v1/documents`               | **Admin** — envia um PDF para indexação              |
| GET    | `/health`                         | Liveness                                             |
| GET    | `/health/ready`                   | Readiness (MongoDB e Ollama)                         |

### Chat

```bash
curl -X POST http://localhost:8000/api/v1/chat/messages \
  -H "Content-Type: application/json" \
  -d '{"question": "O que é velocidade média?", "subject": "Fisica"}'
```

```json
{
  "session_id": "8f1c2e1e-3b0e-4a43-9d35-0c1f0f8f2a77",
  "answer": "A **velocidade média** é a razão entre ...",
  "sources": [
    {"title": "Cinemática - Cap. 1", "subject": "Fisica", "score": 0.91, "excerpt": "..."}
  ]
}
```

- `session_id` é opcional na primeira pergunta; a API cria um e devolve. O
  frontend deve guardá-lo (ex.: `localStorage`) e reenviá-lo nas perguntas
  seguintes para manter o histórico.
- `subject` é opcional e deve ser um `value` de `GET /subjects`.
- `question`: 1 a 2000 caracteres.
- Limite de perguntas por IP (padrão 5/min): excedido → `429` com header
  `Retry-After`.
- Se o Ollama estiver fora do ar ou sem o modelo → `503`.
- Quando nenhum trecho relevante é encontrado, `answer` traz uma mensagem
  padrão, `sources` vem vazio e a troca não entra no histórico.

### Upload de PDF (admin)

```bash
curl -X POST http://localhost:8000/api/v1/documents \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -F "file=@Fisica_Cinematica.pdf" -F "subject=Fisica" -F "title=Cinemática - Cap. 1"
```

Respostas: `201` (`chunks_created`), `401` chave errada/ausente, `503` se
`ADMIN_API_KEY` não estiver configurada, `413` arquivo grande demais, `415`
não é PDF, `422` matéria inválida ou PDF sem texto extraível. A requisição só
responde ao fim da vetorização, que pode levar de segundos a minutos para PDFs
grandes — use um timeout generoso no frontend e **não exponha a chave admin
no código do navegador** (use um painel admin protegido ou chame por backend).

### Exemplo de consumo no frontend

```ts
const API = "http://localhost:8000/api/v1";

export async function ask(question: string, subject?: string) {
  const sessionId = localStorage.getItem("acodeai:session") ?? undefined;
  const res = await fetch(`${API}/chat/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, subject, session_id: sessionId }),
  });
  if (res.status === 429) throw new Error(`Aguarde ${res.headers.get("Retry-After")}s`);
  if (!res.ok) throw new Error((await res.json()).detail ?? "Erro");
  const data = await res.json();
  localStorage.setItem("acodeai:session", data.session_id);
  return data; // { session_id, answer, sources }
}
```

Erros seguem o formato `{"detail": "..."}` (em erros de validação, `detail` é
uma lista no padrão do FastAPI).

## Pré-requisitos

- Python 3.13 e [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) (ou use o serviço `ollama` do `docker-compose.yml`)
- MongoDB com Atlas Vector Search (o `docker-compose.yml` sobe `mongodb-atlas-local`)

## Rodando localmente

```bash
cp .env.example .env                 # ajuste ADMIN_API_KEY e CORS_ALLOW_ORIGINS
uv sync

ollama pull qwen2.5:7b               # chat
ollama pull nomic-embed-text         # embeddings (768 dimensões)
docker compose up -d mongodb

uv run python -m scripts.create_vector_index    # uma vez, antes da 1ª ingestão
uv run python -m scripts.ingest_cli caminho/arquivo.pdf Fisica "Cinemática - Cap. 1"
# ou em lote: PDFs em data/raw_pdfs/ nomeados Materia_Descricao.pdf
uv run python -m scripts.ingest_bulks_pdf

uv run uvicorn src.presentation.api.main:app --reload
```

## Rodando com Docker

```bash
docker compose up -d --build
```

Sobe MongoDB, Ollama (baixa os modelos na primeira vez) e a API em
`http://localhost:8000`. Dentro do compose a API usa os hosts `mongodb` e
`ollama` automaticamente, sobrescrevendo os `localhost` do `.env`. O Ollama
roda com `OLLAMA_CONTEXT_LENGTH=8192`; rodando o Ollama fora do Docker, suba-o
com `OLLAMA_CONTEXT_LENGTH=8192 ollama serve`, senão o prompt do RAG pode ser
truncado silenciosamente.

Atrás de um proxy reverso, mantenha `--proxy-headers` (já no Dockerfile) para
o rate limit enxergar o IP real do cliente.

## Variáveis de ambiente

| Variável                    | Obrigatória | Descrição                                                          |
|-----------------------------|:-----------:|--------------------------------------------------------------------|
| `MONGO_URI`                 | ✅          | String de conexão do MongoDB                                        |
| `MONGO_DB_NAME`             |             | Nome do banco (padrão: `acode-ai`)                                  |
| `MONGO_ROOT_USERNAME` / `MONGO_ROOT_PASSWORD` | | Credenciais do Mongo local (docker-compose)               |
| `ADMIN_API_KEY`             |             | Chave do header `X-API-Key` para upload de PDFs; vazia = desabilitado |
| `CORS_ALLOW_ORIGINS`        |             | Origens do frontend, separadas por vírgula                          |
| `MAX_UPLOAD_MB`             |             | Tamanho máximo do PDF (padrão: `25`)                                |
| `OLLAMA_BASE_URL`           |             | Endpoint OpenAI-compatível (padrão: `http://localhost:11434/v1`)    |
| `OLLAMA_CHAT_MODEL`         |             | Modelo de chat (padrão: `qwen2.5:7b`)                               |
| `OLLAMA_EMBEDDING_MODEL`    |             | Modelo de embeddings (padrão: `nomic-embed-text`)                   |
| `OLLAMA_MAX_TOKENS`         |             | Limite de tokens da resposta (padrão: `2048`)                       |
| `OLLAMA_TIMEOUT_SECONDS`    |             | Timeout das chamadas ao Ollama (padrão: `180`)                      |
| `EMBEDDING_DIMENSIONS`      |             | Dimensão do vetor; deve bater com o modelo e o índice (padrão: `768`) |
| `RATE_LIMIT_REQUESTS`       |             | Máx. de perguntas por IP na janela (padrão: `5`)                    |
| `RATE_LIMIT_WINDOW_SECONDS` |             | Janela do rate limit em segundos (padrão: `60`)                     |

## Testes

```bash
uv run pytest
```

A suíte usa repositórios e IA falsos (não precisa de Mongo nem Ollama) e
cobre os endpoints, validações, rate limit, autenticação admin, upload, CORS e
o adaptador do Ollama (via transporte HTTP simulado).

## Notas de migração

- **Discord → API:** o bot, os cogs e o `DiscordFormatter` foram removidos. O
  histórico agora é por `session_id` (UUID) em vez do ID de usuário do Discord;
  sessões antigas (campo `user_id`) ficam órfãs na coleção `chat_sessions` e
  podem ser apagadas.
- **Gemini/DeepSeek → Ollama:** os vetores antigos são incompatíveis com o
  `nomic-embed-text`, mesmo com 768 dimensões. Apague a coleção
  `document_chunks` e reingira os PDFs. Se trocar de modelo de embeddings com
  outra dimensão, ajuste `EMBEDDING_DIMENSIONS`, recrie o índice e reingira.
- Metadado `source_path` dos chunks virou `source_file` (só o nome do arquivo,
  sem caminho do servidor).

## Limitações conhecidas / próximos passos

- Sem autenticação de usuários: o `session_id` (UUID não adivinhável) é a única
  proteção de uma conversa. Para contas reais, adicione login/JWT e associe as
  sessões ao usuário.
- A resposta do chat não é transmitida em streaming; com modelos locais ela pode
  levar dezenas de segundos. SSE em `/chat/messages/stream` é o próximo passo
  natural para a UX do frontend.
- O rate limiter é em memória por processo; com várias réplicas, migre para Redis.
- `PyMuPDFAdapter` não faz OCR: PDFs digitalizados não geram texto.
- O driver `motor` está depreciado (fim do suporte previsto para maio/2027);
  migrar para a API assíncrona nativa do PyMongo.
- O `nomic-embed-text` rende melhor com os prefixos `search_document: ` (ingestão)
  e `search_query: ` (pergunta); ainda não aplicados.
