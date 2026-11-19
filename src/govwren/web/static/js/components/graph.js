// The graph around a record: what relies on it to the left, what it relies on to the right.
// Drawn as SVG by hand, with every node a link, and always shown beside the same thing as a
// list, so that nothing is available only as a picture.

import { h } from "../core/dom.js";
import { plural } from "../core/format.js";
import { hrefOf, recordChip, standingPill, TYPES } from "./record.js";
import { alert, card, emptyState } from "./ui.js";

const NS = "http://www.w3.org/2000/svg";
const BOX = { width: 208, height: 48, gapX: 76, gapY: 14, pad: 16, top: 34 };

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) if (value != null) node.setAttribute(key, value);
  for (const child of children.flat()) if (child != null) node.append(child);
  return node;
}

const clip = (text, length) => (text.length > length ? `${text.slice(0, length - 1).trimEnd()}…` : text);

function layout(data) {
  const column = (node) => (node.side === "downstream" ? -node.distance : node.side === "upstream" ? node.distance : 0);
  const columns = new Map();
  for (const node of data.nodes) {
    const key = column(node);
    if (!columns.has(key)) columns.set(key, []);
    columns.get(key).push(node);
  }
  const keys = [...columns.keys()].sort((a, b) => a - b);
  const place = new Map();
  // Nearest the centre first, so that each further column can sit beside what it hangs from.
  for (const key of [...keys].sort((a, b) => Math.abs(a) - Math.abs(b))) {
    const nodes = columns.get(key);
    nodes.sort((a, b) => (place.get(a.through)?.row ?? 0) - (place.get(b.through)?.row ?? 0) || a.name.localeCompare(b.name));
    nodes.forEach((node, row) => place.set(node.ref, { column: keys.indexOf(key), row, count: nodes.length }));
  }
  const tallest = Math.max(...[...columns.values()].map((nodes) => nodes.length));
  const height = BOX.top + tallest * (BOX.height + BOX.gapY) + BOX.pad;
  const width = BOX.pad * 2 + keys.length * BOX.width + (keys.length - 1) * BOX.gapX;
  const at = (ref) => {
    const spot = place.get(ref);
    const columnHeight = spot.count * (BOX.height + BOX.gapY) - BOX.gapY;
    return {
      x: BOX.pad + spot.column * (BOX.width + BOX.gapX),
      y: BOX.top + (height - BOX.top - BOX.pad - columnHeight) / 2 + spot.row * (BOX.height + BOX.gapY),
    };
  };
  return { keys, at, width, height };
}

