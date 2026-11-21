// Tela de conversa do aluno.

import { ApiError, MAX_QUESTION_CHARS, createClient } from "./api.js";
import {
  EXAMPLES,
  FALLBACK_SUBJECTS,
  FOLLOW_UPS,
  LETTERS,
  MIXED_EXAMPLES,
  SHORT_LABELS,
  SUBJECT_ICONS,
} from "./content.js";
import { copyText, h, isTouchDevice, prefersReducedMotion, sleep } from "./dom.js";
import { renderMarkdown } from "./markdown.js";

const config = window.ACODEAI ?? {};
const client = createClient({ baseUrl: config.apiBase ?? "", chatTimeoutMs: config.chatTimeoutMs });

const KEYS = { session: "acodeai:session", subject: "acodeai:subject", messages: "acodeai:messages" };
const MAX_STORED_MESSAGES = 40;
const COUNTER_FROM = Math.floor(MAX_QUESTION_CHARS * 0.8);
const SLOW_HINT_AFTER_S = 15;

// ------------------------------------------------------------------ persistência (tolerante a falhas)
const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* modo privado / cota cheia: segue sem salvar */
    }
  },
  remove(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* idem */
    }
  },
};

// ------------------------------------------------------------------ estado
const state = {
  sessionId: store.get(KEYS.session, null),
  subject: store.get(KEYS.subject, ""), // "" = todas as matérias
  messages: [], // só trocas concluídas: { role, content, subject?, sources?, question? }
  subjects: FALLBACK_SUBJECTS,
  pending: null, // pergunta enviada e ainda sem resposta: { question, subject, el }
  busy: false,
  controller: null,
  cooldownUntil: 0,
};

// ------------------------------------------------------------------ elementos
const $ = (selector) => document.querySelector(selector);
const el = {
  banner: $("#banner"),
  welcome: $("#welcome"),
  messages: $("#messages"),
  followups: $("#followups"),
  subjects: $("#subjects"),
  form: $("#composer"),
  question: $("#question"),
  send: $("#send"),
  counter: $("#counter"),
  keyHint: $("#key-hint"),
  newChat: $("#new-chat"),
  confirm: $("#confirm"),
  announcer: $("#announcer"),
};

let typing = null; // { node, timer }
let errorCard = null;
let cooldownTimer = null;

const scrollBehavior = () => (prefersReducedMotion() ? "auto" : "smooth");

function labelFor(value) {
  if (!value) return "Todas";
  const found = state.subjects.find((s) => s.value === value);
  return SHORT_LABELS[value] ?? found?.label ?? value;
}

function announce(text) {
  el.announcer.textContent = "";
  setTimeout(() => (el.announcer.textContent = text), 50);
}

// ------------------------------------------------------------------ banner de status
function showBanner(text) {
  el.banner.replaceChildren(
    h("span", {}, text),
    h("button", { class: "banner-close", type: "button", "aria-label": "Fechar aviso", onclick: () => (el.banner.hidden = true) }, "×"),
  );
  el.banner.hidden = false;
}

async function checkReadiness() {
  try {
    const { ready } = await client.readiness();
    if (!ready) {
      showBanner("O tutor está iniciando ou algum serviço (banco de dados ou IA) está fora do ar. Você pode tentar perguntar mesmo assim.");
    }
  } catch (error) {
    const reason = error instanceof ApiError && error.kind === "not_found" ? error.hint : "Não consegui conectar ao servidor do AcodeAI.";
    showBanner(reason);
  }
}

// ------------------------------------------------------------------ matérias
function renderSubjects() {
  const options = [{ value: "", label: "Todas" }, ...state.subjects];
  el.subjects.replaceChildren(
    h("legend", { class: "sr-only" }, "Matéria da pergunta"),
    ...options.map((s) =>
      h(
        "label",
        { class: "chip" },
        h("input", {
          type: "radio",
          name: "subject",
          value: s.value,
          checked: s.value === state.subject,
          onchange: () => chooseSubject(s.value),
        }),
        h("span", { class: "chip-face" }, s.value ? h("span", { "aria-hidden": "true" }, SUBJECT_ICONS[s.value] ?? "📘") : null, labelFor(s.value)),
      ),
    ),
  );
}

function chooseSubject(value) {
  state.subject = value;
  store.set(KEYS.subject, value);
  if (isEmptyConversation()) renderWelcome();
}

async function loadSubjects() {
  try {
    const subjects = await client.listSubjects();
    if (subjects.length === 0) return;
    state.subjects = subjects;
    if (state.subject && !subjects.some((s) => s.value === state.subject)) state.subject = "";
    renderSubjects();
    renderWelcome();
  } catch {
    /* mantém a lista embutida; o erro real aparece ao enviar a pergunta */
  }
}

