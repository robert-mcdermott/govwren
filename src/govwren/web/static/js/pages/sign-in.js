// The sign-in page, shown whenever nobody is signed in.

import { post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { wren } from "../core/icons.js";
import { brand } from "../components/shell.js";
import { banner, field, submit } from "../components/form.js";
import { avatar } from "../components/ui.js";
import { setTitle } from "./page.js";

const POINTS = [
  "One front door for every AI request",
  "Review in proportion to the risk",
  "A record of every decision, and the reasons for it",
];

const SSO_PROBLEMS = {
  cancelled: "Sign-in was cancelled at your organization's sign-in page.",
  expired: "That sign-in took too long or was already used. Please try again.",
  unavailable: "Your organization's sign-in service could not be reached. Try again in a few minutes.",
  refused: "Your organization account could not be used here. Ask whoever looks after GovWren to check your access.",
  failed: "Sign-in did not complete. Please try again.",
};

function safeNext() {
  const next = new URLSearchParams(window.location.search).get("next") || "/";
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function signIn(root, meta) {
  setTitle("Sign in");
  const email = field("Email address", { type: "email", autocomplete: "username", required: true, name: "email" });
  const password = field("Password", { type: "password", autocomplete: "current-password", required: true, name: "password" });
  const problem = banner();
  const go = button("Sign in", { kind: "btn-primary btn-block", type: "submit" });
  const form = h("form", { class: "stack", novalidate: true, onsubmit: async (event) => {
    event.preventDefault();
    const done = await submit({ button: go, fields: { email, password }, banner: problem,
      run: () => post("/api/v1/session", { email: email.input.value, password: password.input.value }) });
    if (done) window.location.assign(safeNext());
    else password.input.select();
  } }, problem, email.node, password.node, go);

  const sample = meta.demo ? h("section", { class: "demo-people", "aria-labelledby": "demo-people-title" },
    h("h2", { id: "demo-people-title" }, "Explore the demo"),
    h("p", { class: "muted" }, "This is a fictional organization. Choose someone to sign in as; no password is needed."),
    h("ul", {}, meta.demo.accounts.map((person) => h("li", {},
      h("button", { type: "button", class: "demo-person", onclick: async (event) => {
        event.currentTarget.disabled = true;
        try {
          await post("/api/v1/session/demo", { email: person.email });
          window.location.assign(safeNext());
        } catch (error) {
          event.currentTarget.disabled = false;
          problem.textContent = error.detail || "That did not work.";
          problem.hidden = false;
        }
      } },
      avatar(person.name),
      h("span", { class: "grow" }, h("span", { class: "cell-main" }, person.name, h("span", { class: "subtle" }, ` · ${person.title}`)),
        h("span", { class: "cell-sub" }, person.about)),
      icon("chevron-right", "icon icon-sm")))))) : null;

  const next = safeNext();
  const failed = new URLSearchParams(window.location.search).get("sso");
  const sso = meta.sso && !sample ? h("div", { class: "stack" },
    failed ? h("div", { class: "alert alert-danger", role: "alert" }, SSO_PROBLEMS[failed] ?? SSO_PROBLEMS.failed) : null,
    h("a", { class: "btn btn-primary btn-block", href: `/api/v1/sso/start?next=${encodeURIComponent(next)}` }, meta.sso.label)) : null;
  const local = !sso ? form : h("details", { class: "local-sign-in", open: failed === "refused" ? null : undefined },
    h("summary", {}, meta.sso.local_sign_in ? "Sign in with a password instead" : "Administrator sign-in"),
    h("div", { class: "stack" }, h("div", {}), form));

  const organization = meta.branding.organization_name;
  root.replaceChildren(h("div", { class: "sign-in" },
    h("main", { class: "sign-in-form", id: "main" }, h("div", {},
      h("div", { class: "sign-in-brand" }, brand(meta)),
      h("h1", {}, "Sign in"),
      h("p", { class: "muted" }, organization ? `AI governance at ${organization}.` : "Welcome back."),
      sample ? h("div", { class: "stack-lg" }, h("div", {}), problem, sample)
        : h("div", { class: "stack-lg" }, h("div", {}), sso, local),
      h("p", { class: "sign-in-foot" }, sample ? `Demo data, built ${meta.demo.built_on}. Nothing here is real.`
        : sso ? "Trouble signing in? Ask whoever looks after GovWren in your organization."
          : "Trouble signing in? Ask an administrator to reset your password."))),
    h("aside", { class: "sign-in-art", "aria-hidden": "true" },
      wren("wren"),
      h("blockquote", {}, "May I use this?"),
      h("p", {}, "The fastest safe path from that question to an answer you can rely on."),
      h("ul", {}, POINTS.map((point) => h("li", {}, icon("check"), point))))));
  if (!sample && !sso) email.input.focus();
}
