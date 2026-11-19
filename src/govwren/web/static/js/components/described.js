// Record types that are mostly a description (models, datasets) are drawn and edited from
// the list of fields the server publishes, so a new field needs no change here. Also here:
// the cards every record shares for links to other records and pointers to other systems.

import { del, get, patch, post, put } from "../core/api.js";
import { button, h, icon, iconButton } from "../core/dom.js";
import { date } from "../core/format.js";
import { label, options, unitOptions } from "../core/lookups.js";
import { navigate } from "../core/router.js";
import { can } from "../core/session.js";
import { banner, checkbox, field, select, submit } from "./form.js";
import { confirmAction, openOverlay } from "./overlay.js";
import { peoplePicker } from "./people-picker.js";
import { recordChip, standingPill, TYPES } from "./record.js";
import { toast } from "./toast.js";
import { alert, card, pill } from "./ui.js";

let published = null;

/** The fields of the described record types, and the links each kind of record may make. */
export async function recordTypes() {
  published ??= get("/api/v1/record-types").then((answer) => answer.data);
  return published;
}

const choicesOf = (spec, vocab) => spec.options?.map((item) => [item.key, item.label])
  ?? (vocab[spec.vocab] ?? []).filter((item) => !item.retired).map((item) => [item.key, item.label]);
const labelOf = (spec, vocab, key) => spec.options?.find((item) => item.key === key)?.label ?? label(vocab, spec.vocab, key);
const empty = (value) => value == null || value === "" || (Array.isArray(value) && !value.length);

function facts(pairs) {
  const shown = pairs.filter(([, value]) => !empty(value));
  if (!shown.length) return h("p", { class: "muted" }, "Nothing recorded yet.");
  return h("dl", { class: "dl" }, shown.map(([term, value]) => [h("dt", {}, term), h("dd", {}, value)]));
}

