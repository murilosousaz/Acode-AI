import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createClient, parseRetryAfter, validationMessage } from "../../frontend/assets/js/api.js";

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

function clientWith(handler, options = {}) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init, body: init.body && typeof init.body === "string" ? JSON.parse(init.body) : init.body });
    return handler(url, init, calls.length);
  };
  return { client: createClient({ fetchImpl, ...options }), calls };
}

const rejects = (promise, kind) =>
  assert.rejects(promise, (error) => {
    assert.ok(error instanceof ApiError, `esperava ApiError, veio ${error}`);
    assert.equal(error.kind, kind);
    return true;
  });

const OK_ANSWER = { session_id: "8f1c2e1e-3b0e-4a43-9d35-0c1f0f8f2a77", answer: "**Resposta**", sources: [] };

// ---------------------------------------------------------------- sendMessage
test("sendMessage monta o corpo certo e omite subject/session_id vazios", async () => {
  const { client, calls } = clientWith(() => json(200, OK_ANSWER));
  await client.sendMessage({ question: "Oi?", subject: "", sessionId: null });
  assert.equal(calls[0].url, "/api/v1/chat/messages");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(calls[0].body, { question: "Oi?" });

  await client.sendMessage({ question: "Oi?", subject: "Fisica", sessionId: OK_ANSWER.session_id });
  assert.deepEqual(calls[1].body, { question: "Oi?", subject: "Fisica", session_id: OK_ANSWER.session_id });
});

test("sendMessage normaliza a resposta e as fontes", async () => {
  const body = { ...OK_ANSWER, sources: [{ title: "Cinemática", subject: "Fisica", excerpt: "texto", score: 0.91 }, { excerpt: "x" }] };
  const { client } = clientWith(() => json(200, body));
  const result = await client.sendMessage({ question: "q" });
  assert.equal(result.sessionId, OK_ANSWER.session_id);
  assert.equal(result.answer, "**Resposta**");
  assert.deepEqual(result.sources[0], { title: "Cinemática", subject: "Fisica", excerpt: "texto", score: 0.91 });
  assert.equal(result.sources[1].title, "Material"); // campos ausentes ganham padrão
});

test("baseUrl é prefixado (front hospedado separado) e barras finais são removidas", async () => {
  const { client, calls } = clientWith(() => json(200, OK_ANSWER), { baseUrl: "http://localhost:8000/" });
  await client.sendMessage({ question: "q" });
  assert.equal(calls[0].url, "http://localhost:8000/api/v1/chat/messages");
});

// ---------------------------------------------------------------- erros HTTP
test("429 → rate_limit com Retry-After", async () => {
  const { client } = clientWith(() => json(429, { detail: "Limite..." }, { "Retry-After": "23" }));
  await assert.rejects(client.sendMessage({ question: "q" }), (e) => {
    assert.equal(e.kind, "rate_limit");
    assert.equal(e.retryAfter, 23);
    assert.match(e.hint, /23s/);
    assert.ok(e.retryable);
    return true;
  });
});

test("Retry-After ausente, inválido ou absurdo é saneado", () => {
  assert.equal(parseRetryAfter(null), 30);
  assert.equal(parseRetryAfter("abc"), 30);
  assert.equal(parseRetryAfter("0"), 30);
  assert.equal(parseRetryAfter("7"), 7);
  assert.equal(parseRetryAfter("999999"), 600);
});

test("503 usa a mensagem do servidor quando existe", async () => {
  const { client } = clientWith(() => json(503, { detail: "O serviço de IA está indisponível no momento." }));
  await assert.rejects(client.sendMessage({ question: "q" }), (e) => {
    assert.equal(e.kind, "unavailable");
    assert.equal(e.hint, "O serviço de IA está indisponível no momento.");
    return true;
  });
});

test("500 do servidor → server, sem expor o texto técnico", async () => {
  const { client } = clientWith(() => json(500, { detail: "Erro interno do servidor." }));
  await assert.rejects(client.sendMessage({ question: "q" }), (e) => {
    assert.equal(e.kind, "server");
    assert.equal(e.retryable, true);
    return true;
  });
});

test("502/504 de proxy com HTML (não é JSON) → server", async () => {
  const { client } = clientWith(() => new Response("<html>Bad Gateway</html>", { status: 502 }));
  await rejects(client.sendMessage({ question: "q" }), "server");
});

test("200 com corpo que não é JSON (base errada devolvendo HTML) → unexpected", async () => {
  const { client } = clientWith(() => new Response("<html>index</html>", { status: 200 }));
  await rejects(client.sendMessage({ question: "q" }), "unexpected");
});

test("200 com formato inválido ou resposta vazia → unexpected", async () => {
  await rejects(clientWith(() => json(200, { session_id: "x" })).client.sendMessage({ question: "q" }), "unexpected");
  await rejects(clientWith(() => json(200, { ...OK_ANSWER, answer: "   " })).client.sendMessage({ question: "q" }), "unexpected");
});

test("404 → not_found aponta para config.js", async () => {
  const { client } = clientWith(() => json(404, { detail: "Not Found" }), { baseUrl: "http://x:1" });
  await assert.rejects(client.sendMessage({ question: "q" }), (e) => {
    assert.equal(e.kind, "not_found");
    assert.match(e.hint, /config\.js/);
    assert.match(e.hint, /http:\/\/x:1/);
    return true;
  });
});

