// Admin → Email: how email is set up, how it is doing, and a test message.

import { get, post } from "../core/api.js";
import { button, h, icon } from "../core/dom.js";
import { toast } from "../components/toast.js";
import { alert, card, pageHeader, pill, stat } from "../components/ui.js";
import { show } from "./page.js";

const SECURITY = { starttls: "Encrypted, with STARTTLS", tls: "Encrypted, with TLS", none: "Not encrypted" };

export function adminEmail(main) {
  return show(main, {
    title: "Email",
    load: async () => (await get("/api/v1/mail", null, { fresh: true })).data,
    view: (data) => {
      if (!data.enabled) {
        return h("div", { class: "stack-lg" },
          pageHeader({ title: "Email", lede: "Send notices by email, as they happen or as a daily summary." }),
          card({ title: "Connection", actions: pill("Not set up") }, h("div", { class: "stack" },
            h("p", {}, "GovWren sends no email. What needs each person is listed on their Home page and under the bell."),
            h("ol", { class: "steps-list" },
              h("li", {}, "In ", h("code", {}, "govwren.toml"), ", give the ", h("code", {}, "[mail]"), " section your mail server's host and the address email should come from."),
              h("li", {}, "If the server needs a password, put it in the environment variable that section names."),
              h("li", {}, "Set ", h("code", {}, "base_url"), " under ", h("code", {}, "[server]"), " so that messages can link back here, then restart GovWren.")))));
      }
      const result = h("div", { "aria-live": "polite" });
      const test = button("Send me a test message", { kind: "btn-primary", onclick: async () => {
        test.disabled = true;
        result.replaceChildren();
        try {
          const done = (await post("/api/v1/mail/test")).data;
          toast(`Sent to ${done.sent_to}.`);
          result.replaceChildren(alert("ok", icon("check"), h("div", {}, `The mail server accepted a message for ${done.sent_to}. Check that it arrives.`)));
        } catch (error) {
          result.replaceChildren(alert("danger", icon("alert"), h("div", {}, h("strong", {}, "It could not be sent. "), error.detail ?? "")));
        } finally {
          test.disabled = false;
        }
      } });
      const rows = [["Mail server", `${data.host}, port ${data.port}`], ["Connection", SECURITY[data.security] ?? data.security],
        ["From", data.from_name ? `${data.from_name} <${data.from_address}>` : data.from_address],
        ["Daily summaries", `Put together after ${String(data.digest_hour).padStart(2, "0")}:00 UTC`]];
      return h("div", { class: "stack-lg" },
        pageHeader({ title: "Email", lede: "Notices go out as they happen, or as a daily summary, as each person chooses under Your account." }),
        data.links ? null : alert("warn", icon("alert"), h("div", {}, h("strong", {}, "Messages cannot link back to GovWren. "),
          "Set base_url under [server] in govwren.toml to the address people use.")),
        h("div", { class: "grid-3" }, stat(String(data.waiting), "Waiting to be sent"), stat(String(data.sent), "Sent"), stat(String(data.failed), "Given up on")),
        data.last_error ? alert("warn", icon("alert"), h("div", {}, h("strong", {}, "The most recent problem: "), data.last_error)) : null,
        card({ title: "Connection", actions: pill("Set up", "ok"),
          footer: h("span", { class: "subtle" }, "These are set in govwren.toml on the server, not here.") },
        h("dl", { class: "facts" }, rows.map(([term, value]) => [h("dt", {}, term), h("dd", {}, value)]))),
        card({ title: "Try it" }, h("div", { class: "stack" },
          h("p", { class: "muted" }, "Sends one message to your own address, now, and says whether the mail server accepted it."),
          h("div", {}, test), result)));
    },
  });
}
