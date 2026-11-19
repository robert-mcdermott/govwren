// Admin → Operations: how the installation is running, on one page.

import { get } from "../core/api.js";
import { h, icon } from "../core/dom.js";
import { dateTime, relative } from "../core/format.js";
import { alert, card, pageHeader, pill, stat } from "../components/ui.js";
import { show } from "./page.js";

const TONE = { ok: ["Fine", "ok"], warn: ["Look at this", "warn"], fail: ["Fix this", "danger"] };

function megabytes(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(bytes ? 1 : 0, Math.round(bytes / 1e6))} MB`;
}

export function adminOperations(main) {
  return show(main, {
    title: "Operations",
    load: async () => (await get("/api/v1/operations", null, { fresh: true })).data,
    view: (data) => {
      const failing = data.checks.filter((check) => check.status === "fail").length;
      const warning = data.checks.filter((check) => check.status === "warn").length;
      const late = data.jobs.filter((job) => job.enabled && job.last_status && job.last_status !== "ok");
      return h("div", { class: "stack-lg" },
        pageHeader({ eyebrow: "Admin", title: "Operations",
          lede: `GovWren ${data.version} on ${data.database}, at migration ${data.revision}, with ${data.workers} server ${data.workers === 1 ? "process" : "processes"}. These are the checks that govwren doctor --production makes.` }),
        failing ? alert("danger", icon("alert"), h("div", {}, h("strong", {}, `${failing} ${failing === 1 ? "thing needs" : "things need"} fixing. `), "They are marked below."))
          : warning ? alert("warn", icon("alert"), h("div", {}, `Working, with ${warning} ${warning === 1 ? "thing" : "things"} to look at.`))
            : alert("ok", icon("check"), h("div", {}, "Everything checks out.")),
        h("div", { class: "grid-3" }, stat(String(data.size.use_cases), "Use cases"), stat(String(data.size.events), "Events in the history"),
          stat(megabytes(data.size.file_bytes), `In ${data.size.files} evidence ${data.size.files === 1 ? "file" : "files"}`)),
        card({ title: "Checks", flush: true }, h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", {}, h("tr", {}, ["Check", "Standing", "What was found"].map((heading) => h("th", { scope: "col" }, heading)))),
          h("tbody", {}, data.checks.map((check) => h("tr", {},
            h("th", { scope: "row" }, check.name), h("td", {}, pill(...TONE[check.status])), h("td", {}, check.detail))))))),
        h("div", { class: "grid-3" },
          card({ title: "Backup" }, data.backup ? h("div", { class: "stack-sm" }, h("p", {}, `Last made ${relative(data.backup.at)}, ${dateTime(data.backup.at)}.`), h("p", { class: "subtle mono" }, data.backup.file))
            : h("p", { class: "muted" }, "govwren backup has not been run here.")),
          card({ title: "Email" }, data.mail.enabled ? h("div", { class: "stack-sm" },
            h("p", {}, `${data.mail.sent} sent, ${data.mail.waiting} waiting, ${data.mail.failed} given up on.`),
            data.mail.last_error ? h("p", { class: "due-late" }, data.mail.last_error) : null, h("p", {}, h("a", { href: "/admin/email" }, "Email settings")))
            : h("p", { class: "muted" }, "Not set up.")),
          card({ title: "Webhooks" }, data.webhooks.set_up ? h("div", { class: "stack-sm" },
            h("p", {}, `${data.webhooks.set_up} set up, ${data.webhooks.waiting} ${data.webhooks.waiting === 1 ? "delivery" : "deliveries"} waiting, ${data.webhooks.given_up} given up on.`),
            data.webhooks.paused ? h("p", { class: "due-late" }, `${data.webhooks.paused} paused after repeated failures.`) : null, h("p", {}, h("a", { href: "/admin/webhooks" }, "Webhooks")))
            : h("p", { class: "muted" }, "None is set up."))),
        card({ title: "Scheduled work", flush: true, actions: h("a", { class: "btn btn-sm", href: "/admin/jobs" }, "Open scheduled work") },
          h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", {}, h("tr", {}, ["Job", "Last ran", "How it went"].map((heading) => h("th", { scope: "col" }, heading)))),
            h("tbody", {}, data.jobs.map((job) => h("tr", {},
              h("th", { scope: "row" }, job.label),
              h("td", { class: "nowrap" }, job.last_finished_at ? relative(job.last_finished_at) : h("span", { class: "subtle" }, "Not yet")),
              h("td", {}, !job.enabled ? pill("Paused") : job.last_status === "ok" ? pill("Fine", "ok") : job.last_status ? pill("Failed", "danger") : pill("Waiting"),
                job.last_summary ? h("span", { class: "subtle" }, ` ${job.last_summary}`) : null))))))),
        late.length ? null : h("p", { class: "subtle" }, "Scheduled work runs while the server is up. Each job is claimed in the database before it runs, so several server processes never run one twice."));
    },
  });
}
