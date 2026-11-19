// Evidence: the files, links, and notes that show a thing is so. One small list and one
// drawer, used on records, conditions, and review findings alike.

import { get, patch, post, upload } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { label, options, vocabularies } from "../core/lookups.js";
import { banner, field, select, submit } from "./form.js";
import { confirmAction, openOverlay } from "./overlay.js";
import { toast } from "./toast.js";
import { card, pill } from "./ui.js";

const STATES = { current: null, expiring: ["Expires soon", "warn"], expired: ["Expired", "danger"], withdrawn: ["Withdrawn", ""] };

export function size(bytes) {
  if (bytes < 1024) return `${bytes} bytes`;
  return bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function statePill(item) {
  const found = STATES[item.state];
  return found ? pill(found[0], found[1]) : null;
}

/** Add evidence to something. supports: what it is attached to, as the API names it. */
export async function addEvidence({ supports, about, onDone }) {
  const vocab = await vocabularies();
  openOverlay({
    title: "Attach evidence",
    subtitle: about,
    render: (body, footer, close) => {
      const title = field("What is it?", { required: true, hint: "A few words, such as “Ethics approval letter”." });
      const kind = select("Kind", options(vocab, "evidence_kinds"), { value: "document" });
      const file = field("A file", { type: "file", hint: "PDF, images, office documents, plain text, CSV, or JSON, up to 25 MB." });
      const url = field("Or an address", { type: "url", placeholder: "https://", hint: "Where it lives, if it is kept in another system." });
      const note = field("Note", { type: "textarea", hint: "What it shows. Do not paste sensitive data here." });
      const dated = field("Its date", { type: "date" });
      const until = field("Good until", { type: "date", hint: "For things that go stale, such as a yearly report. Leave empty otherwise." });
      const problem = banner();
      const save = button("Attach", { kind: "btn-primary" });
      file.input.addEventListener("change", () => {
        const chosen = file.input.files[0];
        if (chosen && !title.input.value) title.input.value = chosen.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
      });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, banner: problem,
          fields: { title, kind, file, url, dated_on: dated, expires_on: until },
          run: async () => {
            const chosen = file.input.files[0];
            const stored = chosen ? (await upload("/api/v1/evidence/files", chosen, { name: chosen.name })).data : null;
            return post("/api/v1/evidence", { title: title.input.value, kind: kind.input.value,
              description: note.input.value || null, url: url.input.value || null,
              file_id: stored?.file_id ?? null, file_name: stored?.name ?? null,
              dated_on: dated.input.value || null, expires_on: until.input.value || null, supports });
          } });
        if (done) {
          close();
          toast(`${done.data.ref} was attached.`);
          onDone?.(done.data);
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, title.node, kind.node, file.node, url.node, note.node,
        h("div", { class: "grid-2" }, dated.node, until.node)));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function withdraw(item, onDone) {
  confirmAction({ title: "Withdraw this evidence?", text: "It stays on the record, marked as withdrawn. Use this for something attached by mistake or no longer true.",
    confirmLabel: "Withdraw", danger: true,
    run: async () => {
      await patch(`/api/v1/evidence/${item.ref}`, { status: "withdrawn" });
      toast("The evidence was withdrawn.");
      onDone?.();
    } });
}

/** Evidence as a list. Each row: what it is, how to get it, and whether it is still good. */
export function evidenceList(items, { vocab = null, onChange = null } = {}) {
  return h("ul", { class: "evidence-list" }, items.map((item) => h("li", { "data-state": item.state },
    icon(item.file ? "file" : item.url ? "external" : "note", "icon"),
    h("div", { class: "grow" },
      h("div", { class: "cell-main" },
        item.file ? h("a", { href: item.file.href, download: item.file.name }, item.title)
          : item.url ? h("a", { href: item.url, target: "_blank", rel: "noopener noreferrer" }, item.title) : item.title),
      h("div", { class: "cell-sub" }, [item.ref, vocab ? label(vocab, "evidence_kinds", item.kind) : null,
        item.file ? `${item.file.name} · ${size(item.file.size)}` : null,
        item.dated_on ? `dated ${date(item.dated_on)}` : null,
        item.expires_on ? `good until ${date(item.expires_on)}` : null, item.owner?.name].filter(Boolean).join(" · ")),
      item.description ? h("div", { class: "cell-sub" }, item.description) : null),
    statePill(item),
    item.can?.edit && item.state !== "withdrawn" && onChange
      ? button("Withdraw", { kind: "btn-ghost btn-sm", onclick: () => withdraw(item, onChange) }) : null)));
}

/** The Evidence card on a record's page. */
export function evidenceCard(record, ctx) {
  const items = record.evidence ?? [];
  const canAdd = record.can?.edit;
  if (!items.length && !canAdd) return null;
  return card({ title: "Evidence", actions: canAdd ? button("Attach", { kind: "btn-sm", iconName: "plus",
    onclick: () => addEvidence({ supports: [record.ref], about: `${record.ref} · ${record.name}`, onDone: ctx.reload }) }) : null },
  items.length ? evidenceList(items, { vocab: ctx.vocab, onChange: ctx.reload })
    : h("p", { class: "muted" }, "Nothing is attached. Attach the approvals, agreements, and reports this rests on."));
}

export async function allEvidence(params) {
  return get("/api/v1/evidence", params, { fresh: true });
}
