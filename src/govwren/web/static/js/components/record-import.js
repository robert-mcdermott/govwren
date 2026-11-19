// Import records from a spreadsheet saved as CSV: say which column is which field, check
// the file, read the report, then import.

import { upload } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { report } from "./importer.js";
import { openOverlay } from "./overlay.js";
import { TYPES } from "./record.js";
import { toast } from "./toast.js";
import { alert } from "./ui.js";

export function openRecordImport({ type, onDone }) {
  const meta = TYPES[type];
  openOverlay({
    title: `Import ${meta.nouns}`,
    subtitle: "From a spreadsheet saved as CSV, with a header row. Nothing is changed until every row is good.",
    render: (body, footer, close) => {
      const file = h("input", { type: "file", class: "input", accept: ".csv,text/csv", "aria-label": "CSV file" });
      const mapper = h("div", {});
      const result = h("div", { "aria-live": "polite" });
      const check = button("Check the file", { kind: "btn-primary", disabled: true });
      const apply = button("Import", { kind: "btn-primary", hidden: true });
      let text = null;
      let selects = new Map();
      const mapping = () => JSON.stringify(Object.fromEntries([...selects].map(([header, select]) => [header, select.value])));
      const fail = (error) => {
        const detail = Object.values(error.fields ?? {}).join(" ") || error.detail || "The file could not be read.";
        result.replaceChildren(alert("danger", icon("alert"), h("div", {}, detail)));
      };
      const send = (params) => upload(`/api/v1/imports/records/${meta.path}`, new Blob([text], { type: "text/csv" }), params);
      const drawMapping = (data) => {
        selects = new Map();
        mapper.replaceChildren(h("div", { class: "stack-sm" },
          h("h3", { class: "bars-title" }, "Which column is which?"),
          h("div", { class: "table-wrap" }, h("table", { class: "table mapping" },
            h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Column in your file"), h("th", { scope: "col" }, "Field in GovWren"))),
            h("tbody", {}, data.headers.map((header) => {
              const select = h("select", { class: "select", "aria-label": `Field for the column ${header}` },
                h("option", { value: "" }, "Leave out"),
                data.fields.map((field) => h("option", { value: field.key, selected: data.mapping[header] === field.key },
                  field.required ? `${field.label} (needed)` : field.label)));
              select.addEventListener("change", () => {
                apply.hidden = true;
                check.hidden = false;
                result.replaceChildren();
              });
              selects.set(header, select);
              return h("tr", {}, h("th", { scope: "row" }, header), h("td", {}, select));
            }))))));
      };
      const run = async (dryRun) => {
        const active = dryRun ? check : apply;
        active.disabled = true;
        try {
          const answer = await send({ dry_run: dryRun, mapping: mapping() });
          if (!dryRun && answer.data.applied) {
            close();
            toast(`Imported: ${answer.data.created} added, ${answer.data.updated} changed.`);
            onDone?.();
            return;
          }
          result.replaceChildren(report({ ...answer.data, problems: answer.data.problems }));
          const ready = !answer.data.problems.length && (answer.data.created + answer.data.updated) > 0;
          apply.hidden = !ready;
          check.hidden = ready;
        } catch (error) {
          fail(error);
        } finally {
          active.disabled = false;
        }
      };
      file.addEventListener("change", async () => {
        text = file.files[0] ? await file.files[0].text() : null;
        check.disabled = !text;
        check.hidden = false;
        apply.hidden = true;
        result.replaceChildren();
        mapper.replaceChildren();
        if (!text) return;
        try {
          drawMapping((await send({ dry_run: true })).data); // the first look only guesses the mapping
        } catch (error) {
          fail(error);
          check.disabled = true;
        }
      });
      check.addEventListener("click", () => run(true));
      apply.addEventListener("click", () => run(false));
      body.append(h("div", { class: "stack-lg" },
        h("p", { class: "muted" }, `Each row becomes one ${meta.noun}. A row whose name matches a record already here changes that record; map a column to Reference to say exactly which.`,
          type === "system" || type === "model" ? " Import vendors first, so that rows can name them." : ""),
        file, mapper, result));
      footer.replaceChildren(h("div", { class: "row" }, check, apply, button("Cancel", { kind: "btn-ghost", onclick: close })));
      footer.hidden = false;
    },
  });
}
