/**
 * Small DOM helpers.
 *
 * User supplied strings are only ever assigned to `textContent` (or used as
 * image `src`), so no user value goes through `innerHTML`.
 */

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") {
      node.className = value;
    } else if (key === "text") {
      node.textContent = String(value);
    } else if (key === "dataset") {
      Object.assign(node.dataset, value);
    } else if (key === "attrs") {
      for (const [name, attrValue] of Object.entries(value)) {
        if (attrValue === null || attrValue === undefined || attrValue === false) continue;
        node.setAttribute(name, String(attrValue));
      }
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key in node) {
      node[key] = value;
    } else {
      node.setAttribute(key, String(value));
    }
  }
  appendChildren(node, children);
  return node;
}

export function appendChildren(node, children) {
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) {
      appendChildren(node, child);
    } else if (child instanceof Node) {
      node.appendChild(child);
    } else {
      node.appendChild(document.createTextNode(String(child)));
    }
  }
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function setText(node, value) {
  node.textContent = value == null ? "" : String(value);
}

export function show(node, visible = true) {
  if (!node) return;
  node.hidden = !visible;
}

export function setPressed(node, pressed) {
  node.classList.toggle("is-active", Boolean(pressed));
  node.setAttribute("aria-pressed", pressed ? "true" : "false");
}

export function chipButton({ label, active = false, onClick, value }) {
  const node = el("button", {
    class: "chip",
    type: "button",
    text: label,
    onclick: onClick,
  });
  if (value !== undefined) node.dataset.value = value;
  setPressed(node, active);
  return node;
}
