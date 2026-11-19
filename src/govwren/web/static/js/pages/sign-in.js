// The sign-in page, shown whenever nobody is signed in.

import { post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { wren } from "../core/icons.js";
import { brand } from "../components/shell.js";
import { banner, field, submit } from "../components/form.js";
import { setTitle } from "./page.js";

const POINTS = [
  "One front door for every AI request",
  "Review in proportion to the risk",
  "A record of every decision, and the reasons for it",
];

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

  const organization = meta.branding.organization_name;
  root.replaceChildren(h("div", { class: "sign-in" },
    h("main", { class: "sign-in-form", id: "main" }, h("div", {},
      h("div", { class: "sign-in-brand" }, brand(meta)),
      h("h1", {}, "Sign in"),
      h("p", { class: "muted" }, organization ? `AI governance at ${organization}.` : "Welcome back."),
      h("div", { class: "stack-lg" }, h("div", {}), form),
      h("p", { class: "sign-in-foot" }, "Trouble signing in? Ask an administrator to reset your password."))),
    h("aside", { class: "sign-in-art", "aria-hidden": "true" },
      wren("wren"),
      h("blockquote", {}, "May I use this?"),
      h("p", {}, "The fastest safe path from that question to an answer you can rely on."),
      h("ul", {}, POINTS.map((point) => h("li", {}, icon("check"), point))))));
  email.input.focus();
}
