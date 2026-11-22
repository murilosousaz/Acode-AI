import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createClient, createSSEParser } from "../../frontend/assets/js/api.js";

const enc = new TextEncoder();
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const META = frame("meta", { session_id: "sess-1", sources: [{ title: "Cinemática", subject: "Fisica", excerpt: "x", score: 0.9 }] });
const tok = (text) => frame("token", { text });

/** Resposta SSE cujo corpo é entregue pelos pedaços dados (strings ou bytes), na ordem. */
function sseResponse(chunks, { status = 200, headers = {} } = {}) {
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? enc.encode(chunk) : chunk);
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream", ...headers } });
}

const json = (status, body, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

function clientWith(handler, options = {}) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init, body: typeof init.body === "string" ? JSON.parse(init.body) : init.body });
    return handler(url, init, calls.length);
  };
  return { client: createClient({ fetchImpl, ...options }), calls };
}

const run = (client, extra = {}) => {
  const seen = { meta: [], tokens: [] };
  const promise = client.streamMessage(
    { question: "q", subject: "Fisica", sessionId: null },
    { onMeta: (m) => seen.meta.push(m), onToken: (t) => seen.tokens.push(t), ...extra },
  );
  return { promise, seen };
};

const rejectsKind = (promise, kind) =>
  assert.rejects(promise, (e) => {
    assert.ok(e instanceof ApiError, `esperava ApiError, veio ${e}`);
    assert.equal(e.kind, kind);
    return true;
  });

// ---------------------------------------------------------------- parser
function parse(chunks) {
  const events = [];
  const parser = createSSEParser((name, data) => events.push([name, data]));
  for (const chunk of chunks) parser.feed(chunk);
  return events;
}

test("parser: eventos completos, comentários ignorados, vários eventos num pedaço", () => {
  assert.deepEqual(parse([`: ping\n\nevent: a\ndata: 1\n\nevent: b\ndata: 2\n\n`]), [["a", "1"], ["b", "2"]]);
});

test("parser: evento partido em qualquer ponto (até no meio da palavra)", () => {
  const whole = "event: token\ndata: {\"text\": \"olá\"}\n\n";
  for (let cut = 1; cut < whole.length; cut++) {
    assert.deepEqual(parse([whole.slice(0, cut), whole.slice(cut)]), [["token", '{"text": "olá"}']], `corte em ${cut}`);
  }
});

test("parser: CRLF, inclusive com \\r e \\n em pedaços diferentes", () => {
  assert.deepEqual(parse(["event: a\r\ndata: 1\r\n\r\n"]), [["a", "1"]]);
  assert.deepEqual(parse(["event: a\r\ndata: 1\r", "\n\r", "\n"]), [["a", "1"]]);
});

test("parser: várias linhas data são unidas com \\n; evento sem nome vira 'message'", () => {
  assert.deepEqual(parse(["data: linha1\ndata: linha2\n\n"]), [["message", "linha1\nlinha2"]]);
});

test("parser: evento incompleto no fim não é entregue", () => {
  assert.deepEqual(parse(["event: a\ndata: 1\n\nevent: b\ndata: 2"]), [["a", "1"]]);
});

// ---------------------------------------------------------------- streamMessage
test("entrega meta e tokens na ordem e devolve o resultado completo", async () => {
  const { client, calls } = clientWith(() => sseResponse([META, tok("A velocidade "), tok("média."), frame("done", {})]));
  const { promise, seen } = run(client);
  const result = await promise;

  assert.equal(calls[0].url, "/api/v1/chat/messages/stream");
  assert.equal(calls[0].init.headers.Accept, "text/event-stream");
  assert.deepEqual(calls[0].body, { question: "q", subject: "Fisica" }); // session_id vazio é omitido
  assert.deepEqual(seen.tokens, ["A velocidade ", "média."]);
  assert.equal(seen.meta.length, 1);
  assert.deepEqual(result, {
    sessionId: "sess-1",
    answer: "A velocidade média.",
    sources: [{ title: "Cinemática", subject: "Fisica", excerpt: "x", score: 0.9 }],
  });
});

test("caractere UTF-8 partido ao meio entre dois pedaços de rede chega inteiro", async () => {
  const bytes = enc.encode(META + tok("ação ✓ 😀") + frame("done", {}));
  const cut = bytes.indexOf(0xc3) + 1; // no meio do "ç" (2 bytes)
  const { client } = clientWith(() => sseResponse([bytes.slice(0, cut), bytes.slice(cut)]));
  assert.equal((await run(client).promise).answer, "ação ✓ 😀");
});

test("heartbeat (comentário) no meio não atrapalha", async () => {
  const { client } = clientWith(() => sseResponse([META, ": ping\n\n", tok("ok"), ": ping\n\n", frame("done", {})]));
  assert.equal((await run(client).promise).answer, "ok");
});

test("erros antes do stream continuam sendo HTTP normal (429, 503, 422, 500)", async () => {
  const kinds = [
    [json(429, { detail: "x" }, { "Retry-After": "7" }), "rate_limit"],
    [json(503, { detail: "IA fora" }), "unavailable"],
    [json(422, { detail: [{ loc: ["body", "question"], type: "string_too_long", ctx: { max_length: 2000 } }] }), "validation"],
    [json(500, { detail: "Erro interno do servidor." }), "server"],
    [new Response("<html>502</html>", { status: 502 }), "server"],
  ];
  for (const [response, kind] of kinds) {
    const { client } = clientWith(() => response);
    await rejectsKind(run(client).promise, kind);
  }
  const limited = clientWith(() => json(429, {}, { "Retry-After": "7" }));
  await assert.rejects(run(limited.client).promise, (e) => e.retryAfter === 7);
});