test("422 do FastAPI vira frase para o aluno", async () => {
  const tooLong = [{ type: "string_too_long", loc: ["body", "question"], msg: "x", ctx: { max_length: 2000 } }];
  const { client } = clientWith(() => json(422, { detail: tooLong }));
  await assert.rejects(client.sendMessage({ question: "q" }), (e) => {
    assert.equal(e.kind, "validation");
    assert.match(e.hint, /2000 caracteres/);
    assert.equal(e.retryable, false);
    return true;
  });
  assert.equal(validationMessage([{ loc: ["body", "subject"], msg: "x" }]), "Matéria inválida. Escolha uma das opções.");
  assert.equal(validationMessage([{ loc: ["body", "question"], type: "value_error", msg: "x" }]), "Escreva sua dúvida antes de enviar.");
  assert.equal(validationMessage("PDF sem texto"), "PDF sem texto");
  assert.equal(validationMessage([]), null);
});

// ---------------------------------------------------------------- rede, timeout, cancelamento
test("falha de rede (fetch rejeita) → network", async () => {
  const { client } = clientWith(() => {
    throw new TypeError("Failed to fetch");
  });
  await rejects(client.sendMessage({ question: "q" }), "network");
});

test("timeout próprio → timeout", async () => {
  const { client } = createFast(() => new Promise(() => {}), { chatTimeoutMs: 20 });
  await rejects(client.sendMessage({ question: "q" }), "timeout");
});

function createFast(handler, options) {
  // fetch que respeita o AbortSignal, como o de verdade
  const fetchImpl = (url, init) =>
    new Promise((resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(Object.assign(new Error("abort"), { name: "AbortError" })));
      handler(url, init).then?.(resolve, reject);
    });
  return { client: createClient({ fetchImpl, ...options }) };
}

test("cancelar pelo usuário → aborted; sinal já cancelado nem chama a rede", async () => {
  const { client } = createFast(() => new Promise(() => {}));
  const controller = new AbortController();
  const pending = client.sendMessage({ question: "q" }, { signal: controller.signal });
  controller.abort();
  await rejects(pending, "aborted");

  const { client: c2, calls } = clientWith(() => json(200, OK_ANSWER));
  const done = new AbortController();
  done.abort();
  await rejects(c2.sendMessage({ question: "q" }, { signal: done.signal }), "aborted");
  assert.equal(calls.length, 0);
});

// ---------------------------------------------------------------- demais endpoints
test("listSubjects filtra itens inválidos e usa value como label padrão", async () => {
  const { client } = clientWith(() => json(200, [{ value: "Fisica", label: "Física" }, { value: "Geral" }, { label: "sem value" }]));
  assert.deepEqual(await client.listSubjects(), [
    { value: "Fisica", label: "Física" },
    { value: "Geral", label: "Geral" },
  ]);
});

test("clearSession aceita 204 sem corpo e escapa o id", async () => {
  const { client, calls } = clientWith(() => new Response(null, { status: 204 }));
  await client.clearSession("a/b");
  assert.equal(calls[0].url, "/api/v1/chat/sessions/a%2Fb");
  assert.equal(calls[0].init.method, "DELETE");
});

test("readiness: 503 = não pronto (sem lançar); rede fora = lança network", async () => {
  assert.deepEqual(await clientWith(() => json(200, { status: "ready", checks: { mongodb: "ok" } })).client.readiness(), {
    ready: true,
    checks: { mongodb: "ok" },
  });
  assert.equal((await clientWith(() => json(503, { status: "unavailable", checks: {} })).client.readiness()).ready, false);
  await rejects(
    clientWith(() => {
      throw new TypeError("x");
    }).client.readiness(),
    "network",
  );
});

test("uploadDocument envia multipart com a chave no header X-API-Key", async () => {
  const { client, calls } = clientWith(() => json(201, { title: "T", subject: "Fisica", filename: "a.pdf", chunks_created: 12 }));
  const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "a.pdf", { type: "application/pdf" });
  const result = await client.uploadDocument({ file, subject: "Fisica", title: "T", apiKey: "segredo" });
  assert.equal(result.chunks_created, 12);
  assert.equal(calls[0].init.headers["X-API-Key"], "segredo");
  assert.equal(calls[0].init.headers["Content-Type"], undefined); // o navegador define o boundary
  assert.equal(calls[0].body.get("subject"), "Fisica");
  assert.equal(calls[0].body.get("file").name, "a.pdf");
});

test("upload: 401, 413, 415 e 422 viram tipos próprios", async () => {
  const run = (status, body) =>
    clientWith(() => json(status, body)).client.uploadDocument({ file: new File(["x"], "a.pdf"), subject: "Geral", title: "t", apiKey: "k" });
  await rejects(run(401, { detail: "Chave de API inválida ou ausente." }), "unauthorized");
  await rejects(run(413, { detail: "Arquivo maior que o limite de 25 MB." }), "too_large");
  await rejects(run(415, { detail: "não é PDF" }), "not_pdf");
  await assert.rejects(run(422, { detail: "Nenhum texto extraível no PDF (provavelmente é digitalizado)." }), (e) => {
    assert.equal(e.kind, "validation");
    assert.match(e.hint, /digitalizado/);
    return true;
  });
});