function shownValue(spec, value, vocab) {
  if (empty(value)) return null;
  if (spec.kind === "choices") return h("div", { class: "row-sm wrap" }, value.map((key) => pill(labelOf(spec, vocab, key))));
  if (spec.kind === "choice") return spec.vocab === "catalog_statuses" ? standingPill(value) : labelOf(spec, vocab, value);
  if (spec.kind === "date") return date(value);
  if (spec.kind === "url") return h("a", { href: value, target: "_blank", rel: "noopener noreferrer" }, value.replace(/^https?:\/\//, ""));
  if (spec.kind === "long") return h("p", { class: "prose" }, value);
  return value;
}

const applies = (spec, origin) => !spec.only_for || !origin || spec.only_for.includes(origin);

/** One card for each group of fields that has something in it. */
export function describedCards(record, specs, vocab, { skip = [] } = {}) {
  const groups = new Map();
  for (const spec of specs) {
    if (skip.includes(spec.group ?? "About") || !applies(spec, record.origin)) continue;
    if (!groups.has(spec.group ?? "About")) groups.set(spec.group ?? "About", []);
    groups.get(spec.group ?? "About").push([spec.label, shownValue(spec, record[spec.key], vocab)]);
  }
  return [...groups].filter(([, pairs]) => pairs.some(([, value]) => !empty(value)))
    .map(([title, pairs]) => card({ title: title === "About" ? "Details" : title }, facts(pairs)));
}

function control(spec, value, vocab) {
  if (spec.kind === "choice") {
    const node = select(spec.label, [["", spec.required ? "Choose" : "Not said"], ...choicesOf(spec, vocab)], { value: value ?? "", hint: spec.hint });
    return { ...node, read: () => node.input.value || null };
  }
  if (spec.kind === "choices") {
    const chosen = value ?? [];
    const boxes = choicesOf(spec, vocab).map(([key, text]) => checkbox(text, { checked: chosen.includes(key), value: key }));
    const node = h("fieldset", {}, h("legend", {}, spec.label), spec.hint ? h("p", { class: "hint subtle" }, spec.hint) : null,
      h("div", { class: "grid-2" }, boxes.map((box) => box.node)));
    return { node, input: boxes[0]?.input ?? node, setError: () => {}, read: () => boxes.filter((box) => box.input.checked).map((box) => box.input.value) };
  }
  const type = { long: "textarea", date: "date", url: "url" }[spec.kind] ?? "text";
  const node = field(spec.label, { type, value: value ?? "", hint: spec.hint, placeholder: spec.kind === "url" ? "https://" : null });
  return { ...node, read: () => node.input.value.trim() || null };
}

/** Add or edit a model or a dataset. */
export function editDescribed(type) {
  return async ({ record = null, vocab, units, vendors = [], onDone }) => {
    const specs = (await recordTypes())[type];
    const meta = TYPES[type];
    openOverlay({
      title: record ? `Edit ${meta.noun}` : `Add a ${meta.noun}`,
      subtitle: record ? record.ref : meta.blurb,
      render: (body, footer, close) => {
        const name = field("Name", { value: record?.name ?? "", required: true });
        const summary = field("Summary", { type: "textarea", value: record?.summary ?? "" });
        const unit = select("Unit", unitOptions(units.tree, { blank: "None" }), { value: record?.org_unit_id ?? "" });
        const vendor = type === "model" ? select("Vendor", [["", "None, or not a supplier's"], ...vendors.map((v) => [v.ref, v.name])],
          { value: record?.vendor?.ref ?? "" }) : null;
        const restricted = checkbox("Restricted", { checked: record?.restricted ?? false,
          hint: "Known only to its owners, the unit's stewards, governance, and auditors." });
        const controls = new Map();
        const groups = new Map();
        for (const spec of specs) {
          if (spec.governed && !can("edit_all")) continue;
          const made = control(spec, record?.[spec.key], vocab);
          controls.set(spec.key, { spec, ...made });
          if (!groups.has(spec.group ?? "About")) groups.set(spec.group ?? "About", []);
          groups.get(spec.group ?? "About").push({ spec, node: made.node });
        }
        const origin = controls.get("origin");
        const sections = [...groups].map(([title, items], index) => {
          const node = h("div", { class: "form-section stack" }, h("h3", {}, title),
            index === 0 ? [name.node, summary.node, h("div", { class: "grid-2" }, unit.node, vendor?.node)] : null,
            items.map((item) => item.node));
          return { node, items, first: index === 0 };
        });
        const sync = () => {
          for (const { node, items, first } of sections) {
            let any = first;
            for (const item of items) {
              item.node.hidden = !applies(item.spec, origin?.input.value);
              any ||= !item.node.hidden;
            }
            node.hidden = !any;
          }
        };
        origin?.input.addEventListener("change", sync);
        sync();
        const problem = banner();
        const save = button(record ? "Save" : "Add", { kind: "btn-primary" });
        const fields = { name, org_unit_id: unit, ...Object.fromEntries([...controls].map(([key, c]) => [key, c])) };
        if (vendor) fields.vendor = vendor;
        save.addEventListener("click", async () => {
          const values = { name: name.input.value, summary: summary.input.value || null,
            org_unit_id: unit.input.value ? Number(unit.input.value) : null, restricted: restricted.input.checked };
          if (vendor) values.vendor = vendor.input.value || null;
          for (const [key, c] of controls) if (applies(c.spec, origin?.input.value)) values[key] = c.read();
          const plain = (value) => JSON.stringify(empty(value) ? null : value);
          const sent = record ? Object.fromEntries(Object.entries(values).filter(([key, value]) =>
            plain(value) !== plain(key === "vendor" ? record.vendor?.ref : record[key]))) : values;
          const path = `/api/v1/${meta.path}`;
          const done = await submit({ button: save, fields, banner: problem,
            run: () => (record ? patch(`${path}/${record.ref}`, { version: record.version, ...sent }) : post(path, sent)) });
          if (!done) return;
          close();
          if (record) {
            toast("Saved.");
            onDone?.(done.data);
          } else {
            toast(`${done.data.ref} was added.`);
            navigate(`/${meta.path}/${done.data.ref}`);
          }
        });
        body.append(h("form", { class: "stack-lg", novalidate: true, onsubmit: (event) => {
          event.preventDefault();
          save.click();
        } }, problem, sections.map((s) => s.node),
        h("div", { class: "form-section stack" }, h("h3", {}, "Visibility"), restricted.node)));
        footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
        footer.hidden = false;
      },
    });
  };
}

// --- Links to other records ---

function addLink(record, ctx, offered) {
  openOverlay({
    title: "Link to another record",
    subtitle: `${record.ref} · ${record.name}`,
    render: (body, footer, close) => {
      const relation = select("This record", offered.map((item, index) => [index, `${item.label.toLowerCase()} a ${TYPES[item.to].noun}`]), { value: 0 });
      const search = h("input", { class: "input", type: "search", placeholder: "Find it by name or reference", "aria-label": "Find a record" });
      const results = h("div", { class: "pick-results" });
      const note = field("Note", { hint: "Optional. A few words on how they are connected.", maxlength: 300 });
      const problem = banner();
      let timer = null;
      const draw = async () => {
        const choice = offered[Number(relation.input.value)];
        const found = (await get(`/api/v1/${TYPES[choice.to].path}`, { q: search.value.trim(), limit: 8, sort: "name" }, { fresh: true })).data
          .filter((row) => row.ref !== record.ref);
        results.replaceChildren(...(found.length ? found.map((row) => h("button", { type: "button", class: "pick-item", onclick: async () => {
          const done = await submit({ button: results, banner: problem,
            run: () => post("/api/v1/links", { source: record.ref, relation: choice.relation, target: row.ref, note: note.input.value || null }) });
          if (done) {
            close();
            toast("Linked.");
            ctx.reload();
          }
        } }, icon(TYPES[choice.to].iconName), h("span", {}, h("span", { class: "cell-main" }, row.name), h("span", { class: "cell-sub" }, ` ${row.ref}`))))
          : [h("p", { class: "muted" }, `No ${TYPES[choice.to].nouns} match.`)]));
      };
      relation.input.addEventListener("change", draw);
      search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(draw, 200);
      });
      draw();
      body.append(h("div", { class: "stack-lg" }, problem, relation.node, note.node,
        h("div", { class: "field" }, h("div", { class: "label" }, "Which one"), search, results)));
      footer.replaceChildren(h("div", { class: "row" }, button("Close", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

/** What this record points to and what points to it, grouped by how. */
export function linksCard(record, ctx, { hide = [] } = {}) {
  const links = record.links ?? { outgoing: [], incoming: [], hidden: 0 };
  const offered = (ctx.types?.links?.[record.type] ?? []).filter((item) => !(record.type === "use_case" && item.to === "system"));
  const canEdit = record.can?.edit && offered.length;
  const groups = new Map();
  for (const [side, entries] of [["outgoing", links.outgoing], ["incoming", links.incoming]]) {
    for (const entry of entries) {
      if (hide.includes(`${side}:${entry.relation}:${entry.record.type}`)) continue;
      if (!groups.has(entry.label)) groups.set(entry.label, []);
      groups.get(entry.label).push({ ...entry, removable: side === "outgoing" && canEdit });
    }
  }
  if (!groups.size && !canEdit) return null;
  return card({ title: "Connected to", actions: canEdit ? button("Add", { kind: "btn-sm", iconName: "plus", onclick: () => addLink(record, ctx, offered) }) : null },
    groups.size ? h("div", { class: "stack" }, [...groups].map(([title, entries]) => h("div", { class: "stack-sm" },
      h("h3", { class: "bars-title" }, title),
      entries.map((entry) => h("div", { class: "row" },
        h("div", { class: "grow" }, recordChip(entry.record), entry.note ? h("div", { class: "cell-sub" }, entry.note) : null),
        entry.record.type === "dataset" && entry.record.data_class ? pill(label(ctx.vocab, "data_classes", entry.record.data_class))
          : entry.record.catalog_status ? standingPill(entry.record.catalog_status) : null,
        entry.removable ? iconButton("close", `Remove the link to ${entry.record.name}`, { onclick: () => confirmAction({
          title: "Remove this link?", text: `${record.name} will no longer be shown as connected to ${entry.record.name}.`, confirmLabel: "Remove", danger: true,
          run: async () => {
            await del(`/api/v1/links/${entry.id}`);
            toast("The link was removed.");
            ctx.reload();
          } }) }) : null)))))
      : h("p", { class: "muted" }, "Nothing yet. Link it to the models, datasets, and systems it relies on."),
    links.hidden ? h("p", { class: "subtle" }, `And ${links.hidden} more that you do not have access to.`) : null);
}

// --- Pointers to other systems ---

function editReferences(record, ctx) {
  openOverlay({
    title: "References",
    subtitle: "Where to find the protocol, grant, agreement, ticket, or repository this belongs to.",
    render: (body, footer, close) => {
      const rows = [];
      const list = h("div", { class: "stack" });
      const add = (item = { kind: "protocol", identifier: "", label: "", url: "" }) => {
        const kind = h("select", { class: "select", "aria-label": "Kind" }, options(ctx.vocab, "reference_kinds").map(([key, text]) => h("option", { value: key, selected: key === item.kind }, text)));
        const identifier = h("input", { class: "input", value: item.identifier ?? "", placeholder: "Number or name there", "aria-label": "Number or name in the other system" });
        const text = h("input", { class: "input", value: item.label ?? "", placeholder: "What it is (optional)", "aria-label": "What it is" });
        const url = h("input", { class: "input", type: "url", value: item.url ?? "", placeholder: "https:// (optional)", "aria-label": "Address" });
        const row = { kind, identifier, text, url };
        const node = h("div", { class: "reference-row" }, h("div", { class: "grid-2" }, kind, identifier), h("div", { class: "grid-2" }, text, url),
          button("Remove", { kind: "btn-ghost btn-sm", onclick: () => {
            rows.splice(rows.indexOf(row), 1);
            node.remove();
          } }));
        rows.push(row);
        list.append(node);
      };
      (record.references ?? []).forEach((item) => add(item));
      const problem = banner();
      const save = button("Save", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, banner: problem, run: () => put(`/api/v1/records/${record.ref}/references`, {
          references: rows.filter((row) => row.identifier.value.trim()).map((row) => ({ kind: row.kind.value,
            identifier: row.identifier.value.trim(), label: row.text.value.trim() || null, url: row.url.value.trim() || null })) }) });
        if (done) {
          close();
          toast("Saved.");
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, list, h("div", {}, button("Add a reference", { iconName: "plus", onclick: () => add() }))));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

export function referencesCard(record, ctx) {
  const items = record.references ?? [];
  const canEdit = record.can?.edit;
  if (!items.length && !canEdit) return null;
  return card({ title: "In other systems", actions: canEdit ? button("Edit", { kind: "btn-sm", onclick: () => editReferences(record, ctx) }) : null },
    items.length ? h("ul", { class: "stack-sm" }, items.map((item) => h("li", {},
      h("div", { class: "cell-main" }, item.url ? h("a", { href: item.url, target: "_blank", rel: "noopener noreferrer" }, item.identifier) : item.identifier),
      h("div", { class: "cell-sub" }, [label(ctx.vocab, "reference_kinds", item.kind), item.label].filter(Boolean).join(" · ")))))
      : h("p", { class: "muted" }, "No protocol, grant, agreement, or ticket is recorded."));
}

// --- Agent profiles ---

export function agentCard(record, ctx) {
  const specs = ctx.types?.agent_profile ?? [];
  const profile = record.agent_profile ?? {};
  const filled = Object.keys(profile).length > 0;
  if (record.kind !== "agent" && !filled) return null;
  const edit = () => openOverlay({
    title: "Agent profile",
    subtitle: "What it may do, as whom, and how a person stops it.",
    render: (body, footer, close) => {
      const controls = specs.map((spec) => ({ spec, ...control(spec, profile[spec.key], ctx.vocab) }));
      const problem = banner();
      const save = button("Save", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const done = await submit({ button: save, banner: problem,
          fields: Object.fromEntries(controls.map((c) => [`agent_profile.${c.spec.key}`, c])),
          run: () => patch(`/api/v1/systems/${record.ref}`, { version: record.version,
            agent_profile: Object.fromEntries(controls.map((c) => [c.spec.key, c.read()])) }) });
        if (done) {
          close();
          toast("Saved.");
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, controls.map((c) => c.node)));
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
  return card({ title: "What it can do by itself", actions: record.can?.edit ? button("Edit", { kind: "btn-sm", onclick: edit }) : null },
    filled ? facts(specs.map((spec) => [spec.label, shownValue(spec, profile[spec.key], ctx.vocab)]))
      : alert("warn", icon("alert"), h("div", {}, "This is an agent, and nothing is recorded yet about what it may do or how it is stopped.")));
}

// --- Vendor agreements ---

const STATES = { current: ["Current", "ok"], ending: ["Ends soon", "warn"], notice: ["In its notice period", "warn"], ended: ["Ended", "danger"] };

function editAgreement(vendor, ctx, agreement = null) {
  openOverlay({
    title: agreement ? "Edit agreement" : "Add an agreement",
    subtitle: vendor.name,
    render: (body, footer, close) => {
      const kind = select("Kind", options(ctx.vocab, "agreement_kinds"), { value: agreement?.kind ?? "master" });
      const title = field("Title", { value: agreement?.title ?? "", required: true });
      const reference = field("Reference", { value: agreement?.reference ?? "", hint: "Its number in your contracts system." });
      const starts = field("In effect from", { type: "date", value: agreement?.effective_on ?? "" });
      const ends = field("Ends on", { type: "date", value: agreement?.expires_on ?? "", hint: "Leave empty if it has no end date." });
      const notice = field("Notice needed, in days", { type: "number", min: 0, max: 730, value: agreement?.notice_days ?? "",
        hint: "How long before the end date you must say you are not renewing." });
      const renews = checkbox("Renews by itself unless notice is given", { checked: agreement?.auto_renews ?? false });
      const notes = field("Notes", { type: "textarea", value: agreement?.notes ?? "" });
      let owner = agreement?.owner ?? null;
      const ownerLine = h("div", { class: "cell-sub" });
      const showOwner = () => { ownerLine.textContent = owner ? `Looked after by ${owner.name}` : "Nobody is named as looking after it."; };
      showOwner();
      const picker = peoplePicker({ label: "Who looks after it", exclude: () => false, onPick: (account) => {
        owner = { id: account.id, name: account.display_name };
        showOwner();
      } });
      const problem = banner();
      const save = button(agreement ? "Save" : "Add", { kind: "btn-primary" });
      save.addEventListener("click", async () => {
        const values = { kind: kind.input.value, title: title.input.value, reference: reference.input.value || null,
          effective_on: starts.input.value || null, expires_on: ends.input.value || null,
          notice_days: notice.input.value === "" ? null : Number(notice.input.value), auto_renews: renews.input.checked,
          owner_id: owner?.id ?? null, notes: notes.input.value || null };
        const done = await submit({ button: save, banner: problem,
          fields: { kind, title, reference, effective_on: starts, expires_on: ends, notice_days: notice },
          run: () => (agreement ? patch(`/api/v1/agreements/${agreement.id}`, values) : post(`/api/v1/vendors/${vendor.ref}/agreements`, values)) });
        if (done) {
          close();
          toast("Saved.");
          ctx.reload();
        }
      });
      body.append(h("div", { class: "stack-lg" }, problem, h("div", { class: "grid-2" }, kind.node, reference.node), title.node,
        h("div", { class: "grid-2" }, starts.node, ends.node), notice.node, renews.node, h("div", { class: "stack-sm" }, picker, ownerLine), notes.node));
      footer.replaceChildren(h("div", { class: "row" }, save,
        agreement ? button("Remove", { kind: "btn-ghost", onclick: () => confirmAction({ title: "Remove this agreement?",
          text: "It stays in the vendor's history.", confirmLabel: "Remove", danger: true,
          run: async () => {
            await del(`/api/v1/agreements/${agreement.id}`);
            toast("The agreement was removed.");
            ctx.reload();
          } }) }) : null,
        button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

export function agreementsCard(vendor, ctx) {
  const items = vendor.agreements ?? [];
  const canEdit = vendor.can?.edit;
  return card({ title: "Agreements", flush: items.length > 0,
    actions: canEdit ? button("Add", { kind: "btn-sm", iconName: "plus", onclick: () => editAgreement(vendor, ctx) }) : null },
  items.length ? h("ul", {}, items.map((item) => {
    const [text, tone] = STATES[item.state] ?? STATES.current;
    const when = item.expires_on ? `${item.state === "ended" ? "Ended" : "Ends"} ${date(item.expires_on)}` : "No end date";
    return h("li", { class: "list-row" },
      h("div", { class: "grow" },
        canEdit ? h("button", { type: "button", class: "btn-ghost cell-main link-button", onclick: () => editAgreement(vendor, ctx, item) }, item.title)
          : h("div", { class: "cell-main" }, item.title),
        h("div", { class: "cell-sub" }, [label(ctx.vocab, "agreement_kinds", item.kind), item.reference, when,
          item.notice_by && item.state !== "ended" ? `give notice by ${date(item.notice_by)}` : null,
          item.auto_renews ? "renews by itself" : null, item.owner?.name].filter(Boolean).join(" · "))),
      pill(text, tone));
  })) : h("p", { class: "muted" }, "No agreements are recorded."));
}
