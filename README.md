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
| POST   | `/api/v1/chat/messages/stream`    | Igual, com a resposta chegando aos pedaços (SSE)     |
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

### Chat em streaming (SSE)

`POST /api/v1/chat/messages/stream` recebe o mesmo corpo de `/chat/messages`, mas
responde `text/event-stream`: o texto aparece conforme o modelo o escreve (o
primeiro pedaço chega em poucos segundos, em vez de esperar a resposta inteira).

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/messages/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "O que é velocidade média?"}'
```

```text
event: meta
data: {"session_id": "8f1c…", "sources": [{"title": "Cinemática - Cap. 1", "subject": "Fisica", "excerpt": "...", "score": 0.91}]}

event: token
data: {"text": "A **velocidade média** "}

event: token
data: {"text": "é a razão entre ..."}

event: done
data: {}
```

- `meta` vem primeiro (a busca nos materiais já terminou); depois, zero ou mais
  `token`; no fim, `done`. Se o modelo cair no meio, em vez de `done` vem
  `event: error` com `{"status": 503, "detail": "..."}`, e **a troca não entra no
  histórico** (respostas interrompidas nunca são gravadas).
- Erros que acontecem *antes* do primeiro byte (422, 429, falha na busca) são
  respostas HTTP normais, como no endpoint clássico. O rate limit é o mesmo.
- Linhas começando com `:` são heartbeat (a cada 15 s) para proxies não derrubarem
  a conexão enquanto o modelo carrega; ignore-as. Atrás de nginx, o header
  `X-Accel-Buffering: no` já é enviado.
- O frontend usa este endpoint por padrão e cai no clássico se a API não o tiver;
  para desligar, `stream: false` em `frontend/config.js`.
- Modelos "thinking" (qwen3, deepseek-r1) não têm o raciocínio transmitido, só a
  resposta final; nesses modelos a espera até o primeiro pedaço é maior.

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

(O frontend pronto está em `frontend/`; veja `frontend/assets/js/api.js` para um cliente completo, com tratamento de erros.)

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

## Frontend

A pasta `frontend/` tem a interface web, em HTML/CSS/JS puro (**sem build, sem
Node**). A própria API a serve na raiz, na mesma origem, então não há CORS para
configurar:

| Endereço                      | O quê                                                   |
|-------------------------------|---------------------------------------------------------|
| `http://localhost:8000/`      | Tutor: o aluno escolhe a matéria e conversa             |
| `http://localhost:8000/admin/`| Área do professor: envia PDFs (pede a `ADMIN_API_KEY`)  |

O que o aluno encontra: perguntas de exemplo para começar, filtro por matéria,
respostas que aparecem enquanto são escritas (streaming, com botão **Parar**), em
Markdown com fórmulas (KaTeX), fontes recolhíveis, atalhos de
continuação ("Explique de outro jeito", "Dê um exemplo"), conversa que continua
depois de recarregar a página, aviso de limite de perguntas com contagem
regressiva e mensagens de erro em português com "Tentar de novo". Funciona no
celular, em modo claro/escuro e com teclado/leitor de tela.

As bibliotecas (marked, DOMPurify, KaTeX) ficam em `frontend/assets/vendor/`
(licenças em `THIRD_PARTY.md`), então a interface funciona sem internet. A
resposta da IA é sanitizada antes de ir para a página.

**Hospedar o frontend separado da API** (Vercel, Netlify...): edite
`apiBase` em `frontend/config.js`, coloque o endereço do frontend em
`CORS_ALLOW_ORIGINS` e, se quiser, desligue o serviço da pasta na API com
`SERVE_FRONTEND=false`.

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
| `SERVE_FRONTEND`            |             | Serve `frontend/` em `/` (padrão: `true`)                           |
| `EMBEDDING_QUERY_PREFIX`    |             | Prefixo das perguntas na busca (ex.: `search_query:`). Vazio = nenhum |
| `EMBEDDING_DOCUMENT_PREFIX` |             | Prefixo dos textos ingeridos (ex.: `search_document:`). Vazio = nenhum |
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
uv run pytest                                  # backend (e E2E, se o Playwright estiver instalado)
node --test "tests/frontend/*.test.mjs"        # unidade do frontend (Node 20+, sem dependências)
```

O backend usa repositórios e IA falsos (não precisa de Mongo nem Ollama) e
cobre endpoints, validações, rate limit, autenticação admin, upload, CORS, o
adaptador do Ollama (transporte HTTP simulado), a busca com contexto da
conversa, o pipeline do `$vectorSearch`, o middleware de erros e o serviço do
frontend.

**E2E do frontend** (opcional): abrem a interface num Chromium de verdade contra
um servidor de simulação (`tests/e2e/mock_server.py`, só biblioteca padrão) que
reproduz o contrato da API, incluindo 429, 503, 500 e proxy devolvendo HTML.
Sem o Playwright instalado, eles são pulados:

```bash
uv add --dev playwright && uv run playwright install chromium
uv run pytest tests/e2e
```

## Prefixos de embedding (melhora a busca com o nomic-embed-text)

O `nomic-embed-text` foi treinado para receber `search_document:` antes dos textos
guardados e `search_query:` antes das perguntas. Com os prefixos, a busca costuma
trazer trechos mais relevantes. Por padrão eles ficam **desligados**, para não
invalidar o que você já ingeriu.

Para ligar (os dois, sempre juntos), no `.env`:

```bash
EMBEDDING_QUERY_PREFIX=search_query:
EMBEDDING_DOCUMENT_PREFIX=search_document:
```

> ⚠️ **Depois de mudar, reingira todos os PDFs.** Os vetores já gravados foram feitos
> sem prefixo; misturá-los com perguntas *com* prefixo não dá erro, só piora a busca
> em silêncio.

```bash
uv run python -m scripts.ingest_bulks_pdf     # reingere data/raw_pdfs/ (substitui os chunks antigos)
uv run python -m scripts.check_embeddings     # confirma: "Tudo certo" (sai com código 1 se não)
```

Para não depender de memória, cada chunk guarda com qual modelo/prefixo foi vetorizado
(`metadata.embedding_model` e `metadata.embedding_document_prefix`). Na inicialização a
API compara isso com a configuração atual e escreve um aviso no log se houver chunks
desatualizados, ou se só um dos dois prefixos estiver configurado. Chunks ingeridos antes
desta versão (sem registro) contam como "sem prefixo". Se algo ficar pior, desligue os
prefixos e reingira de novo. O mesmo vale ao trocar `OLLAMA_EMBEDDING_MODEL`.

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
- O rate limit é por IP: numa escola ou cursinho todos os alunos compartilham o
  mesmo IP de saída. Ajuste `RATE_LIMIT_REQUESTS` para o tamanho das turmas.
- O rate limiter é em memória por processo; com várias réplicas, migre para Redis.
- `PyMuPDFAdapter` não faz OCR: PDFs digitalizados não geram texto.
- O driver `motor` está depreciado (fim do suporte previsto para maio/2027);
  migrar para a API assíncrona nativa do PyMongo.
- Os prefixos do `nomic-embed-text` são opcionais e vêm desligados (ver a seção
  *Prefixos de embedding*); ligá-los exige reingerir os PDFs.
