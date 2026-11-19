// Controls: the library with how each control stands, the controls of one record, and one
// control with the records it applies to.

import { get, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { query } from "../core/router.js";
import { can } from "../core/session.js";
import { addEvidence } from "../components/evidence.js";
import { banner, checkbox, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STATUS = { not_started: ["Not started", ""], in_progress: ["In progress", "warn"], implemented: ["In place", "ok"], not_applicable: ["Does not apply", ""] };
const KINDS = { use_case: "use cases", system: "AI systems", model: "models", dataset: "datasets" };
const kinds = (list) => { const text = list.map((kind) => KINDS[kind]).join(" and "); return text.charAt(0).toUpperCase() + text.slice(1); };
const statusPill = (item) => (item.check_due ? pill("Check is due", "warn") : pill(...STATUS[item.status]));
const share = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

function setStanding(control, record, reload, mayExempt) {
  openOverlay({
    title: "How does it stand?", subtitle: control.title, kind: "dialog",
    render: (body, footer, shut) => {
      const options = Object.entries(STATUS).filter(([key]) => key !== "not_applicable" || mayExempt).map(([key, [text]]) => [key, text]);
      const status = select("Standing", options, { value: control.status });
      const note = field("How it is done here", { type: "textarea", value: control.note ?? "", hint: "Or, if it does not apply, why not." });
      const checked = control.status === "implemented" ? checkbox("I checked today that it is still in place", { hint: `Sets the next check ${control.check_months} months from now.` }) : null;
      const problem = banner();
      const go = button("Save", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { status, note },
          run: () => put(`/api/v1/controls/${control.key}/standing`, { record, status: status.input.value, note: note.input.value, checked: Boolean(checked?.input.checked) }) });
        if (done) {
          shut();
          toast("Saved.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, h("p", { class: "muted" }, control.statement), status.node, note.node, checked?.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

function standingRow(control, record, reload, mayExempt) {
  return h("li", { class: "row wrap" },
    h("div", { class: "grow" }, h("a", { class: "cell-main", href: `/controls/${control.key}` }, control.title),
      h("div", { class: "cell-sub" }, control.statement),
      control.note ? h("div", { class: "cell-sub" }, `Here: ${control.note}`) : null,
      control.status === "implemented" && control.next_check_on ? h("div", { class: "cell-sub" }, `${control.owner ?? "Nobody"} · next check ${date(control.next_check_on)}`) : null,
      control.evidence?.length ? h("div", { class: "cell-sub" }, "Evidence: ", control.evidence.map((item, index) => [index ? ", " : "",
        h("a", { href: `/evidence?q=${item.ref}` }, item.title), item.state === "expired" ? " (expired)" : item.state === "expiring" ? " (expires soon)" : ""])) : null),
    h("div", { class: "row-sm wrap" }, statusPill(control),
      control.evidence_gap === "expired" ? pill("Evidence expired", "danger") : control.evidence_gap === "none" ? pill("No evidence") : null,
      record && control.implementation_id && control.can_set ? button("Attach", { kind: "btn-sm btn-ghost", "aria-label": `Attach evidence to: ${control.title}`,
        onclick: () => addEvidence({ supports: [`control:${control.implementation_id}`], about: control.title, onDone: reload }) }) : null,
      control.can_set ? button("Set…", { kind: "btn-sm", "aria-label": `Say how this stands: ${control.title}`, onclick: () => setStanding(control, record, reload, mayExempt) }) : null));
}

const grouped = (controls) => [...controls.reduce((groups, control) => groups.set(control.category_label, [...(groups.get(control.category_label) ?? []), control]), new Map())];

export function controlList(main) {
  const record = query().get("record");
  return show(main, {
    title: "Controls",
    load: async () => {
      const found = await get("/api/v1/controls", record ? { record } : null, { fresh: true });
      return { controls: found.data, about: found.meta.record ?? null, governs: can("govern") };
    },
    view: (data, reload) => {
      if (record) {
        const inPlace = data.controls.filter((c) => c.status === "implemented").length;
        const counted = data.controls.filter((c) => c.status !== "not_applicable").length;
        return h("div", { class: "stack-lg" },
          h("a", { class: "back-link", href: "/controls" }, icon("chevron-left", "icon icon-sm"), "The control library"),
          pageHeader({ eyebrow: `Controls · ${data.about.ref}`, title: data.about.name,
            lede: `${inPlace} of ${counted} controls that apply here are in place.` }),
          data.controls.length ? grouped(data.controls).map(([label, items]) => card({ title: label },
            h("ul", { class: "rows" }, items.map((control) => standingRow(control, record, reload, data.governs)))))
            : emptyState({ iconName: "check", title: "No control applies to this record" }));
      }
      const program = data.controls.filter((c) => c.scope === "program");
      const done = program.filter((c) => c.status === "implemented").length;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Controls", lede: "The safeguards of the program, each defined once. Some are for the program as a whole. The rest apply to every record their rule picks out." }),
        h("p", { class: "muted" }, `${done} of ${program.length} program controls are in place.`),
        grouped(data.controls).map(([label, items]) => card({ title: label }, h("ul", { class: "rows" }, items.map((control) => (control.scope === "program"
          ? standingRow(control, null, reload, data.governs)
          : h("li", { class: "row wrap" },
            h("div", { class: "grow" }, h("a", { class: "cell-main", href: `/controls/${control.key}` }, control.title),
              h("div", { class: "cell-sub" }, control.statement),
              h("div", { class: "cell-sub" }, `Applies to ${control.applies_to.map((kind) => KINDS[kind]).join(" and ")}`)),
            h("div", { class: "control-coverage" },
              (() => { const bar = h("div", { class: "meter", role: "img", "aria-label": `${control.in_place} of ${control.applicable} in place` }, h("span")); bar.style.setProperty("--share", `${share(control.in_place, control.applicable)}%`); return bar; })(),
              h("div", { class: "subtle numeric" }, control.applicable ? `${control.in_place} of ${control.applicable} records` : "No record yet")))))))));
    },
  });
}

export function controlPage(main, params) {
  return show(main, {
    title: "Control",
    load: async () => {
      const found = await get(`/api/v1/controls/${params.key}`, null, { fresh: true });
      return { ...found.data, governs: can("govern") };
    },
    view: (control, reload) => {
      document.title = control.title;
      const program = control.scope === "program";
      const inPlace = control.records.filter((r) => r.status === "implemented").length;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/controls" }, icon("chevron-left", "icon icon-sm"), "Controls"),
        pageHeader({ eyebrow: `Control · ${control.category_label}`, title: control.title, lede: control.statement,
          actions: program ? [statusPill(control), control.can_set ? button("Set how it stands…", { kind: "btn-primary", onclick: () => setStanding(control, null, reload, control.governs) }) : null] : null }),
        h("div", { class: "split" },
          program ? card({ title: "How it stands for the program" }, h("dl", { class: "facts" },
            h("dt", {}, "Standing"), h("dd", {}, STATUS[control.status][0]),
            h("dt", {}, "How it is done"), h("dd", {}, control.note ?? "Nothing recorded yet"),
            h("dt", {}, "Owner"), h("dd", {}, control.owner ?? "Nobody"),
            h("dt", {}, "Next check"), h("dd", {}, control.next_check_on ? date(control.next_check_on) : "No date")))
            : card({ title: "Where it applies", flush: true, actions: h("span", { class: "subtle" }, `${inPlace} of ${control.records.length} in place`) },
              control.records.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
                h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Record"), h("th", { scope: "col" }, "Standing"), h("th", { scope: "col" }, "Owner"), h("th", { scope: "col" }, "Next check"))),
                h("tbody", {}, control.records.map((record) => h("tr", {},
                  h("td", {}, h("a", { class: "cell-main", href: `/controls?record=${record.ref}` }, record.name), h("div", { class: "cell-sub" }, record.ref)),
                  h("td", {}, statusPill(record)), h("td", {}, record.owner ?? ""),
                  h("td", { class: "nowrap" }, record.next_check_on ? date(record.next_check_on) : ""))))))
                : h("p", { class: "muted card-pad" }, "It applies to no record you can see.")),
          h("div", { class: "stack-lg" },
            card({ title: "About this control" }, h("dl", { class: "facts" },
              h("dt", {}, "Applies to"), h("dd", {}, program ? "The program as a whole" : kinds(control.applies_to)),
              h("dt", {}, "Checked"), h("dd", {}, `Every ${control.check_months} months`))),
            control.risks.length ? card({ title: "Risks it answers" }, h("ul", {}, control.risks.map((risk) => h("li", {}, risk.title)))) : null)));
    },
  });
}
