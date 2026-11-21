// Área do professor: envia um PDF para indexação (POST /api/v1/documents).

import { ApiError, createClient } from "./api.js";
import { FALLBACK_SUBJECTS } from "./content.js";
import { h } from "./dom.js";

const config = window.ACODEAI ?? {};
const client = createClient({ baseUrl: config.apiBase ?? "" });
const MAX_MB = config.maxUploadMb ?? 25;

const $ = (selector) => document.querySelector(selector);
const el = {
  form: $("#upload"),
  key: $("#key"),
  file: $("#file"),
  drop: $("#drop"),
  dropTitle: $("#drop-title"),
  dropHint: $("#drop-hint"),
  subject: $("#subject"),
  title: $("#title"),
  status: $("#status"),
  submit: $("#submit"),
};

let file = null;
let titleEdited = false;
let subjectEdited = false;
let busy = false;
let timer = null;

const formatSize = (bytes) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`);
const normalize = (text) => text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// ------------------------------------------------------------------ matérias
function fillSubjects(subjects) {
  const current = el.subject.value;
  el.subject.replaceChildren(
    h("option", { value: "" }, "Escolha a matéria"),
    ...subjects.map((s) => h("option", { value: s.value }, s.label)),
  );
  el.subject.value = current;
}

async function loadSubjects() {
  fillSubjects(FALLBACK_SUBJECTS);
  try {
    fillSubjects(await client.listSubjects());
  } catch {
    /* fica com a lista embutida */
  }
}

// ------------------------------------------------------------------ arquivo
// Convenção dos scripts de ingestão em lote: "Fisica_Cinematica.pdf" → matéria Fisica, título "Fisica Cinematica".
function suggestFromName(name) {
  const base = name.replace(/\.pdf$/i, "");
  const first = normalize(base.split("_")[0]);
  const match = [...el.subject.options].find((o) => o.value && normalize(o.value) === first);
  return { subject: match?.value ?? "", title: base.replace(/_/g, " ").trim() };
}

function setFile(selected) {
  clearStatus();
  if (!selected) return;

  const isPdf = selected.type === "application/pdf" || /\.pdf$/i.test(selected.name);
  if (!isPdf) return showMessage("error", "Isso não é um PDF", "Escolha um arquivo com a extensão .pdf.");
  if (selected.size > MAX_MB * 1024 * 1024) {
    return showMessage("error", "Arquivo grande demais", `O limite é ${MAX_MB} MB; este tem ${formatSize(selected.size)}.`);
  }

  file = selected;
  el.drop.classList.add("has-file");
  el.dropTitle.textContent = selected.name;
  el.dropHint.textContent = `${formatSize(selected.size)} · clique para trocar`;

  const suggestion = suggestFromName(selected.name);
  if (!subjectEdited && suggestion.subject) el.subject.value = suggestion.subject;
  if (!titleEdited) el.title.value = suggestion.title;
}

function resetFile() {
  file = null;
  el.file.value = "";
  el.drop.classList.remove("has-file");
  el.dropTitle.textContent = "Escolha um PDF ou arraste até aqui";
  el.dropHint.textContent = "Só PDFs com texto selecionável (digitalizados ainda não são lidos).";
}

// ------------------------------------------------------------------ mensagens
function clearStatus() {
  clearInterval(timer);
  el.status.replaceChildren();
}

function showMessage(kind, title, hint, ...extra) {
  clearInterval(timer);
  const box = h("div", { class: kind === "error" ? "msg error" : "result", role: kind === "error" ? "alert" : null },
    h("p", { class: kind === "error" ? "error-title" : "" }, title),
    hint ? h("p", { class: kind === "error" ? "error-hint" : "" }, hint) : null,
    ...extra,
  );
  el.status.replaceChildren(box);
}

function showProgress() {
  const text = h("p", {}, "Enviando e indexando… isso pode levar alguns minutos para PDFs grandes. Mantenha esta página aberta.");
  const clock = h("p", { class: "hint" }, "0s");
  el.status.replaceChildren(h("div", { class: "typing" }, h("span", { class: "dots", "aria-hidden": "true" }, h("i"), h("i"), h("i")), h("div", {}, text, clock)));
  const started = Date.now();
  timer = setInterval(() => (clock.textContent = `${Math.floor((Date.now() - started) / 1000)}s`), 1000);
}

// ------------------------------------------------------------------ envio
function validate() {
  if (!el.key.value.trim()) return { field: el.key, message: "Digite a chave de administrador." };
  if (!file) return { field: el.drop, message: "Escolha um arquivo PDF." };
  if (!el.subject.value) return { field: el.subject, message: "Escolha a matéria do material." };
  if (!el.title.value.trim()) return { field: el.title, message: "Informe o título do material." };
  return null;
}

async function onSubmit(event) {
  event.preventDefault();
  if (busy) return;

  const problem = validate();
  if (problem) {
    showMessage("error", "Falta um dado", problem.message);
    problem.field.focus?.();
    return;
  }

  busy = true;
  el.submit.disabled = true;
  showProgress();
  try {
    const result = await client.uploadDocument({
      file,
      subject: el.subject.value,
      title: el.title.value.trim(),
      apiKey: el.key.value.trim(),
    });
    const again = h("button", { class: "btn-soft", type: "button", onclick: startAnother }, "Enviar outro material");
    showMessage("ok", "Material indexado!", `“${result.title}” foi dividido em ${result.chunks_created} trechos e já pode ser usado nas respostas.`, h("div", { class: "error-actions" }, again));
  } catch (error) {
    const apiError = error instanceof ApiError ? error : new ApiError("server");
    showMessage("error", apiError.title, apiError.hint);
    if (apiError.kind === "unauthorized") el.key.focus();
  } finally {
    busy = false;
    el.submit.disabled = false;
  }
}

function startAnother() {
  resetFile();
  el.title.value = "";
  el.subject.value = "";
  titleEdited = false;
  subjectEdited = false;
  clearStatus();
  el.file.focus();
}

// ------------------------------------------------------------------ eventos
el.file.addEventListener("change", () => setFile(el.file.files[0]));
el.title.addEventListener("input", () => (titleEdited = true));
el.subject.addEventListener("change", () => (subjectEdited = true));
el.form.addEventListener("submit", onSubmit);

for (const type of ["dragenter", "dragover"]) {
  el.drop.addEventListener(type, (event) => {
    event.preventDefault();
    el.drop.classList.add("over");
  });
}
for (const type of ["dragleave", "drop"]) {
  el.drop.addEventListener(type, (event) => {
    event.preventDefault();
    el.drop.classList.remove("over");
  });
}
el.drop.addEventListener("drop", (event) => setFile(event.dataTransfer?.files?.[0]));

loadSubjects();
