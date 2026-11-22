// Cliente da API do AcodeAI. Sem dependências de DOM: roda no navegador e no Node (testes).

export const API_PREFIX = "/api/v1";
export const MAX_QUESTION_CHARS = 2000;

// O servidor espera até OLLAMA_TIMEOUT_SECONDS (180s) pelo modelo; aqui esperamos um pouco mais
// para o erro do servidor chegar antes do nosso timeout.
export const DEFAULT_CHAT_TIMEOUT_MS = 200_000;
export const DEFAULT_UPLOAD_TIMEOUT_MS = 15 * 60_000;

const RETRY_AFTER_DEFAULT_S = 30;
const RETRY_AFTER_MAX_S = 600;

/** Erro de chamada à API. `kind` diz o que aconteceu; `title`/`hint` são textos prontos para o aluno. */
export class ApiError extends Error {
  constructor(kind, { status = 0, detail = null, retryAfter = null, base = "" } = {}) {
    const { title, hint } = describe(kind, { detail, retryAfter, base });
    super(`${title}. ${hint}`);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter; // segundos (só em rate_limit)
    this.title = title;
    this.hint = hint;
  }

  /** Vale oferecer "Tentar de novo" com a mesma entrada? */
  get retryable() {
    return ["network", "timeout", "interrupted", "unavailable", "server", "rate_limit", "aborted", "unexpected"].includes(this.kind);
  }
}

function describe(kind, { detail, retryAfter, base }) {
  const text = typeof detail === "string" ? detail : null;
  switch (kind) {
    case "network":
      return {
        title: "Sem conexão com o servidor",
        hint: "Confira sua internet (ou se o AcodeAI está rodando) e tente de novo.",
      };
    case "timeout":
      return {
        title: "A resposta demorou demais",
        hint: "O tutor não respondeu a tempo. Tente de novo; perguntas mais curtas costumam ser mais rápidas.",
      };
    case "interrupted":
      return {
        title: "A resposta foi interrompida",
        hint: "A conexão caiu antes de a resposta terminar. Tente de novo.",
      };
    case "aborted":
      return { title: "Pergunta cancelada", hint: "Você pode enviar de novo quando quiser." };
    case "rate_limit":
      return {
        title: "Muitas perguntas seguidas",
        hint: `Dá para perguntar de novo em ${retryAfter ?? RETRY_AFTER_DEFAULT_S}s.`,
      };
    case "unavailable":
      return {
        title: "Tutor indisponível agora",
        hint: text ?? "O serviço de IA está fora do ar ou iniciando. Tente de novo em instantes.",
      };
    case "unauthorized":
      return { title: "Chave de administrador incorreta", hint: "Confira a chave e tente de novo." };
    case "too_large":
      return { title: "Arquivo grande demais", hint: text ?? "O servidor recusou o arquivo por causa do tamanho." };
    case "not_pdf":
      return { title: "Isso não é um PDF", hint: "Envie um arquivo PDF válido." };
    case "validation":
      return { title: "Não foi possível enviar", hint: text ?? "Confira os dados e tente de novo." };
    case "not_found":
      return {
        title: "API não encontrada",
        hint: `Não achei o servidor em "${base || "este endereço"}". Confira o endereço em frontend/config.js.`,
      };
    case "unexpected":
      return {
        title: "Resposta inesperada do servidor",
        hint: "O servidor respondeu em um formato desconhecido. Tente de novo.",
      };
    default:
      return {
        title: "Algo falhou no servidor",
        hint: "Isso não foi culpa sua. Tente de novo; se continuar, avise quem administra o AcodeAI.",
      };
  }
}

/** Converte o `detail` de validação do FastAPI (lista) em uma frase para o aluno. */
export function validationMessage(detail) {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const first = detail[0] ?? {};
  const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
  if (field === "question") {
    if (first.type === "string_too_long") {
      return `Sua pergunta passou de ${first.ctx?.max_length ?? MAX_QUESTION_CHARS} caracteres. Resuma um pouco.`;
    }
    return "Escreva sua dúvida antes de enviar.";
  }
  if (field === "subject") return "Matéria inválida. Escolha uma das opções.";
  if (field === "title") return "Informe um título para o material.";
  if (field === "file") return "Escolha um arquivo PDF.";
  return typeof first.msg === "string" ? first.msg : null;
}

export function parseRetryAfter(value) {
  const seconds = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(seconds) || seconds < 1) return RETRY_AFTER_DEFAULT_S;
  return Math.min(seconds, RETRY_AFTER_MAX_S);
}

/** Traduz uma resposta HTTP de erro em ApiError. `body` é o JSON já lido (ou null). */
export function errorFromResponse(response, body, { base = "" } = {}) {
  const status = response.status;
  const detail = body && typeof body === "object" ? body.detail : null;
  const options = { status, base };

  if (status === 429) {
    const retryAfter = parseRetryAfter(response.headers?.get?.("Retry-After"));
    return new ApiError("rate_limit", { ...options, detail, retryAfter });
  }
  if (status === 401 || status === 403) return new ApiError("unauthorized", { ...options, detail });
  if (status === 404) return new ApiError("not_found", { ...options, detail });
  if (status === 413) return new ApiError("too_large", { ...options, detail });
  if (status === 415) return new ApiError("not_pdf", { ...options, detail });
  if (status === 503) return new ApiError("unavailable", { ...options, detail });
  if (status === 400 || status === 422) {
    return new ApiError("validation", { ...options, detail: validationMessage(detail) });
  }
  return new ApiError("server", { ...options, detail });
}