// ------------------------------------------------------------------ tela inicial
const isEmptyConversation = () => state.messages.length === 0 && !state.pending;

function renderWelcome() {
  el.welcome.hidden = !isEmptyConversation();
  if (el.welcome.hidden) return;

  const subjectExamples = EXAMPLES[state.subject]?.map((text) => ({ subject: state.subject, text }));
  const examples = subjectExamples ?? MIXED_EXAMPLES;

  el.welcome.replaceChildren(
    h("h1", {}, "Qual é a sua dúvida de hoje?"),
    h("p", { class: "lead" }, "Escolha a matéria, escreva a pergunta e eu explico com base nos materiais de estudo. Se não ficar claro, peça de outro jeito."),
    h("p", { class: "examples-label", id: "examples-label" }, "Toque em uma pergunta para começar:"),
    h(
      "ul",
      { class: "examples", "aria-labelledby": "examples-label" },
      examples.map((example, i) =>
        h(
          "li",
          {},
          h(
            "button",
            { class: "example", type: "button", onclick: (event) => chooseExample(event.currentTarget, example.text) },
            h("span", { class: "mark", "aria-hidden": "true" }, LETTERS[i]),
            h("span", { class: "example-text" }, example.text),
            state.subject ? null : h("span", { class: "tag" }, labelFor(example.subject)),
          ),
        ),
      ),
    ),
  );
}

async function chooseExample(button, text) {
  if (state.busy || isCooling()) return;
  button.classList.add("marked"); // a "bolinha" do gabarito é preenchida
  if (!prefersReducedMotion()) await sleep(220);
  ask(text);
}

// ------------------------------------------------------------------ mensagens
function userBubble(question, subject) {
  return h(
    "article",
    { class: "msg msg-user" },
    h("span", { class: "sr-only" }, "Você perguntou: "),
    h("p", { class: "bubble" }, question),
    subject ? h("span", { class: "tag" }, labelFor(subject)) : null,
  );
}

function assistantMessage(message, { latest = false } = {}) {
  const body = h("div", { class: "prose" });
  body.innerHTML = renderMarkdown(message.content); // sanitizado em markdown.js

  const sources = dedupeSources(message.sources ?? []);
  const copy = h("button", { class: "btn-quiet small", type: "button" }, "Copiar");
  copy.addEventListener("click", async () => {
    const ok = await copyText(message.content);
    copy.textContent = ok ? "Copiado!" : "Não deu para copiar";
    announce(ok ? "Resposta copiada." : "Não foi possível copiar.");
    setTimeout(() => (copy.textContent = "Copiar"), 1800);
  });

  return h(
    "article",
    { class: "msg msg-assistant", dataset: { latest: latest ? "true" : "false" } },
    h("span", { class: "sr-only" }, "Resposta do AcodeAI: "),
    body,
    sources.length === 0 && !message.restored ? noContextHelp(message) : null,
    h("div", { class: "msg-actions" }, copy),
    sources.length > 0 ? sourcesBlock(sources) : null,
  );
}

