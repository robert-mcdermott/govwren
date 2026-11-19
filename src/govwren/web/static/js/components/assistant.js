// The optional assistant. Nothing here is drawn unless the server says one is configured.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { dateTime } from "../core/format.js";
import { banner, field, submit } from "./form.js";
import { alert, card, emptyState, pageHeader, pill } from "./ui.js";
import { show } from "../pages/page.js";

let on = false;

export function setAssistant(value) {
  on = Boolean(value);
}

export function assistantOn() {
  return on;
}

/** On a new request: describe it in your own words, and have answers suggested. */
export function draftBox(apply) {
  if (!on) return null;
  const words = field("Describe it in your own words", { type: "textarea", rows: 3, maxlength: 4000,
    hint: "A sentence or two about what you want to do. Describe the data; do not paste any here. An AI assistant will suggest answers for you to check." });
  const problem = banner();
  const said = h("div", { "aria-live": "polite" });
  const go = button("Suggest answers", { type: "button" });
  go.addEventListener("click", async () => {
    said.replaceChildren();
    const found = await submit({ button: go, banner: problem, fields: { description: words },
      run: () => post("/api/v1/assistant/draft", { description: words.input.value }) });
    go.disabled = false;
    if (!found) return;
    const count = apply(found.data.answers);
    said.replaceChildren(alert("info", icon("info"), h("div", {},
      h("strong", {}, count ? `${count} ${count === 1 ? "answer was" : "answers were"} suggested. ` : "Nothing could be suggested from that. "),
      count ? "They are in the form below, written by an AI assistant. Read each one and correct it before you submit." : "Answer the questions below yourself.")));
  });
  return card({ title: "Start from a description" }, h("div", { class: "stack" }, problem, words.node, h("div", {}, go), said));
}

/** The assistant's words as paragraphs and lists. Text only: nothing in them is run or linked. */
function prose(text) {
  const out = [];
  let list = null;
  for (const line of text.split("\n").map((each) => each.trim()).filter(Boolean)) {
    const point = /^[-*•]\s+(.*)$/.exec(line);
    if (point) {
      if (!list) out.push(list = h("ul", { class: "bullets" }));
      list.append(h("li", {}, point[1]));
    } else {
      list = null;
      out.push(h("p", {}, line));
    }
  }
  return h("div", { class: "stack-sm" }, out);
}

/** On a review, for the people working on it: a summary, clearly the assistant's. */
export function summaryPanel(ref) {
  if (!on) return null;
  const out = h("div", { "aria-live": "polite" });
  const go = button("Summarize with the assistant", { kind: "btn-sm" });
  go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      const made = (await post(`/api/v1/reviews/${ref}/summary`)).data;
      out.replaceChildren(h("div", { class: "stack-sm" },
        h("div", { class: "row-sm wrap" }, pill("Written by an AI assistant", "warn"), h("span", { class: "subtle" }, made.model)),
        prose(made.summary),
        h("p", { class: "subtle" }, made.note)));
    } catch (error) {
      out.replaceChildren(alert("warn", icon("alert"), h("div", {}, Object.values(error.fields ?? {}).join(" ") || error.detail || "The assistant could not be asked.")));
    }
    go.disabled = false;
  });
  return card({ title: "Summary", actions: go }, out.childNodes.length ? out : h("div", {}, h("p", { class: "muted" }, "A short summary of this packet, for orientation. It is not part of the record."), out));
}

/** Everything that has been asked of the assistant, for those who read everything. */
export function assistantLog(main) {
  return show(main, {
    title: "Assistant",
    load: async () => (await get("/api/v1/assistant/exchanges", null, { fresh: true })).data,
    view: (data) => h("div", { class: "stack-lg" },
      pageHeader({ title: "Assistant", lede: data.enabled
        ? `Everything asked of the assistant and what it answered. It is the model ${data.model}, and is never shown a request above the data class ${data.max_data_class}.`
        : "No assistant is configured. What was asked of one in the past is kept here." }),
      data.exchanges.length ? h("div", { class: "stack" }, data.exchanges.map((item) => card({
        title: `${item.purpose === "draft" ? "Suggested answers for a request" : `Summary of ${item.subject}`}`,
        actions: item.ok ? pill("Answered", "ok") : pill("Failed", "danger"),
      }, h("div", { class: "stack-sm" },
        h("p", { class: "subtle" }, `${item.by ?? "Someone"} · ${dateTime(item.at)} · ${item.model}`),
        item.error ? h("p", { class: "due-late" }, item.error) : null,
        h("details", {}, h("summary", {}, "What was sent"), h("pre", { class: "exchange" }, item.prompt)),
        item.response ? h("details", {}, h("summary", {}, "What came back"), h("pre", { class: "exchange" }, item.response)) : null))))
        : emptyState({ iconName: "note", title: "Nothing has been asked of the assistant" })),
  });
}
