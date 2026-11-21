// Protege fórmulas LaTeX antes do Markdown e as devolve depois.
//
// Por quê: o Markdown trata "\(" como um "(" escapado e interpreta "_" e "*" dentro das
// fórmulas, estragando o LaTeX. Então trocamos cada fórmula por um marcador, rodamos o
// Markdown, e só no fim colocamos o HTML do KaTeX no lugar dos marcadores.
//
// Sem dependências de DOM: roda no navegador e no Node (testes).

const TOKEN_PREFIX = "acodemathtoken";
const TOKEN_SUFFIX = "x"; // evita que "token1" case dentro de "token10"
const TOKEN_RE = new RegExp(`${TOKEN_PREFIX}(\\d+)${TOKEN_SUFFIX}`, "g");

// Blocos de código ficam fora: um "$" dentro de código não é fórmula.
const CODE_RE = /```[\s\S]*?```|`[^`\n]+`/g;

// Delimitadores aceitos, nesta ordem de prioridade:
//   $$...$$  \[...\]   (fórmula em destaque)
//   \(...\)  $...$     (fórmula na linha)
// Regras do "$...$" (as do Pandoc), para não confundir com dinheiro ("R$ 10 e R$ 20"):
//   - o "$" de abertura não vem colado numa letra/dígito ("R$5", "US$") nem após "\" ou "$";
//   - logo após a abertura não há espaço; logo antes do fechamento não há espaço;
//   - o "$" de fechamento não é seguido de dígito.
const MATH_RE = new RegExp(
  [
    String.raw`\$\$([\s\S]+?)\$\$`,
    String.raw`\\\[([\s\S]+?)\\\]`,
    String.raw`\\\(([\s\S]+?)\\\)`,
    String.raw`(?<![\w\\$])\$(?![\s$])((?:\\.|[^$\\\n])+?)(?<![\s\\])\$(?!\d)`,
  ].join("|"),
  "g",
);

/**
 * Troca as fórmulas por marcadores.
 * @returns {{ text: string, items: Array<{ tex: string, display: boolean }> }}
 */
export function extractMath(source) {
  const codeParts = [];
  const withoutCode = String(source ?? "").replace(CODE_RE, (match) => {
    codeParts.push(match);
    return `\u0000${codeParts.length - 1}\u0000`;
  });

  const items = [];
  const withTokens = withoutCode.replace(MATH_RE, (_, blockDollar, blockBracket, inlineParen, inlineDollar) => {
    const tex = (blockDollar ?? blockBracket ?? inlineParen ?? inlineDollar ?? "").trim();
    if (!tex) return _;
    items.push({ tex, display: blockDollar !== undefined || blockBracket !== undefined });
    return `${TOKEN_PREFIX}${items.length - 1}${TOKEN_SUFFIX}`;
  });

  const text = withTokens.replace(/\u0000(\d+)\u0000/g, (_, i) => codeParts[Number(i)]);
  return { text, items };
}

/** Coloca o HTML de cada fórmula no lugar do seu marcador. `render(item)` devolve HTML seguro. */
export function restoreMath(html, items, render) {
  if (items.length === 0) return html;
  return html.replace(TOKEN_RE, (match, i) => {
    const item = items[Number(i)];
    return item ? render(item) : match;
  });
}

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}
