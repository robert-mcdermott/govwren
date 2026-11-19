// The transparency register: the approved uses chosen for publication, and their words.

import { del, get, put } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date } from "../core/format.js";
import { banner, checkbox, field, submit } from "../components/form.js";
import { openOverlay } from "../components/overlay.js";
import { standingPill } from "../components/record.js";
import { toast } from "../components/toast.js";
import { card, emptyState, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

function edit(entry, reload) {
  const ref = field("Use case", { value: entry?.ref ?? "", placeholder: "UC-0042", hint: "Its reference. It must have an approval in force.", disabled: Boolean(entry) });
  const title = field("Title", { value: entry?.title ?? "", maxlength: 200, hint: "What a reader outside the program would call it." });
  const description = field("Description", { type: "textarea", rows: 7, value: entry?.description ?? "",
    hint: "Plain words: what the AI does, for whom, and what a person still decides. Leave a blank line between paragraphs." });
  const unit = checkbox("Name the unit", { checked: entry?.show_unit ?? true, hint: "Untick to publish without saying which unit it is." });
  const fields = { ref, title, description };
  openOverlay({
    title: entry ? "Change the published words" : "Put a use on the register", subtitle: entry ? `${entry.ref} · ${entry.record_name}` : "It appears the next time the pages are published.", kind: "drawer",
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button(entry ? "Save" : "Put it on the register", { kind: "btn-primary" });
      go.addEventListener("click", async () => {
        const wanted = ref.input.value.trim().toUpperCase();
        if (!wanted) {
          ref.setError("Give the reference of a use case.");
          return;
        }
        const done = await submit({ button: go, banner: problem, fields, run: () => put(`/api/v1/use-cases/${wanted}/register`,
          { title: title.input.value, description: description.input.value, show_unit: unit.input.checked }) });
        if (done) {
          shut();
          toast(entry ? "The words were changed." : "It is on the register.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, ref.node, title.node, description.node, unit.node));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

function takeOff(entry, reload) {
  openOverlay({
    title: "Take it off the register?", subtitle: entry.title, kind: "dialog",
    render: (body, footer, shut) => {
      const problem = banner();
      const go = button("Take it off", { kind: "btn-danger" });
      go.addEventListener("click", async () => {
        if (await submit({ button: go, banner: problem, run: () => del(`/api/v1/use-cases/${entry.ref}/register`) })) {
          shut();
          toast("It is off the register.");
          reload();
        }
      });
      body.append(h("div", { class: "stack" }, problem, h("p", {}, "Its page is left out the next time the pages are published. The use case itself is not changed.")));
      footer.replaceChildren(h("div", { class: "row" }, go, button("Cancel", { kind: "btn-ghost", onclick: shut })));
      footer.hidden = false;
    },
  });
}

export function registerPage(main) {
  return show(main, {
    title: "Register",
    load: async () => (await get("/api/v1/register", null, { fresh: true })).data,
    view: (data, reload) => {
      const held = data.entries.length - data.published;
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Transparency register", lede: "The approved uses chosen for publication, each in words written for readers outside the program. The pages are plain files for any web server.",
          actions: [data.entries.length ? h("a", { class: "btn", href: "/api/v1/register/preview/index.html", target: "_blank", rel: "noopener" }, "Preview") : null,
            data.entries.length ? h("a", { class: "btn", href: "/api/v1/register/pages", download: "register.zip" }, "Download the pages") : null,
            data.can_change ? button("Put a use on the register", { kind: "btn-primary", iconName: "plus", onclick: () => edit(null, reload) }) : null] }),
        data.entries.length ? h("p", { class: "muted" }, `${data.published} ${data.published === 1 ? "use is" : "uses are"} published.`,
          held ? ` ${held} ${held === 1 ? "is" : "are"} held back because the approval is not in force.` : "") : null,
        data.entries.length ? h("div", { class: "stack" }, data.entries.map((entry) => card({
          title: entry.title,
          actions: data.can_change ? h("div", { class: "row-sm" }, button("Change", { "aria-label": `Change the words for ${entry.title}`, onclick: () => edit(entry, reload) }),
            button("Take off", { kind: "btn-ghost", "aria-label": `Take ${entry.title} off the register`, onclick: () => takeOff(entry, reload) })) : null,
        }, h("div", { class: "stack-sm" },
          h("div", { class: "row-sm wrap" }, entry.published ? pill("Published", "ok") : pill("Held back", "warn"), entry.published ? null : standingPill(entry.status),
            h("a", { href: `/use-cases/${entry.ref}` }, `${entry.ref} · ${entry.record_name}`)),
          entry.description.split(/\n{2,}/).map((paragraph) => h("p", {}, paragraph)),
          h("p", { class: "subtle" }, [entry.area, entry.show_unit ? entry.unit : "Unit not named", entry.tools.length ? `Uses ${entry.tools.join(", ")}` : null,
            entry.approved_on ? `First approved ${date(entry.approved_on)}` : null].filter(Boolean).join(" · "))))))
          : emptyState({ iconName: "external", title: "Nothing is on the register yet", text: "Choose an approved use and write a few plain sentences about it. Nothing is published until you put the pages on a web server." }));
    },
  });
}