test("evento error no meio: 503 vira unavailable e traz o texto já recebido só pelos callbacks", async () => {
  const { client } = clientWith(() =>
    sseResponse([META, tok("Começo"), frame("error", { status: 503, detail: "O serviço de IA está indisponível." })]),
  );
  const { promise, seen } = run(client);
  await assert.rejects(promise, (e) => e.kind === "unavailable" && e.hint === "O serviço de IA está indisponível.");
  assert.deepEqual(seen.tokens, ["Começo"]);
});

test("evento error com status 500 → server", async () => {
  const { client } = clientWith(() => sseResponse([META, frame("error", { status: 500, detail: "x" })]));
  await rejectsKind(run(client).promise, "server");
});

test("conexão que acaba sem 'done': com texto = interrupted; sem nada = network", async () => {
  await rejectsKind(run(clientWith(() => sseResponse([META, tok("meio")])).client).promise, "interrupted");
  await rejectsKind(run(clientWith(() => sseResponse([])).client).promise, "network");
});

test("queda de rede durante a leitura", async () => {
  const dropping = () => {
    let pulls = 0;
    const body = new ReadableStream({
      pull(controller) {
        if (pulls++ === 0) controller.enqueue(enc.encode(META + tok("meio")));
        else controller.error(new TypeError("network error")); // cai depois de o texto já ter chegado
      },
    });
    return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
  };
  await rejectsKind(run(clientWith(dropping).client).promise, "interrupted");
});

test("resposta que não é SSE (ex.: JSON de um servidor antigo/proxy) → unexpected", async () => {
  await rejectsKind(run(clientWith(() => json(200, {})).client).promise, "unexpected");
});

test("'done' sem nenhum texto → unexpected", async () => {
  await rejectsKind(run(clientWith(() => sseResponse([META, frame("done", {})])).client).promise, "unexpected");
});

test("fetch que rejeita → network", async () => {
  const { client } = clientWith(() => {
    throw new TypeError("Failed to fetch");
  });
  await rejectsKind(run(client).promise, "network");
});

// ---------------------------------------------------------------- tempo, cancelamento, fallback
function hangingFetch() {
  // fetch que só termina quando abortado, como o de verdade
  return (url, init) =>
    new Promise((resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(Object.assign(new Error("abort"), { name: "AbortError" })));
    });
}

test("silêncio além do limite → timeout", async () => {
  const client = createClient({ fetchImpl: hangingFetch(), chatTimeoutMs: 30 });
  await rejectsKind(run(client).promise, "timeout");
});

test("o limite é de silêncio, não de duração total: pedaços lentos mas contínuos não estouram", async () => {
  const slow = () => {
    let i = 0;
    const parts = [META, tok("a"), tok("b"), tok("c"), tok("d"), frame("done", {})];
    const body = new ReadableStream({
      async pull(controller) {
        if (i >= parts.length) return controller.close();
        await new Promise((r) => setTimeout(r, 40)); // 6 × 40 ms = 240 ms no total, > 100 ms de limite
        controller.enqueue(enc.encode(parts[i++]));
      },
    });
    return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
  };
  const client = createClient({ fetchImpl: async () => slow(), chatTimeoutMs: 100 });
  assert.equal((await run(client).promise).answer, "abcd");
});

test("cancelar pelo usuário → aborted (durante a espera e durante a leitura)", async () => {
  const controller = new AbortController();
  const waiting = createClient({ fetchImpl: hangingFetch() });
  const { promise } = run(waiting, { signal: controller.signal });
  controller.abort();
  await rejectsKind(promise, "aborted");

  const reading = createClient({
    fetchImpl: async (url, init) => {
      const body = new ReadableStream({
        start(c) {
          c.enqueue(enc.encode(META + tok("parcial")));
          init.signal.addEventListener("abort", () => c.error(Object.assign(new Error("abort"), { name: "AbortError" })));
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    },
  });
  const second = new AbortController();
  const run2 = run(reading, { signal: second.signal, onToken: () => second.abort() });
  await rejectsKind(run2.promise, "aborted");

  const done = new AbortController();
  done.abort();
  await rejectsKind(run(clientWith(() => json(200, {})).client, { signal: done.signal }).promise, "aborted");
});

test("API sem streaming (404/405): cai no endpoint clássico, entrega pelos mesmos callbacks e lembra", async () => {
  const classic = { session_id: "sess-9", answer: "Resposta inteira", sources: [{ title: "T", subject: "Geral", excerpt: "e" }] };
  for (const status of [404, 405]) {
    const { client, calls } = clientWith((url) => (url.endsWith("/stream") ? json(status, { detail: "x" }) : json(200, classic)));
    const first = run(client);
    const result = await first.promise;
    assert.equal(result.answer, "Resposta inteira");
    assert.deepEqual(first.seen.tokens, ["Resposta inteira"]);
    assert.equal(first.seen.meta[0].sessionId, "sess-9");
    assert.deepEqual(calls.map((c) => c.url), ["/api/v1/chat/messages/stream", "/api/v1/chat/messages"]);

    await run(client).promise; // segunda pergunta: nem tenta o stream de novo
    assert.deepEqual(calls.slice(2).map((c) => c.url), ["/api/v1/chat/messages"]);
  }
});

test("sinal já cancelado nem chama a rede", async () => {
  const { client, calls } = clientWith(() => sseResponse([META]));
  const done = new AbortController();
  done.abort();
  await rejectsKind(run(client, { signal: done.signal }).promise, "aborted");
  assert.equal(calls.length, 0);
});
