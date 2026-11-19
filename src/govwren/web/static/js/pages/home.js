// Home: what you owe, and, for administrators of a new installation, how to set it up.

import { get } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { date, greeting, titleCase } from "../core/format.js";
import { navigate } from "../core/router.js";
import { can, session } from "../core/session.js";
import { avatar, card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

const WORK_ICONS = { triage: "use_case", decide: "check", task: "shield", question: "info", draft: "edit", condition: "alert",
  periodic: "history", change: "edit", attestation: "note", exception: "alert", incident: "bell", action: "check",
  acceptance: "shield", spot_check: "search" };

function setup(data, meta) {
  const steps = [
    { done: data.units.length > 0, title: "Describe your organization",
      text: "Add your divisions, departments, and labs, or import them from a spreadsheet.",
      href: "/admin/units", action: "Units" },
    { done: data.accounts.length > 1, title: "Add the people who will run the program",
      text: "Give governance, reviewer, auditor, and steward roles to the right people.",
      href: "/admin/people", action: "People" },
    { done: Boolean(meta.branding.organization_name || meta.branding.logo_light || meta.branding.accent),
      title: "Make it yours", text: "Set your organization's name, logo, and colors.",
      href: "/admin/appearance", action: "Appearance" },
  ];
  const left = steps.filter((step) => !step.done).length;
  return card({ title: left ? "Set up your installation" : "Your installation is set up", flush: true,
    actions: pill(left ? `${steps.length - left} of ${steps.length} done` : "All done", left ? "info" : "ok") },
  h("ul", { class: "checklist" }, steps.map((step) => h("li", { "data-done": String(step.done) },
    h("span", { class: "check-mark" }, icon("check", "icon icon-sm")),
    h("div", { class: "grow" }, h("div", { class: "cell-main" }, step.title), h("div", { class: "cell-sub" }, step.text)),
    h("a", { class: "btn btn-sm", href: step.href }, step.action)))));
}

function ask() {
  const input = h("input", { class: "input", type: "search", placeholder: "The name of a tool, such as a chat assistant or a coding tool",
    "aria-label": "The tool you want to use" });
  const form = h("form", { class: "ask", role: "search" }, input, button("Look it up", { kind: "btn-primary", type: "submit" }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const q = input.value.trim();
    navigate(q ? `/catalog?q=${encodeURIComponent(q)}` : "/catalog");
  });
  return card({ title: "May I use this AI tool?" }, h("div", { class: "stack" }, form,
    h("p", { class: "subtle" }, "Look a tool up in the ", h("a", { href: "/catalog" }, "catalog"),
      " to see whether it is approved and what it may be used with. If it is not there, ",
      h("a", { href: "/requests/new" }, "ask about it"), ".")));
}

export function home(main, meta) {
  const me = session();
  return show(main, {
    title: "Home",
    load: async () => {
      const work = (await get("/api/v1/me/work", null, { fresh: true })).data;
      if (!can("admin")) return { work };
      const [units, accounts] = await Promise.all([get("/api/v1/units"), get("/api/v1/accounts")]);
      return { work, units: units.data.units, accounts: accounts.data };
    },
    view: (data) => h("div", { class: "stack-lg" },
      pageHeader({ title: `${greeting()}, ${me.account.name.split(" ")[0]}`,
        lede: meta.branding.organization_name ? `AI governance at ${meta.branding.organization_name}.` : null }),
      data.units ? setup(data, meta) : null,
      ask(),
      h("div", { class: "split" },
        card({ title: "Waiting on you", flush: true, actions: data.work.length ? pill(String(data.work.length), "accent") : null },
          data.work.length ? h("ul", {}, data.work.map((item) => h("li", { class: "list-row" },
            h("span", { class: "work-icon", "data-kind": item.kind }, icon(WORK_ICONS[item.kind] ?? "dot")),
            h("div", { class: "grow" }, h("a", { class: "cell-main", href: item.href }, item.title),
              h("div", { class: "cell-sub" }, item.detail)),
            item.due_on ? h("span", { class: `due${item.overdue ? " due-late" : ""}` }, item.overdue ? "Overdue · " : "Due ", date(item.due_on)) : null)))
            : emptyState({ iconName: "check", title: "Nothing needs your attention",
              text: "Requests, review tasks, conditions, and questions that are yours to act on are listed here, overdue first." })),
        card({ title: "Your access" },
          h("div", { class: "stack" },
            h("div", { class: "row" }, avatar(me.account.name, true), h("div", {},
              h("div", { class: "cell-main" }, me.account.name), h("div", { class: "cell-sub" }, me.account.email))),
            h("div", { class: "row-sm wrap" }, me.roles.map((role) => pill(titleCase(role), role === "member" ? "" : "accent"))),
            h("a", { href: "/account" }, "Your account"))))),
  });
}