function dedupeSources(sources) {
  const seen = new Set();
  return sources.filter((s) => {
    const key = `${s.title}|${s.excerpt}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function sourcesBlock(sources) {
  return h(
    "details",
    { class: "sources" },
    h("summary", {}, `Fontes (${sources.length})`),
    h(
      "ul",
      {},
      sources.map((s) =>
        h(
          "li",
          {},
          h("span", { class: "source-title" }, s.title),
          s.subject ? h("span", { class: "tag" }, labelFor(s.subject)) : null,
          h("p", { class: "excerpt" }, s.excerpt),
        ),
      ),
    ),
  );
}

// Resposta sem nenhum trecho dos materiais: oferece um caminho em vez de um beco sem saída.
function noContextHelp(message) {
  const widen =
    state.subject && message.question
      ? h("button", { class: "btn-soft", type: "button", onclick: () => ask(message.question, { subject: "" }) }, "Buscar em todas as matérias")
      : null;
  return h("div", { class: "help" }, h("p", {}, "Dica: use as palavras que aparecem nos livros e apostilas (por exemplo, “fotossíntese”)."), widen);
}

function renderFollowups() {
  el.followups.replaceChildren();
  const last = state.messages.at(-1);
  if (state.pending || !last || last.role !== "assistant" || (last.sources ?? []).length === 0) return;
  el.followups.append(
    ...FOLLOW_UPS.map((text) => h("button", { class: "btn-soft", type: "button", disabled: isCooling(), onclick: () => ask(text) }, text)),
  );
}

function renderThread() {
  el.messages.replaceChildren(
    ...state.messages.map((m, i) =>
      m.role === "user" ? userBubble(m.content, m.subject) : assistantMessage(m, { latest: i === state.messages.length - 1 }),
    ),
  );
  if (state.pending) {
    state.pending.el = userBubble(state.pending.question, state.pending.subject);
    el.messages.append(state.pending.el);
  }
  renderWelcome();
  renderFollowups();
}

function scrollToBottom() {
  window.scrollTo({ top: document.documentElement.scrollHeight, behavior: scrollBehavior() });
}

// ------------------------------------------------------------------ indicador de espera
function showTyping() {
  const text = h("span", { class: "typing-text" }, "Pensando…");
  const hint = h("span", { class: "typing-hint" });
  const node = h(
    "div",
    { class: "msg msg-assistant typing", role: "status" },
    h("span", { class: "dots", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    h("span", { class: "typing-body" }, text, hint),
    h("button", { class: "btn-link", type: "button", onclick: cancel }, "Cancelar"),
  );
  el.messages.append(node);
  scrollToBottom();

  const startedAt = Date.now();
  const timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    text.textContent = seconds >= 5 ? `Pensando… ${seconds}s` : "Pensando…";
    if (seconds >= SLOW_HINT_AFTER_S) hint.textContent = "A primeira resposta costuma demorar mais, porque o modelo precisa carregar.";
  }, 1000);
  typing = { node, timer };
}

function hideTyping() {
  if (!typing) return;
  clearInterval(typing.timer);
  typing.node.remove();
  typing = null;
}

function cancel() {
  state.controller?.abort();
}

// ------------------------------------------------------------------ erros
function removeError() {
  errorCard?.remove();
  errorCard = null;
  clearInterval(cooldownTimer);
}

function showError(error, { retry } = {}) {
  removeError();
  const hint = h("p", { class: "error-hint" }, error.hint);
  const actions = h("div", { class: "error-actions" });
  const card = h("div", { class: "msg error", role: "alert" }, h("p", { class: "error-title" }, error.title), hint, actions);

  if (retry && error.retryable) {
    const button = h("button", { class: "btn-soft", type: "button", onclick: retry }, "Tentar de novo");
    actions.append(button);
    if (error.kind === "rate_limit") runCooldown(error.retryAfter, { hint, button });
  }

  errorCard = card;
  el.messages.append(card);
  scrollToBottom();
}

function isCooling() {
  return Date.now() < state.cooldownUntil;
}

function runCooldown(seconds, { hint, button }) {
  state.cooldownUntil = Date.now() + seconds * 1000;
  button.disabled = true;
  updateSendState();

  const tick = () => {
    const remaining = Math.ceil((state.cooldownUntil - Date.now()) / 1000);
    if (remaining > 0) {
      hint.textContent = `Dá para perguntar de novo em ${remaining}s.`;
      return;
    }
    clearInterval(cooldownTimer);
    state.cooldownUntil = 0;
    hint.textContent = "Pronto! Já pode perguntar de novo.";
    button.disabled = false;
    updateSendState();
    renderFollowups();
  };
  tick();
  clearInterval(cooldownTimer);
  cooldownTimer = setInterval(tick, 250);
}

// ------------------------------------------------------------------ enviar pergunta
async function ask(question, { subject = state.subject, retry = false } = {}) {
  if (state.busy || isCooling()) return;
  removeError();

  if (!retry || !state.pending) {
    state.pending?.el.remove(); // uma pergunta anterior que falhou é abandonada
    state.pending = { question, subject, el: userBubble(question, subject) };
    el.messages.append(state.pending.el);
  }
  renderWelcome();
  el.followups.replaceChildren();

  state.busy = true;
  updateSendState();
  showTyping();
  const controller = new AbortController();
  state.controller = controller;

  try {
    const result = await client.sendMessage({ question, subject, sessionId: state.sessionId }, { signal: controller.signal });
    commit(question, subject, result);
  } catch (error) {
    fail(error instanceof ApiError ? error : new ApiError("server"));
  } finally {
    hideTyping();
    state.busy = false;
    state.controller = null;
    updateSendState();
  }
}

function commit(question, subject, result) {
  state.sessionId = result.sessionId;
  store.set(KEYS.session, state.sessionId);

  state.messages.push(
    { role: "user", content: question, subject },
    { role: "assistant", content: result.answer, sources: result.sources, question },
  );
  const questionBubble = state.pending?.el;
  state.pending = null;
  store.set(KEYS.messages, state.messages.slice(-MAX_STORED_MESSAGES));

  const node = assistantMessage(state.messages.at(-1), { latest: true });
  el.messages.append(node);
  renderFollowups();
  // Mostra a pergunta e o começo da resposta (em respostas longas, o aluno lê de cima).
  (questionBubble ?? node).scrollIntoView({ block: "start", behavior: scrollBehavior() });
  announce("Nova resposta do AcodeAI.");
  // O botão clicado (exemplo/atalho) some da tela: devolve o foco ao campo. No celular não,
  // para o teclado não abrir sozinho depois de cada resposta.
  if (!isTouchDevice()) el.question.focus({ preventScroll: true });
}

function fail(error) {
  const pending = state.pending;

  if (error.kind === "validation" && pending) {
    // O servidor recusou a pergunta: devolve o texto ao campo para o aluno corrigir.
    pending.el.remove();
    state.pending = null;
    el.question.value = pending.question;
    autosize();
    renderWelcome();
    showError(error);
    el.question.focus();
    return;
  }
  showError(error, { retry: () => ask(pending?.question ?? "", { subject: pending?.subject ?? "", retry: true }) });
  if (error.kind === "network" || error.kind === "unavailable") checkReadiness();
}

// ------------------------------------------------------------------ campo de pergunta
function autosize() {
  el.question.style.height = "auto";
  el.question.style.height = `${Math.min(el.question.scrollHeight, 168)}px`;
}

function updateSendState() {
  const length = el.question.value.trim().length;
  const tooLong = el.question.value.length > MAX_QUESTION_CHARS;

  el.send.disabled = state.busy || isCooling() || length === 0 || tooLong;
  el.question.setAttribute("aria-invalid", String(tooLong));

  el.counter.hidden = el.question.value.length < COUNTER_FROM;
  el.counter.textContent = `${el.question.value.length}/${MAX_QUESTION_CHARS}`;
  el.counter.classList.toggle("over", tooLong);
}

function onSubmit(event) {
  event.preventDefault();
  const text = el.question.value.trim();
  if (!text || el.send.disabled) return;
  el.question.value = "";
  autosize();
  updateSendState();
  ask(text);
}

function onKeydown(event) {
  // Enter envia; Shift+Enter quebra a linha. No celular Enter quebra a linha (o botão envia).
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !isTouchDevice()) {
    event.preventDefault();
    el.form.requestSubmit();
  }
}

// ------------------------------------------------------------------ nova conversa
function resetConversation() {
  state.controller?.abort();
  const oldSession = state.sessionId;
  state.sessionId = null;
  state.messages = [];
  state.pending = null;
  state.cooldownUntil = 0;
  store.remove(KEYS.session);
  store.remove(KEYS.messages);
  removeError();
  hideTyping();
  renderThread();
  updateSendState();
  window.scrollTo({ top: 0 });
  el.question.focus();
  if (oldSession) client.clearSession(oldSession).catch(() => {}); // apagar no servidor é só higiene
}

function onNewChat() {
  if (isEmptyConversation()) {
    el.question.focus();
    return;
  }
  el.confirm.showModal();
}

// ------------------------------------------------------------------ início
function restoreTranscript() {
  const saved = store.get(KEYS.messages, []);
  if (!Array.isArray(saved)) return;
  state.messages = saved.filter((m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string");
}

// Sem transcrição local mas com sessão: busca o histórico no servidor (que não guarda as fontes).
async function restoreFromServer() {
  if (state.messages.length > 0 || !state.sessionId) return;
  try {
    const history = await client.getHistory(state.sessionId);
    state.messages = history
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) =>
        m.role === "user"
          ? { role: "user", content: m.content, subject: "" }
          : { role: "assistant", content: m.content, sources: [], restored: true },
      );
    renderThread();
  } catch {
    /* sessão desconhecida/servidor fora: começa uma conversa nova */
  }
}

function init() {
  restoreTranscript();
  renderSubjects();
  renderThread();
  updateSendState();

  el.form.addEventListener("submit", onSubmit);
  el.question.addEventListener("input", () => {
    autosize();
    updateSendState();
  });
  el.question.addEventListener("keydown", onKeydown);
  el.newChat.addEventListener("click", onNewChat);
  el.confirm.addEventListener("close", () => {
    if (el.confirm.returnValue === "ok") resetConversation();
  });
  if (isTouchDevice()) el.keyHint.hidden = true;

  loadSubjects();
  checkReadiness();
  restoreFromServer();
}

init();
