// What a connected registry suggests for a record: each one accepted or dismissed by a person.

import { post } from "../core/api.js";
import { button, h } from "../core/dom.js";
import { date } from "../core/format.js";
import { toast } from "./toast.js";
import { card } from "./ui.js";

const shown = (value) => value == null || value === "" ? h("span", { class: "subtle" }, "Not set")
  : /^\d{4}-\d\d-\d\d$/.test(value) ? date(value) : String(value);

/** The card on a record's page, or nothing if no suggestion is waiting. */
export function suggestionsCard(suggestions, reload) {
  if (!suggestions?.length) return null;
  const decide = (item, verb, done) => async (event) => {
    event.currentTarget.disabled = true;
    try {
      await post(`/api/v1/suggestions/${item.id}/${verb}`);
      toast(done);
    } catch (error) {
      toast(error.detail || "That did not work.");
    }
    reload();
  };
  return card({ title: "Suggested by the model registry" },
    h("p", { class: "muted" }, "The registry says something different from this record. Nothing changes unless you accept it."),
    h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["Field", "Here", "In the registry", ""].map((heading) => h("th", { scope: "col" }, heading || h("span", { class: "sr-only" }, "Actions"))))),
      h("tbody", {}, suggestions.map((item) => h("tr", {},
        h("th", { scope: "row" }, item.label), h("td", {}, shown(item.current)), h("td", { class: "cell-main" }, shown(item.proposed)),
        h("td", {}, item.can_decide ? h("div", { class: "row-sm" },
          button("Accept", { kind: "btn-sm", "aria-label": `Accept the registry's ${item.label.toLowerCase()}`, onclick: decide(item, "accept", "The record was changed.") }),
          button("Dismiss", { kind: "btn-sm btn-ghost", "aria-label": `Dismiss the registry's ${item.label.toLowerCase()}`, onclick: decide(item, "dismiss", "Dismissed. It will not be suggested again.") })) : null)))))));
}
