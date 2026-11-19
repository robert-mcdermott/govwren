// The catalog: the AI tools the organization has looked at, what each may be used with, and
// the short way to register a use that fits.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { plural } from "../core/format.js";
import { label, options, unitOptions, units, vocabularies } from "../core/lookups.js";
import { navigate, query, setQuery } from "../core/router.js";
import { can, session } from "../core/session.js";
import { banner, checkbox, field, select, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { standingPill } from "../components/record.js";
import { toast } from "../components/toast.js";
import { alert, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const NOTES = {
  under_evaluation: "Being evaluated. Not for use yet.",
  not_approved: "Not approved for use.",
};

function register(system, data) {
  openOverlay({
    title: `Register a use of ${system.name}`,
    subtitle: "If it fits what this tool is approved for, it is approved straight away.",
    render: (body, footer, close) => {
      const me = session();
      const own = new Set([...(me.member_units ?? []), ...(me.steward_units ?? [])]);
      const offered = can("edit_all") || !own.size ? null : own;
      const unitChoices = unitOptions(data.units.tree, { only: offered, blank: "Choose a unit" });
      const name = field("What will you use it for?", { maxlength: 400, hint: "A short name, such as “Drafting grant summaries”." });
      const unit = select("Which unit is this for?", unitChoices, { value: unitChoices.length === 2 ? unitChoices[1][0] : "" });
      const dataClass = select("The most sensitive data involved", options(data.vocab, "data_classes", { blank: "Choose a class" }),
        { hint: system.permitted_data_class ? `This tool is approved for data up to ${label(data.vocab, "data_classes", system.permitted_data_class)}.` : null });
      const categories = options(data.vocab, "data_categories").map(([key, text]) => ({ key, ...checkbox(text) }));
      const everyday = checkbox("It only produces drafts, summaries, or answers that a person checks", {
        hint: "It makes no decisions about people and takes no actions of its own." });
      const problem = banner();
      const save = button("Register", { kind: "btn-primary" });
      const form = h("form", { class: "stack", novalidate: true }, problem, name.node, unit.node, dataClass.node,
        h("fieldset", { class: "stack-sm" }, h("legend", { class: "label" }, "Does it involve any of these?"),
          h("div", { class: "grid-2" }, categories.map((item) => item.node))),
        h("fieldset", { class: "stack-sm" }, h("legend", { class: "label" }, "How will it be used?"), everyday.node));
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const done = await submit({ button: save, banner: problem,
          fields: { name, org_unit_id: unit, data_class: dataClass },
          run: () => post(`/api/v1/catalog/${system.ref}/register`, {
            name: name.input.value, org_unit_id: unit.input.value ? Number(unit.input.value) : null,
            data_class: dataClass.input.value || null,
            data_categories: categories.filter((item) => item.input.checked).map((item) => item.key),
            everyday: everyday.input.checked }) });
        if (!done) return;
        close();
        if (done.data.registered) {
          toast("Registered and approved. The terms of use are on the record.");
          navigate(`/use-cases/${done.data.ref}`);
        } else {
          toast(`This needs a short request. ${done.data.reason} What you entered has been carried over.`, { duration: 9000 });
          navigate(`/use-cases/${done.data.ref}/request`);
        }
      });
      save.addEventListener("click", () => form.requestSubmit());
      body.append(form);
      footer.replaceChildren(h("div", { class: "row" }, save, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

// The rule that health information needs a covering agreement, and the switch for it.
function healthRule(settings, reload) {
  const on = settings.health_agreement_rule;
  const change = button(on ? "Turn off" : "Turn on", { kind: "btn-sm", onclick: async () => {
    change.disabled = true;
    await put("/api/v1/admin/inventory", { health_agreement_rule: !on });
    toast(on ? "The rule is off." : "The rule is on.");
    reload();
  } });
  return card({ title: "Health information needs a covering agreement", actions: [pill(on ? "On" : "Off", on ? "ok" : ""), change] },
    h("p", { class: "muted" }, on
      ? "A use that involves health information is not approved while a tool it uses is hosted by a supplier and no agreement covering health information names that tool. De-identified data, tools on your own equipment, and an approved exception are let through."
      : "Each tool still shows whether an agreement covers it, but nothing is stopped. Turn this on once your agreements are recorded."));
}

function entry(system, data) {
  const excluded = (system.excluded_data_categories ?? []).map((key) => label(data.vocab, "data_categories", key).toLowerCase());
  const facts = [];
  if (system.usable && system.permitted_data_class) {
    facts.push(["Data", `Up to ${label(data.vocab, "data_classes", system.permitted_data_class)}`]);
  }
  if (system.usable && excluded.length) facts.push(["Not for", excluded.join(", ")]);
  const health = { in_place: "Covered by an agreement", not_needed: "Runs on our own equipment", ended: "The agreement has ended",
    available: "No agreement yet", not_offered: "The vendor will not sign an agreement", unknown: "No agreement recorded" }[system.health_agreement];
  if (system.usable && health) facts.push(["Health information", health]);
  if (system.usable && system.trains_on_inputs) {
    facts.push(["Training", { yes: "Trains on what you enter", no: "Does not train on what you enter", unknown: "Not known whether it trains on what you enter" }[system.trains_on_inputs]]);
  }
  return h("li", { class: "card catalog-entry", "data-usable": String(system.usable) },
    h("div", { class: "catalog-head" },
      h("span", { class: "catalog-icon" }, icon(system.type === "model" ? "model" : "system")),
      h("div", { class: "grow" },
        h("h2", {}, h("a", { href: `/${system.type === "model" ? "models" : "systems"}/${system.ref}` }, system.name)),
        h("div", { class: "cell-sub" }, system.type === "model"
          ? ["Model", label(data.vocab, "model_origins", system.origin), system.vendor, system.edition].filter(Boolean).join(" · ")
          : [system.vendor, system.edition].filter(Boolean).join(" · ") || label(data.vocab, "system_kinds", system.kind))),
      standingPill(system.catalog_status)),
    system.summary ? h("p", { class: "catalog-summary" }, system.summary) : null,
    facts.length ? h("dl", { class: "catalog-facts" }, facts.map(([term, text]) => [h("dt", {}, term), h("dd", {}, text)])) : null,
    system.usable && system.terms ? h("p", { class: "catalog-terms" }, h("strong", {}, "Terms of use. "), system.terms) : null,
    h("div", { class: "catalog-foot" },
      system.usable
        ? [h("span", { class: "subtle" }, system.uses ? `${plural(system.uses, "registered use")}` : "No registered uses yet"),
          button("Register my use", { kind: "btn-primary btn-sm", onclick: () => register(system, data) })]
        : h("span", { class: "muted" }, NOTES[system.catalog_status] ?? "")));
}

function ask(reload, name = "") {
  openOverlay({
    title: "Ask for a tool to be evaluated",
    subtitle: "For a tool that is not in the catalog. Governance looks at it, and you are told the answer.",
    kind: "dialog",
    render: (body, footer, close) => {
      const tool = field("Which tool?", { value: name, required: true, hint: "Its name and, if you know it, the plan or edition." });
      const why = field("What do you want to use it for?", { type: "textarea", required: true });
      const url = field("Its website", { type: "url", placeholder: "https://", hint: "Optional." });
      const problem = banner();
      const send = button("Send", { kind: "btn-primary" });
      send.addEventListener("click", async () => {
        const done = await submit({ button: send, banner: problem, fields: { name: tool, reason: why, url },
          run: () => post("/api/v1/catalog/requests", { name: tool.input.value, reason: why.input.value, url: url.input.value || null }) });
        if (done) {
          close();
          toast(`Sent. You will be told when ${done.data.name} has been looked at.`);
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, tool.node, why.node, url.node));
      footer.replaceChildren(h("div", { class: "row" }, send, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}

function askedCard(asked, everyone) {
  if (!asked.length) return null;
  return card({ title: everyone ? "Tools people have asked about" : "You have asked about", flush: true },
    h("ul", {}, asked.map((entry) => h("li", { class: "list-row" },
      h("div", { class: "grow" }, h("a", { class: "cell-main", href: `/systems/${entry.ref}` }, entry.name),
        h("div", { class: "cell-sub" }, everyone ? entry.requests.map((request) => `${request.by}: ${request.reason}`).join(" · ") : entry.requests[0].reason)),
      everyone ? pill(plural(entry.requests.length, "person", "people"), entry.requests.length > 1 ? "accent" : "") : null,
      standingPill(entry.catalog_status)))));
}

export function catalog(main) {
  return show(main, {
    title: "Catalog",
    load: async () => {
      const [list, vocab, unitIndex, asked, settings] = await Promise.all([
        get("/api/v1/catalog", null, { fresh: true }), vocabularies(), units(),
        get("/api/v1/catalog/requests", null, { fresh: true }),
        can("configure") ? get("/api/v1/admin/inventory", null, { fresh: true }) : null]);
      return { systems: list.data, vocab, units: unitIndex, asked: asked.data, settings: settings?.data ?? null };
    },
    view: (data, reload) => {
      const list = h("ul", { class: "catalog-grid" });
      const count = h("div", { class: "subtle", role: "status" });
      const search = h("input", { class: "input catalog-search", type: "search", value: query().get("q") ?? "",
        placeholder: "Search by tool, model, or vendor", "aria-label": "Search the catalog" });
      const draw = () => {
        const words = search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
        const found = data.systems.filter((system) => {
          const text = [system.name, system.vendor, system.edition, system.summary].filter(Boolean).join(" ").toLowerCase();
          return words.every((word) => text.includes(word));
        });
        count.textContent = words.length ? `${found.length} of ${plural(data.systems.length, "tool")}` : plural(data.systems.length, "tool");
        list.replaceChildren(...found.map((system) => entry(system, data)));
        if (!found.length) {
          list.append(h("li", { class: "card catalog-none" }, emptyState({ iconName: "search",
            title: data.systems.length ? "Nothing in the catalog matches" : "The catalog is empty",
            text: data.systems.length
              ? "A tool that is not here has not been evaluated yet. Ask about it and it will be looked at."
              : "Tools appear here once governance has evaluated them.",
            action: button("Ask for it to be evaluated", { kind: "btn-primary", onclick: () => ask(reload, search.value.trim()) }) })));
        }
      };
      search.addEventListener("input", () => {
        setQuery({ q: search.value.trim() || null });
        draw();
      });
      draw();
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Catalog", lede: "The AI tools and models that have been evaluated, and what each may be used with.",
          actions: [button("Ask for a tool to be evaluated", { onclick: () => ask(reload) }),
            h("a", { class: "btn", href: "/requests/new" }, "Request a use")] }),
        alert("info", icon("info"), h("div", {}, "Using an approved tool for everyday work with data it is approved for takes a minute to register. Anything else starts a request, and what you enter is carried over.")),
        askedCard(data.asked, can("read_all")),
        can("configure") && data.settings ? healthRule(data.settings, reload) : null,
        h("div", { class: "row wrap" }, search, count),
        list);
    },
  });
}