function picture(data) {
  const { keys, at, width, height } = layout(data);
  const names = new Map(data.nodes.map((node) => [node.ref, node.name]));
  const edges = data.edges.map((edge) => {
    const from = at(edge.from);
    const to = at(edge.to);
    const forward = from.x <= to.x;
    const x1 = forward ? from.x + BOX.width : from.x;
    const x2 = forward ? to.x : to.x + BOX.width;
    const y1 = from.y + BOX.height / 2;
    const y2 = to.y + BOX.height / 2;
    const bend = from.x === to.x ? BOX.gapX * 0.8 : Math.abs(x2 - x1) / 2;
    const c1 = forward || from.x === to.x ? x1 + bend : x1 - bend;
    const c2 = forward && from.x !== to.x ? x2 - bend : x2 + bend;
    return svg("path", { class: "graph-edge", d: `M${x1},${y1} C${c1},${y1} ${c2},${y2} ${x2},${y2}`, "marker-end": "url(#graph-arrow)" },
      svg("title", {}, `${names.get(edge.from)} — ${edge.label.toLowerCase()} → ${names.get(edge.to)}`));
  });
  const nodes = data.nodes.map((node) => {
    const { x, y } = at(node.ref);
    const meta = TYPES[node.type];
    return svg("a", { href: hrefOf(node.ref), class: `graph-node${node.side === "centre" ? " is-centre" : ""}`, "data-record": node.type,
      "aria-label": `${meta.label} ${node.name}, ${node.ref}${node.via ? `, ${node.via.toLowerCase()}` : ""}` },
    svg("rect", { x, y, width: BOX.width, height: BOX.height, rx: 8 }),
    svg("rect", { class: "graph-kind", x, y, width: 5, height: BOX.height, rx: 2 }),
    svg("text", { class: "graph-name", x: x + 16, y: y + 20 }, clip(node.name, 27)),
    svg("text", { class: "graph-ref", x: x + 16, y: y + 37 }, `${meta.label} · ${node.ref}`),
    svg("title", {}, node.name));
  });
  const centreAt = keys.indexOf(0);
  const heading = (text, from, to) => (to >= from ? svg("text", { class: "graph-heading",
    x: BOX.pad + ((from + to + 1) / 2) * (BOX.width + BOX.gapX) - BOX.gapX / 2, y: 18, "text-anchor": "middle" }, text) : null);
  return h("div", { class: "graph-wrap", tabindex: "0", role: "group", "aria-label": "The graph. The same records are listed below." },
    svg("svg", { class: "graph", width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Records connected to this one" },
      svg("defs", {}, svg("marker", { id: "graph-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" },
        svg("path", { class: "graph-arrow", d: "M0,0 L10,5 L0,10 z" }))),
      heading("Relies on this", 0, centreAt - 1), heading("This relies on", centreAt + 1, keys.length - 1),
      edges, nodes));
}

function listing(title, nodes, byRef, empty) {
  return card({ title, flush: nodes.length > 0 },
    nodes.length ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Record"), h("th", { scope: "col" }, "How"), h("th", { scope: "col" }, "Steps away"))),
      h("tbody", {}, nodes.map((node) => h("tr", {},
        h("td", {}, recordChip(node)),
        h("td", {}, node.via, node.through ? h("span", { class: "muted" }, ` · through ${byRef.get(node.through)?.name ?? node.through}`) : null,
          node.catalog_status && node.type !== "use_case" ? h("div", { class: "cell-sub" }, standingPill(node.catalog_status)) : null),
        h("td", { class: "numeric" }, String(node.distance)))))))
      : h("p", { class: "muted" }, empty));
}

/** The whole Connections tab: a depth switch, the picture, and the two lists. */
export function connections(data, { depth, onDepth }) {
  const byRef = new Map(data.nodes.map((node) => [node.ref, node]));
  const up = data.nodes.filter((node) => node.side === "upstream");
  const down = data.nodes.filter((node) => node.side === "downstream");
  const steps = h("select", { class: "select graph-depth", "aria-label": "How far to follow the links", onchange: (event) => onDepth(Number(event.target.value)) },
    [1, 2, 3, 4, 6].map((n) => h("option", { value: n, selected: n === depth }, n === 1 ? "Direct links only" : `Up to ${n} steps away`)));
  if (data.nodes.length === 1) {
    return card({}, emptyState({ iconName: "link", title: "Not connected to anything yet",
      text: data.hidden ? `It is linked to ${plural(data.hidden, "record")} that you do not have access to.`
        : "Link it to the systems, models, and datasets it relies on from the Overview tab." }));
  }
  return h("div", { class: "stack-lg" },
    h("div", { class: "row wrap" },
      h("p", { class: "muted grow" }, `${plural(down.length, "record relies", "records rely")} on this, and it relies on ${plural(up.length, "record")}.`),
      steps),
    data.truncated ? alert("warn", h("div", {}, "There is more than can be drawn. Follow fewer steps, or use the lists.")) : null,
    card({ flush: true }, picture(data)),
    data.hidden ? h("p", { class: "subtle" }, `${plural(data.hidden, "connected record is", "connected records are")} not shown because you do not have access to ${data.hidden === 1 ? "it" : "them"}.`) : null,
    h("div", { class: "grid-2" },
      listing("Relies on this", down, byRef, "Nothing relies on it."),
      listing("This relies on", up, byRef, "It relies on nothing that is recorded.")));
}
