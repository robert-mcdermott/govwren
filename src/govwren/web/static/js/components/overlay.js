// Drawers and dialogs: accessible modal panels that trap focus and close on Escape.

import { button, h, iconButton, uid } from "../core/dom.js";

let open = null;

function focusables(root) {
  const selector = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';
  return [...root.querySelectorAll(selector)].filter((el) => !el.hidden && el.offsetParent !== null);
}

export function closeOverlay() {
  if (!open) return;
  const { backdrop, panel, returnFocus, onKey, onTab, onFocus } = open;
  document.removeEventListener("keydown", onKey, true);
  document.removeEventListener("keydown", onTab, true);
  document.removeEventListener("focusin", onFocus, true);
  backdrop.remove();
  panel.remove();
  open = null;
  returnFocus?.focus?.();
}

/**
 * Open a panel. render(body, footer, close) fills it and may be async. kind is "drawer"
 * (from the right, for editing) or "dialog" (centered, for a question).
 */
export function openOverlay({ title, subtitle = null, render, kind = "drawer" }) {
  closeOverlay();
  const returnFocus = document.activeElement;
  const titleId = uid("overlay-title");
  const body = h("div", { class: "drawer-body" });
  const footer = h("div", { class: "drawer-footer", hidden: true });
  const panel = h("section", { class: kind, role: "dialog", "aria-modal": "true", "aria-labelledby": titleId },
    h("div", { class: "drawer-header" },
      h("div", { class: "grow stack-sm" }, h("h2", { id: titleId }, title),
        subtitle ? h("div", { class: "muted" }, subtitle) : null),
      iconButton("close", "Close", { onclick: closeOverlay })),
    body, footer);
  const backdrop = h("div", { class: "backdrop", onclick: closeOverlay });
  const onKey = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeOverlay();
    } else if (event.key === "Tab") {
      const items = focusables(panel);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  };
  // Whatever the last control is (the last radio of a group is never a Tab stop), focus that
  // leaves the panel is brought back: to the end if it left backwards, otherwise to the start.
  let backwards = false;
  const onTab = (event) => {
    if (event.key === "Tab") backwards = event.shiftKey;
  };
  const onFocus = (event) => {
    if (panel.contains(event.target) || event.target.closest?.(".toasts")) return;
    const items = focusables(panel);
    (backwards ? items[items.length - 1] : items[0])?.focus();
  };
  document.addEventListener("keydown", onTab, true);
  document.addEventListener("focusin", onFocus, true);
  document.addEventListener("keydown", onKey, true);
  document.body.append(backdrop, panel);
  open = { backdrop, panel, returnFocus, onKey, onTab, onFocus };
  Promise.resolve(render(body, footer, closeOverlay)).then(() => {
    if (open?.panel !== panel) return;
    const items = focusables(panel);
    (items.find((el) => el.matches("input, select, textarea")) ?? items[1] ?? items[0])?.focus();
  });
  return { panel, body, footer };
}

/** Ask before doing something that matters. run() is awaited after the dialog closes. */
export function confirmAction({ title, text, confirmLabel, danger = false, run }) {
  openOverlay({
    title,
    kind: "dialog",
    render: (body, footer, close) => {
      body.append(h("div", { class: "stack" }, typeof text === "string" ? h("p", {}, text) : text));
      footer.replaceChildren(h("div", { class: "row" },
        button(confirmLabel, { kind: danger ? "btn-danger" : "btn-primary", onclick: async () => {
          close();
          await run();
        } }),
        button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}