/**
 * Leitor incremental de Server-Sent Events. `feed(texto)` aceita pedaços em qualquer ponto
 * (inclusive no meio de um evento) e chama `onEvent(nome, dados)` a cada evento completo.
 * Comentários (linhas iniciadas por ":", usadas como heartbeat) são ignorados.
 */
export function createSSEParser(onEvent) {
  let buffer = "";
  return {
    feed(chunk) {
      buffer += chunk;
      let held = "";
      if (buffer.endsWith("\r")) {
        // Um "\r" no fim pode ser a metade de um "\r\n" que chega no próximo pedaço.
        held = "\r";
        buffer = buffer.slice(0, -1);
      }
      buffer = buffer.replace(/\r\n/g, "\n");

      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, end);
        buffer = buffer.slice(end + 2);
        dispatch(block, onEvent);
      }
      buffer += held;
    },
  };
}

function dispatch(block, onEvent) {
  let name = null;
  const data = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  if (name !== null || data.length > 0) onEvent(name ?? "message", data.join("\n"));
}

function normalizeSources(sources) {
  return (Array.isArray(sources) ? sources : []).map((s) => ({
    title: s.title ?? "Material",
    subject: s.subject ?? "",
    excerpt: s.excerpt ?? "",
    score: s.score ?? null,
  }));
}

/**
 * Cria o cliente. `fetchImpl` e `baseUrl` são injetáveis (testes, front hospedado à parte).
 * baseUrl "" = mesma origem da página (o caso normal: a API serve o front).
 */
