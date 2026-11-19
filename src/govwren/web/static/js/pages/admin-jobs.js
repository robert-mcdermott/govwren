// Admin → Scheduled work: what GovWren does by itself, when each job last ran, and what it did.

import { get, post, put } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { dateTime, relative } from "../core/format.js";
import { toast } from "../components/toast.js";
import { alert, card, pageHeader, pill } from "../components/ui.js";
import { show } from "./page.js";

function every(seconds) {
  if (seconds < 3600) return `Every ${seconds / 60 === 1 ? "minute" : `${seconds / 60} minutes`}`;
  if (seconds < 86400) return `Every ${seconds / 3600 === 1 ? "hour" : `${seconds / 3600} hours`}`;
  return `Every ${seconds / 86400 === 1 ? "day" : `${seconds / 86400} days`}`;
}

function state(job) {
  if (!job.enabled) return pill("Paused", "warn");
  if (job.running) return pill("Running", "accent");
  if (job.last_status === "failed") return pill("Failed", "danger");
  return job.last_status ? pill("Working", "ok") : pill("Not run yet");
}

export function adminJobs(main) {
  return show(main, {
    title: "Scheduled work",
    load: async () => (await get("/api/v1/jobs", null, { fresh: true })).data,
    view: (jobs, reload) => {
      const failed = jobs.filter((job) => job.enabled && job.last_status === "failed");
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Scheduled work", lede: "What GovWren does by itself, so that nobody has to remember to." }),
        failed.length ? alert("danger", icon("alert"), h("div", {}, h("strong", {}, `${failed.map((job) => job.label).join(", ")} failed last time. `),
          "It will be tried again when it is next due. The reason is below, and in the server's log.")) : null,
        jobs.map((job) => {
          const run = button("Run now", { kind: "btn-sm", onclick: async () => {
            run.disabled = true;
            try {
              const done = (await post(`/api/v1/jobs/${job.key}/run`)).data;
              toast(`${job.label}: ${done.summary}`);
            } catch (error) {
              toast(error.detail ?? "It could not be run.");
            }
            reload();
          } });
          const pause = button(job.enabled ? "Pause" : "Resume", { kind: "btn-sm btn-ghost", onclick: async () => {
            await put(`/api/v1/jobs/${job.key}`, { enabled: !job.enabled });
            toast(job.enabled ? `${job.label} is paused.` : `${job.label} will run again.`);
            reload();
          } });
          const facts = [["How often", every(job.every_seconds)],
            ["Last ran", job.last_finished_at ? `${relative(job.last_finished_at)}: ${job.last_summary ?? ""}` : "Not yet"],
            ["Next due", job.enabled && job.next_run_at ? dateTime(job.next_run_at) : "Paused"]];
          return card({ title: h("span", { class: "row-sm wrap" }, job.label, state(job)), actions: h("div", { class: "row-sm" }, pause, run) },
            h("div", { class: "stack" },
              h("p", { class: "muted" }, `${job.describes}.`),
              h("dl", { class: "facts" }, facts.map(([term, value]) => [h("dt", {}, term), h("dd", {}, value)])),
              job.runs.length ? h("details", {}, h("summary", {}, `Recent runs that did something (${job.runs.length})`),
                h("table", { class: "table" },
                  h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "When"), h("th", { scope: "col" }, "Result"), h("th", { scope: "col" }, "What it did"))),
                  h("tbody", {}, job.runs.map((item) => h("tr", {},
                    h("td", {}, dateTime(item.started_at)),
                    h("td", {}, item.status === "ok" ? pill("Done", "ok") : pill("Failed", "danger")),
                    h("td", {}, item.summary)))))) : null));
        }));
    },
  });
}
