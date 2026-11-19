// Saved views: a list's filters and sort, kept under a name.

import { del, get, post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { query, setQuery } from "../core/router.js";
import { banner, field, submit } from "./form.js";
import { openOverlay } from "./overlay.js";
import { toast } from "./toast.js";

export function savedViews(listKey) {
  return get("/api/v1/views", { list: listKey }, { fresh: true }).then((answer) => answer.data);
}

const current = () => Object.fromEntries([...query()].filter(([key, value]) => key !== "cursor" && value !== ""));
const same = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());

/** A menu of the person's views for this list, and a way to save or remove one. */
export function viewsBar(listKey, views, reload) {
  const now = current();
  const active = views.find((view) => same(view.params, now));
  const apply = (params) => setQuery({ ...Object.fromEntries([...query().keys()].map((key) => [key, null])), ...params }, { replace: false });
  const menu = h("select", { class: "select", "aria-label": "Saved views", onchange: () => {
    const chosen = views.find((view) => String(view.id) === menu.value);
    if (chosen) apply(chosen.params);
    else if (menu.value === "all") apply({});
  } }, h("option", { value: "", selected: !active, disabled: true, hidden: true }, views.length ? "Saved views" : "No saved views"),
  h("option", { value: "all" }, "Everything, unfiltered"),
  views.map((view) => h("option", { value: view.id, selected: view === active }, view.name)));
  const save = button("Save view", { kind: "btn-ghost", disabled: !Object.keys(now).length, onclick: () => openOverlay({
    title: "Save this view", kind: "dialog", subtitle: "The filters and sort you have now, under a name of your own.",
    render: (body, footer, close) => {
      const name = field("Name", { required: true, maxlength: 80, value: active?.name ?? "" });
      const problem = banner();
      const go = button("Save", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, fields: { name }, banner: problem,
          run: () => post("/api/v1/views", { list: listKey, name: name.input.value, params: now }) });
        if (done) {
          close();
          toast(`Saved as “${done.data.name}”.`);
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, name.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    } }) });
  const remove = active ? button("Remove view", { kind: "btn-ghost", onclick: async () => {
    await del(`/api/v1/views/${active.id}`);
    toast(`“${active.name}” was removed.`);
    reload();
  } }) : null;
  return h("div", { class: "views-bar" }, menu, save, remove);
}
