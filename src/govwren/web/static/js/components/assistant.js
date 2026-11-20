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
  const words = field("Describe it in your own words", { type: "textarea", rows: 4, maxlength: 4000,
    placeholder: "Such as: Our research nurses want to use the enterprise chat assistant to summarize clinic notes into short case summaries for the weekly trial meeting. The notes are about patients and include health information. A nurse reads and corrects every summary before it is used. Only our lab uses it.",
    hint: "An AI assistant fills in what your words say or plainly imply, marks each answer it gives, and leaves the rest for you. The more you say about the tool, the data, who is affected, and who checks what it produces, the more it can fill in. Describe the data; do not paste any here." });
  const problem = banner();
  const said = h("div", { "aria-live": "polite" });
  const go = button("Suggest answers", { type: "button" });
  go.addEventListener("click", async () => {
    said.replaceChildren();
    const found = await submit({ button: go, banner: problem, fields: { description: words },
      run: () => post("/api/v1/assistant/draft", { description: words.input.value }) });
    go.disabled = false;
    if (!found) return;
    const filled = apply(found.data.answers);
    const count = filled.length;
    // Say which questions were filled, and on which step, since most are not on the step in
    // view. A short description answers little: say so, and what would help.
    const steps = new Map();
    for (const item of filled) {
      if (!steps.has(item.step)) steps.set(item.step, { open: item.open, labels: [] });
      steps.get(item.step).labels.push(item.label);
    }
    const thin = count < 4 ? "Your description did not say enough for more. Add what kind of data is involved, who is affected, and who checks what it produces, then ask again, or answer the rest yourself." : null;
    said.replaceChildren(alert("info", icon("info"), h("div", { class: "stack-sm" },
      h("div", {}, h("strong", {}, count ? `${count} ${count === 1 ? "answer was" : "answers were"} suggested. ` : "Nothing could be suggested from that. "),
        count ? "Each is marked “Suggested by the assistant” in the form. Read each one and correct it before you submit." : "Add more about what you want to do, with which tool and what data, and ask again, or answer the questions below yourself."),
      count ? h("ul", { class: "suggested-list" }, [...steps].map(([title, where]) => h("li", {},
        h("button", { type: "button", class: "link-button", onclick: where.open }, title), ": ", where.labels.join("; ")))) : null,
      thin ? h("div", {}, thin) : null)));
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
