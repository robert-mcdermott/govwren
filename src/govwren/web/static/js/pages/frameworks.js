// Frameworks: those loaded, and readiness against one. Readiness is worked out from how the
// controls stand; nothing on this page is typed in except that a requirement does not apply.

import { del, get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date } from "../core/format.js";
import { navigate } from "../core/router.js";
import { banner, field, submit } from "../components/form.js";
import { confirmAction, openOverlay } from "../components/overlay.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const STATES = { covered: ["Covered", "ok"], partly: ["Partly covered", "warn"], gap: ["A gap", "danger"],
  not_mapped: ["Not mapped", ""], not_applicable: ["Does not apply", ""] };
const LEVELS = { full: "ok", partial: "warn", none: "" };

function summary(counts) {
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0) || 1;
  const bar = h("div", { class: "state-bar", role: "img", "aria-label": Object.entries(counts).map(([key, count]) => `${count} ${STATES[key][0].toLowerCase()}`).join(", ") },
    Object.entries(counts).filter(([, count]) => count).map(([key, count]) => {
      const part = h("span", { "data-state": key });
      part.style.setProperty("--share", `${(count / total) * 100}%`);
      return part;
    }));
  return h("div", { class: "stack-sm" }, bar,
    h("div", { class: "row-sm wrap" }, Object.entries(counts).map(([key, count]) => pill(`${count} ${STATES[key][0].toLowerCase()}`, STATES[key][1]))));
}

export function frameworkList(main) {
  return show(main, {
    title: "Frameworks",
    load: async () => (await get("/api/v1/frameworks", null, { fresh: true })).data,
    view: (data, reload) => h("div", { class: "stack-lg" },
      pageHeader({ title: "Frameworks", lede: "An outside framework is optional. The controls stand on their own; a framework shows how they answer someone else's list of requirements.",
        actions: h("a", { class: "btn", href: "/api/v1/statement-of-applicability", download: "statement-of-applicability.csv" }, "Statement of applicability") }),
      data.loaded.length ? data.loaded.map((framework) => card({ title: h("a", { href: `/frameworks/${framework.key}` }, framework.title),
        actions: framework.version ? h("span", { class: "subtle" }, `Version ${framework.version}`) : null }, summary(framework.counts)))
        : emptyState({ iconName: "note", title: "No framework is loaded", text: "Nothing is missing without one. Load one if you are asked to show readiness against it." }),
      data.available.length ? card({ title: "Built in, not loaded" }, h("ul", { class: "rows" }, data.available.map((framework) => h("li", { class: "row wrap" },
        h("div", { class: "grow" }, h("div", { class: "cell-main" }, framework.title), h("div", { class: "cell-sub" }, framework.attribution ?? "")),
        data.can_load ? button("Load it", { kind: "btn-sm", "aria-label": `Load ${framework.title}`, onclick: async () => {
          await post("/api/v1/frameworks", { key: framework.key });
          toast(`${framework.title} was loaded.`);
          reload();
        } }) : null)))) : null),
  });
}

function exempt(framework, requirement, reload) {
  openOverlay({
    title: "This requirement does not apply", subtitle: requirement.code, kind: "dialog",
    render: (body, footer, shut) => {
      const why = field("Why it does not apply to the organization", { type: "textarea", hint: "Shown with the requirement, and exported with it." });
      const problem = banner();
      const go = button("Save", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const done = await submit({ button: go, banner: problem, fields: { justification: why },
          run: () => put(`/api/v1/frameworks/${framework.key}/applicability`, { code: requirement.code, applies: false, justification: why.input.value }) });
        if (done) {
          shut();
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, h("p", { class: "muted" }, requirement.text ?? requirement.title), why.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function frameworkPage(main, params) {
  return show(main, {
    title: "Framework",
    load: async () => (await get(`/api/v1/frameworks/${params.key}`, null, { fresh: true })).data,
    view: (framework, reload) => {
      document.title = framework.title;
      const restore = async (requirement) => {
        await put(`/api/v1/frameworks/${framework.key}/applicability`, { code: requirement.code, applies: true });
        reload();
      };
      const leaf = (requirement) => h("li", { class: "stack-sm" },
        h("div", { class: "row wrap" },
          h("div", { class: "grow" }, h("div", { class: "cell-main" }, requirement.code), h("div", {}, requirement.text ?? requirement.title)),
          h("div", { class: "row-sm wrap" }, pill(...STATES[requirement.state]),
            framework.can_change && requirement.state !== "not_applicable" ? button("Does not apply…", { kind: "btn-sm btn-ghost", "aria-label": `${requirement.code} does not apply`, onclick: () => exempt(framework, requirement, reload) }) : null,
            framework.can_change && requirement.state === "not_applicable" ? button("It applies", { kind: "btn-sm btn-ghost", "aria-label": `${requirement.code} applies`, onclick: () => restore(requirement) }) : null)),
        requirement.justification ? h("div", { class: "cell-sub" }, `Why it does not apply: ${requirement.justification}`) : null,
        requirement.controls.length ? h("ul", { class: "behind" }, requirement.controls.map((control) => h("li", { class: "row-sm wrap" },
          pill(control.level === "full" ? "In place" : control.level === "partial" ? "Partly" : "Not yet", LEVELS[control.level]),
          h("a", { href: `/controls/${control.key}` }, control.title), h("span", { class: "subtle" }, control.detail))))
          : requirement.state === "not_mapped" ? h("div", { class: "cell-sub" }, "No control in the library is mapped to this. It is never counted as covered.") : null);
      const remove = framework.can_change ? button("Remove", { kind: "btn-ghost", onclick: () => confirmAction({
        title: `Remove ${framework.title}?`, text: "Controls, their standing, and their evidence are not touched. You can load it again.", confirmLabel: "Remove", danger: true,
        run: async () => {
          await del(`/api/v1/frameworks/${framework.key}`);
          toast("Removed.");
          navigate("/frameworks");
        } }) }) : null;
      return h("div", { class: "stack-lg" },
        h("a", { class: "back-link", href: "/frameworks" }, icon("chevron-left", "icon icon-sm"), "Frameworks"),
        pageHeader({ eyebrow: [framework.publisher, framework.version ? `Version ${framework.version}` : null].filter(Boolean).join(" · "), title: framework.title,
          lede: `Readiness across ${framework.total} requirements, worked out from how the controls stand. Loaded ${date(framework.loaded_at)}.`,
          actions: [h("a", { class: "btn", href: `/api/v1/statement-of-applicability?framework=${encodeURIComponent(framework.key)}`, download: `statement-of-applicability-${framework.key}.csv` }, "Statement of applicability"), remove] }),
        framework.attribution ? alert("info", icon("info"), h("div", {}, framework.attribution, framework.source_url ? [" ", h("a", { href: framework.source_url, target: "_blank", rel: "noopener noreferrer" }, "The source")] : null)) : null,
        card({ title: "Where it stands" }, summary(framework.counts)),
        framework.requirements.map((group) => card({ title: group.title ? `${group.code}: ${group.title}` : group.code },
          h("div", { class: "stack" }, group.text && group.children.length ? h("p", { class: "muted" }, group.text) : null,
            h("ul", { class: "rows" }, (group.children.length ? group.children : [group]).map(leaf))))));
    },
  });
}
