// Mini helper para montar DOM sem innerHTML (evita injetar texto do usuário/IA como HTML).

/**
 * h("button", { class: "x", onclick: fn, "aria-label": "..." }, "texto", outroNo)
 * Props: class, dataset (objeto), on* (listeners), booleanos (disabled...), demais viram atributos.
 */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

function append(parent, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function clear(el) {
  el.replaceChildren();
  return el;
}

export const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const isTouchDevice = () => window.matchMedia("(pointer: coarse)").matches;

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Copia texto; usa um fallback para páginas em http:// (sem navigator.clipboard). */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = h("textarea", { style: "position:fixed;opacity:0", readonly: true }, text);
    document.body.append(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}
