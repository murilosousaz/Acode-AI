// Markdown (marked) + sanitização (DOMPurify) + fórmulas (KaTeX).
// As bibliotecas vêm de assets/vendor/ como <script> clássicos e ficam em window.*.
//
// A resposta da IA é texto não confiável: tudo passa pelo DOMPurify antes de ir para a página.

import { escapeHtml, extractMath, restoreMath } from "./math.js";

let configured = false;

function setup() {
  if (configured) return;
  configured = true;

  // Links externos abrem em outra aba e não vazam o referrer.
  window.DOMPurify.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A" && node.hasAttribute("href")) {
      node.setAttribute("target", "_blank");
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
}

function renderFormula({ tex, display }) {
  const katex = window.katex;
  if (!katex) return `<code>${escapeHtml(tex)}</code>`; // sem KaTeX: mostra o LaTeX como código
  try {
    return katex.renderToString(tex, {
      displayMode: display,
      throwOnError: false,
      strict: "ignore",
      trust: false,
      output: "htmlAndMathml",
    });
  } catch {
    return `<code>${escapeHtml(tex)}</code>`;
  }
}

/** Converte Markdown (com LaTeX) em HTML seguro. */
export function renderMarkdown(source) {
  setup();
  const { text, items } = extractMath(source);

  const rawHtml = window.marked.parse(text, { gfm: true, breaks: true, async: false });
  const safeHtml = window.DOMPurify.sanitize(rawHtml, {
    USE_PROFILES: { html: true },
    // Sem imagens (evita rastreamento por URL remota), formulários nem estilos embutidos.
    FORBID_TAGS: ["img", "picture", "source", "style", "form", "input", "button", "textarea", "select", "iframe"],
    FORBID_ATTR: ["style"],
  });

  // Tabelas largas rolam dentro do próprio bloco, sem quebrar o layout no celular.
  const withTables = safeHtml.replace(/<table/g, '<div class="table-wrap"><table').replace(/<\/table>/g, "</table></div>");

  // O HTML do KaTeX é gerado por ele (trust:false) e entra só depois da sanitização.
  return restoreMath(withTables, items, renderFormula);
}