export function createClient({ baseUrl = "", fetchImpl, chatTimeoutMs = DEFAULT_CHAT_TIMEOUT_MS } = {}) {
  const base = String(baseUrl || "").replace(/\/+$/, "");
  const doFetch = fetchImpl ?? ((...args) => globalThis.fetch(...args));
  let streamSupported = true;

  function fetchFailure(error, { timedOut, signal }) {
    if (timedOut) return new ApiError("timeout");
    if (error?.name === "AbortError" || signal?.aborted) return new ApiError("aborted");
    return new ApiError("network");
  }

  // Mesmo contrato do streaming, usando o endpoint clássico: entrega tudo de uma vez.
  async function viaClassicEndpoint(input, { signal, onMeta, onToken }) {
    const result = await client.sendMessage(input, { signal });
    onMeta?.({ sessionId: result.sessionId, sources: result.sources });
    onToken?.(result.answer);
    return result;
  }

  async function request(path, { method = "GET", json, form, headers = {}, signal, timeoutMs = 30_000 } = {}) {
    if (signal?.aborted) throw new ApiError("aborted");

    const controller = new AbortController();
    let timedOut = false;
    const onAbort = () => controller.abort();
    signal?.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    const init = { method, headers: { ...headers }, signal: controller.signal };
    if (json !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(json);
    } else if (form) {
      init.body = form; // o navegador define o boundary do multipart
    }

    try {
      let response;
      let text = "";
      try {
        response = await doFetch(`${base}${path}`, init);
        text = response.status === 204 ? "" : await response.text();
      } catch (error) {
        if (timedOut) throw new ApiError("timeout");
        if (error?.name === "AbortError" || signal?.aborted) throw new ApiError("aborted");
        throw new ApiError("network");
      }

      let body = null;
      if (text) {
        try {
          body = JSON.parse(text);
        } catch {
          body = null; // ex.: página HTML de erro de um proxy (502/504)
        }
      }

      if (!response.ok) throw errorFromResponse(response, body, { base });
      if (response.status !== 204 && body === null) throw new ApiError("unexpected", { status: response.status });
      return body;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
  }

  const client = {
    baseUrl: base,

    async listSubjects({ signal } = {}) {
      const data = await request(`${API_PREFIX}/subjects`, { signal });
      if (!Array.isArray(data)) throw new ApiError("unexpected");
      return data.filter((s) => s && typeof s.value === "string").map((s) => ({ value: s.value, label: s.label ?? s.value }));
    },

    /** Devolve { sessionId, answer, sources[] }. `subject`/`sessionId` vazios são omitidos. */
    async sendMessage({ question, subject, sessionId }, { signal } = {}) {
      const payload = { question };
      if (subject) payload.subject = subject;
      if (sessionId) payload.session_id = sessionId;

      const data = await request(`${API_PREFIX}/chat/messages`, {
        method: "POST",
        json: payload,
        signal,
        timeoutMs: chatTimeoutMs,
      });
      if (typeof data?.answer !== "string" || !data.answer.trim() || !Array.isArray(data.sources)) {
        throw new ApiError("unexpected");
      }
      return {
        sessionId: data.session_id ?? sessionId ?? null,
        answer: data.answer,
        sources: normalizeSources(data.sources),
      };
    },

    /**
     * Como sendMessage, mas a resposta chega aos pedaços (SSE): `onMeta({ sessionId, sources })`
     * uma vez, `onToken(texto)` a cada pedaço. Devolve o mesmo { sessionId, answer, sources }.
     * O limite de tempo vale entre pedaços (silêncio), não para a resposta inteira.
     * Se a API não tiver o endpoint de streaming (404/405), cai no endpoint clássico — e lembra disso.
     */
    async streamMessage({ question, subject, sessionId }, { signal, onMeta, onToken } = {}) {
      if (!streamSupported) return viaClassicEndpoint({ question, subject, sessionId }, { signal, onMeta, onToken });
      if (signal?.aborted) throw new ApiError("aborted");

      const payload = { question };
      if (subject) payload.subject = subject;
      if (sessionId) payload.session_id = sessionId;

      const controller = new AbortController();
      let timedOut = false;
      let timer;
      const arm = () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, chatTimeoutMs);
      };
      const onAbort = () => controller.abort();
      signal?.addEventListener("abort", onAbort, { once: true });
      arm();

      const result = { sessionId: sessionId ?? null, answer: "", sources: [] };
      let finished = false;
      let streamError = null;
      let received = false;

      const parser = createSSEParser((name, raw) => {
        let data = {};
        try {
          data = raw ? JSON.parse(raw) : {};
        } catch {
          return; // evento ilegível: ignora
        }
        if (name === "meta") {
          result.sessionId = data.session_id ?? result.sessionId;
          result.sources = normalizeSources(data.sources);
          onMeta?.({ sessionId: result.sessionId, sources: result.sources });
        } else if (name === "token" && typeof data.text === "string") {
          received = true;
          result.answer += data.text;
          onToken?.(data.text);
        } else if (name === "done") {
          finished = true;
        } else if (name === "error") {
          streamError = new ApiError(data.status === 503 ? "unavailable" : "server", { status: data.status ?? 0, detail: data.detail });
        }
      });

      try {
        let response;
        try {
          response = await doFetch(`${base}${API_PREFIX}/chat/messages/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
            body: JSON.stringify(payload),
            signal: controller.signal,
          });
        } catch (error) {
          throw fetchFailure(error, { timedOut, signal });
        }

        if (response.status === 404 || response.status === 405) {
          streamSupported = false; // API sem streaming: usa o endpoint clássico daqui em diante
          return viaClassicEndpoint({ question, subject, sessionId }, { signal, onMeta, onToken });
        }
        if (!response.ok) {
          const text = await response.text().catch(() => "");
          let body = null;
          try {
            body = text ? JSON.parse(text) : null;
          } catch {
            body = null;
          }
          throw errorFromResponse(response, body, { base });
        }
        if (!(response.headers.get("Content-Type") ?? "").includes("text/event-stream")) {
          throw new ApiError("unexpected", { status: response.status });
        }

        try {
          if (response.body?.getReader) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            for (;;) {
              const { done, value } = await reader.read();
              if (done) break;
              arm(); // chegou algo (inclusive heartbeat): recomeça a contagem de silêncio
              parser.feed(decoder.decode(value, { stream: true }));
            }
            parser.feed(decoder.decode());
          } else {
            parser.feed(await response.text());
          }
        } catch (error) {
          if (error instanceof ApiError) throw error;
          const failure = fetchFailure(error, { timedOut, signal });
          // A conexão caiu no meio, depois de já termos recebido texto.
          throw failure.kind === "network" && received ? new ApiError("interrupted") : failure;
        }

        if (streamError) throw streamError;
        if (!finished) throw new ApiError(received ? "interrupted" : "network");
        if (!result.answer.trim()) throw new ApiError("unexpected");
        return result;
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener("abort", onAbort);
      }
    },

    async getHistory(sessionId, { signal } = {}) {
      const data = await request(`${API_PREFIX}/chat/sessions/${encodeURIComponent(sessionId)}`, { signal });
      return Array.isArray(data?.messages) ? data.messages : [];
    },

    async clearSession(sessionId) {
      await request(`${API_PREFIX}/chat/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    },

    /** Resultado de /health/ready: { ready: boolean, checks }. Rede fora do ar lança ApiError("network"). */
    async readiness({ signal } = {}) {
      try {
        const data = await request("/health/ready", { signal, timeoutMs: 10_000 });
        return { ready: true, checks: data?.checks ?? {} };
      } catch (error) {
        if (error instanceof ApiError && error.kind === "unavailable") return { ready: false, checks: {} };
        throw error;
      }
    },

    /** Área do professor: envia um PDF. A chave admin vai no header e nunca é guardada. */
    async uploadDocument({ file, subject, title, apiKey }, { signal } = {}) {
      const form = new FormData();
      form.append("file", file);
      form.append("subject", subject);
      form.append("title", title);
      return request(`${API_PREFIX}/documents`, {
        method: "POST",
        form,
        headers: { "X-API-Key": apiKey },
        signal,
        timeoutMs: DEFAULT_UPLOAD_TIMEOUT_MS,
      });
    },
  };
  return client;
}
