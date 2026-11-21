import assert from "node:assert/strict";
import { test } from "node:test";

import { escapeHtml, extractMath, restoreMath } from "../../frontend/assets/js/math.js";

const tex = (text) => extractMath(text).items.map((i) => i.tex);

test("reconhece os quatro delimitadores", () => {
  const { text, items } = extractMath(String.raw`a \(x^2\) b $$y=1$$ c \[z\] d $w$`);
  assert.deepEqual(items.map((i) => [i.tex, i.display]), [
    ["x^2", false],
    ["y=1", true],
    ["z", true],
    ["w", false],
  ]);
  assert.doesNotMatch(text, /[\\$]/); // nada de LaTeX cru sobra para o Markdown mexer
});

test("fórmula de várias linhas em destaque", () => {
  assert.deepEqual(tex("$$\n\\frac{a}{b}\n$$"), ["\\frac{a}{b}"]);
});

test("dinheiro em reais NÃO vira fórmula", () => {
  for (const frase of [
    "O preço é R$ 10,00 e depois R$ 20,00.",
    "Custa R$10 e R$20.",
    "Ganhou $100 e gastou $20 no mercado.",
    "US$5 ou US$6",
  ]) {
    assert.deepEqual(tex(frase), [], frase);
  }
});

test("cifrão dentro de código é ignorado", () => {
  assert.deepEqual(tex("use `$x$` e\n```\n$$y$$\n```\n"), []);
  const { text } = extractMath("veja `$x$` aqui e $v$ ali");
  assert.match(text, /`\$x\$`/); // o código volta intacto
});

test("variável simples entre cifrões e \\$ escapado", () => {
  assert.deepEqual(tex("a velocidade $v$ e a aceleração $a$"), ["v", "a"]);
  assert.deepEqual(tex(String.raw`custa \$5 e \$6`), []);
});

test("delimitador vazio é deixado como está", () => {
  const { text, items } = extractMath("$$   $$");
  assert.equal(items.length, 0);
  assert.equal(text, "$$   $$");
});

test("restoreMath troca cada marcador, inclusive com 11+ fórmulas (token1 vs token10)", () => {
  const src = Array.from({ length: 12 }, (_, i) => `\\(f${i}\\)`).join(" ");
  const { text, items } = extractMath(src);
  const html = restoreMath(`<p>${text}</p>`, items, (item) => `<m>${item.tex}</m>`);
  assert.equal(html, `<p>${Array.from({ length: 12 }, (_, i) => `<m>f${i}</m>`).join(" ")}</p>`);
});

test("sem fórmulas, restoreMath devolve o HTML igual", () => {
  assert.equal(restoreMath("<p>oi</p>", [], () => "X"), "<p>oi</p>");
});

test("escapeHtml", () => {
  assert.equal(escapeHtml(`<img src="x" onerror='a&b'>`), "&lt;img src=&quot;x&quot; onerror=&#39;a&amp;b&#39;&gt;");
});
