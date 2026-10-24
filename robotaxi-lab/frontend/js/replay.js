// Replay view: animate each algorithm's cars over the day, minute by minute.
import { on, resultSeries, state } from "./state.js";
import { el, fmt, store, svg } from "./util.js";
import { ratioText } from "./compare.js";

const player = {
  T: 0,              // current time in minutes (fractional while playing)
  total: 0,
  playing: false,
  speed: 2,          // minutes per second
  layout: "split",
  showRoutes: true,
  hidden: new Set(), // series keys hidden from the replay
  last: null,        // timestamp of previous animation frame
  lastWhole: -1,     // last whole minute the status table was drawn for
};

let views = [];      // one per map card
let series = [];
let timeline = null;

const DARK_TEXT_SLOTS = new Set([3, 4, 5]);
const colorVar = (slot) => (slot === "opt" ? "var(--opt)" : `var(--s${slot})`);
const textVar = (slot) => (slot === "opt" ? "var(--surface)" : DARK_TEXT_SLOTS.has(slot) ? "#18212c" : "#ffffff");

export function initReplay() {
  const saved = store.get("player", {});
  player.speed = saved.speed || 2;
  player.layout = saved.layout || "split";
  player.showRoutes = saved.showRoutes !== false;
  document.getElementById("pl-speed").value = String(player.speed);
  document.getElementById("pl-routes").checked = player.showRoutes;
  setLayoutButtons();

  document.getElementById("pl-play").addEventListener("click", togglePlay);
  document.getElementById("pl-back").addEventListener("click", () => step(-1));
  document.getElementById("pl-fwd").addEventListener("click", () => step(1));
  document.getElementById("pl-start").addEventListener("click", () => seek(0));
  document.getElementById("pl-end").addEventListener("click", () => seek(player.total));
  document.getElementById("pl-scrub").addEventListener("input", (e) => { pause(); seek(Number(e.target.value)); });
  document.getElementById("pl-speed").addEventListener("change", (e) => { player.speed = Number(e.target.value); persist(); });
  document.getElementById("pl-routes").addEventListener("change", (e) => { player.showRoutes = e.target.checked; persist(); draw(); });
  for (const b of document.querySelectorAll("#replay [data-layout]")) {
    b.addEventListener("click", () => { player.layout = b.dataset.layout; setLayoutButtons(); persist(); build(); });
  }

  document.addEventListener("keydown", (e) => {
    if (document.getElementById("view-replay").hidden || !state.result) return;
    if (e.target.closest("input, textarea, select, [contenteditable]") || e.ctrlKey || e.metaKey || e.altKey) return;
    const keys = {
      " ": togglePlay, ArrowLeft: () => step(-1), ArrowRight: () => step(1),
      Home: () => seek(0), End: () => seek(player.total),
    };
    if (keys[e.key] && !(e.key === " " && e.target.closest("button"))) { e.preventDefault(); keys[e.key](); }
  });

  on("result-changed", () => { pause(); player.T = 0; player.hidden.clear(); build(); });
  on("theme-changed", draw);
}

function persist() {
  store.set("player", { speed: player.speed, layout: player.layout, showRoutes: player.showRoutes });
}

function setLayoutButtons() {
  for (const b of document.querySelectorAll("#replay [data-layout]")) {
    b.setAttribute("aria-checked", String(b.dataset.layout === player.layout));
  }
}

// ------------------------------------------------------------------ playback

function togglePlay() {
  if (player.playing) return pause();
  if (player.T >= player.total) player.T = 0;
  player.playing = true;
  player.last = null;
  document.getElementById("pl-play").classList.add("playing");
  document.getElementById("pl-play").setAttribute("aria-label", "Pause");
  requestAnimationFrame(frame);
}

function pause() {
  player.playing = false;
  const b = document.getElementById("pl-play");
  b.classList.remove("playing");
  b.setAttribute("aria-label", "Play");
}

function frame(ts) {
  if (!player.playing) return;
  if (player.last !== null) {
    const dt = Math.min(0.1, (ts - player.last) / 1000);
    player.T = Math.min(player.total, player.T + dt * player.speed);
  }
  player.last = ts;
  draw();
  if (player.T >= player.total) return pause();
  requestAnimationFrame(frame);
}

function step(d) {
  pause();
  const whole = d > 0 ? Math.floor(player.T + 1e-9) + 1 : Math.ceil(player.T - 1e-9) - 1;
  seek(whole);
}

function seek(t) {
  player.T = Math.max(0, Math.min(player.total, t));
  draw();
}

// ------------------------------------------------------------------ geometry

// Position k blocks along the Manhattan path from a to b, moving in x first.
function along(a, b, k) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  if (k <= Math.abs(dx)) return [a[0] + Math.sign(dx) * k, a[1]];
  return [b[0], a[1] + Math.sign(dy) * Math.min(Math.abs(dy), k - Math.abs(dx))];
}

function remainingPath(a, b, k) {
  const pos = along(a, b, k);
  const corner = [b[0], a[1]];
  return k < Math.abs(b[0] - a[0]) ? [pos, corner, b] : [pos, b];
}

function carState(legs, depot, T) {
  let at = depot;
  for (const leg of legs) {
    if (T < leg.start) return { pos: at, kind: "parked", leg: null, next: leg };
    if (T < leg.end) {
      const k = T - leg.start;
      return { pos: leg.kind === "idle" ? leg.from : along(leg.from, leg.to, k), kind: leg.kind, leg, k };
    }
    at = leg.to;
  }
  return { pos: at, kind: "parked", leg: null };
}

function tripStatus(sched, trip, i, T) {
  const o = sched.trips[String(i)];
  if (T < trip.t) return { kind: "upcoming", o };
  if (T < o.pickup) return { kind: "waiting", o, waited: T - trip.t };
  if (T < o.dropoff) return { kind: "riding", o };
  return { kind: "done", o };
}

// ------------------------------------------------------------------ building

function build() {
  const r = state.result;
  document.getElementById("replay-empty").hidden = !!r;
  document.getElementById("replay").hidden = !r;
  if (!r) { views = []; return; }
  const inst = r.instance;
  series = resultSeries();
  player.total = Math.max(1, ...series.map((s) => s.sched.metrics.last_dropoff), ...inst.trips.map((t) => t.t));
  player.T = Math.min(player.T, player.total);
  const scrub = document.getElementById("pl-scrub");
  scrub.max = String(player.total);
  document.getElementById("pl-total").textContent = `of ${player.total} min`;

  buildSeriesFilter();
  buildTimeline(inst);
  const visible = series.filter((s) => !player.hidden.has(s.key));
  const maps = document.getElementById("maps");
  maps.classList.toggle("overlay", player.layout === "overlay");
  views = [];
  if (player.layout === "overlay") {
    maps.style.setProperty("--cols", "1");
    views.push(buildMap(inst, visible, true));
  } else {
    const cols = visible.length <= 1 ? 1 : visible.length <= 4 ? 2 : 3;
    maps.style.setProperty("--cols", String(cols));
    for (const s of visible) views.push(buildMap(inst, [s], false));
  }
  maps.replaceChildren(...views.map((v) => v.card));
  if (!visible.length) maps.replaceChildren(el("p", { class: "empty" }, "Every algorithm is hidden. Turn one back on above the maps."));
  player.lastWhole = -1;
  draw();
}

function buildSeriesFilter() {
  let row = document.getElementById("pl-series");
  if (!row) {
    row = el("div", { class: "series-filter", id: "pl-series", role: "group", "aria-label": "Algorithms shown" });
    document.querySelector("#replay .replay-body").before(row);
  }
  row.replaceChildren(
    el("span", { class: "series-filter-label" }, "Show"),
    ...series.map((s) => el("button", {
      type: "button", class: "series-toggle", "aria-pressed": String(!player.hidden.has(s.key)),
      onclick: () => { player.hidden.has(s.key) ? player.hidden.delete(s.key) : player.hidden.add(s.key); build(); },
    }, el("span", { class: "swatch", style: { background: colorVar(s.slot) } }), s.name)),
  );
}

function buildTimeline(inst) {
  const total = player.total;
  const ppm = Math.max(14, Math.min(22, 640 / total));
  const top = 12, H = top * 2 + total * ppm, W = 138;
  const y = (t) => top + t * ppm;
  const every = total > 900 ? 60 : total > 400 ? 30 : total > 120 ? 10 : 5;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": "Request times" });
  root.append(svg("line", { class: "tl-axis", x1: 36, x2: 36, y1: y(0), y2: y(total) }));
  for (let t = 0; t <= total; t += every) {
    root.append(svg("line", { class: "tl-tick", x1: 32, x2: 36, y1: y(t), y2: y(t) }));
    root.append(svg("text", { class: "tl-label", x: 29, y: y(t) + 3.5, "text-anchor": "end", text: String(t) }));
  }
  const byT = new Map();
  inst.trips.forEach((tr, i) => { if (!byT.has(tr.t)) byT.set(tr.t, []); byT.get(tr.t).push(i); });
  const reqs = [];
  for (const [t, ids] of [...byT.entries()].sort((a, b) => a[0] - b[0])) {
    const label = ids.length > 4 ? `${ids.slice(0, 3).join(", ")} +${ids.length - 3}` : ids.join(", ");
    const g = svg("g", { class: "tl-req", tabindex: "0", role: "button", "aria-label": `Trips ${ids.join(", ")} requested at minute ${t}. Jump there.` },
      svg("title", { text: `Minute ${t}: trip${ids.length > 1 ? "s" : ""} ${ids.join(", ")}` }),
      svg("circle", { cx: 36, cy: y(t), r: 4 }),
      svg("text", { x: 46, y: y(t) + 4, text: label }));
    const jump = () => { pause(); seek(t); };
    g.addEventListener("click", jump);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); jump(); } });
    root.append(g);
    reqs.push({ t, g });
  }
  const head = svg("g", {},
    svg("line", { class: "tl-head", x1: 22, x2: W - 2, y1: 0, y2: 0 }),
    svg("text", { class: "tl-head-label", x: W - 2, y: -4, "text-anchor": "end", text: "" }));
  root.append(head);
  const box = document.getElementById("timeline");
  box.replaceChildren(el("p", { class: "tl-title" }, "Requests"), el("p", { class: "tl-sub" }, "Click one to jump to it"), root);
  timeline = { reqs, head, y, box, ppm };
}

function buildMap(inst, list, overlay) {
  const W = inst.width, H = inst.height;
  const pad = 0.8;
  const k = Math.max(1, Math.max(W, H) / 12);              // marker scale for large grids
  const X = (x) => x, Y = (yv) => H - yv;
  const root = svg("svg", {
    class: "map-svg", viewBox: `${-pad} ${-pad} ${W + 2 * pad} ${H + 2 * pad}`,
    role: "img", "aria-label": overlay ? "Map with every algorithm overlaid" : `Map for ${list[0].name}`,
  });
  root.append(svg("rect", { class: "m-block", x: -pad, y: -pad, width: W + 2 * pad, height: H + 2 * pad }));
  const sw = 0.34 * Math.min(1.6, k);
  for (let x = 0; x <= W; x++) root.append(svg("rect", { class: "m-street", x: x - sw / 2, y: -pad, width: sw, height: H + 2 * pad }));
  for (let yv = 0; yv <= H; yv++) root.append(svg("rect", { class: "m-street", x: -pad, y: Y(yv) - sw / 2, width: W + 2 * pad, height: sw }));
  const labelEvery = W > 24 ? 5 : W > 12 ? 2 : 1;
  for (let x = 0; x <= W; x += labelEvery) root.append(svg("text", { class: "m-coord", x, y: H + pad * 0.72, "font-size": 0.3 * k, text: String(x) }));
  for (let yv = 0; yv <= H; yv += labelEvery) root.append(svg("text", { class: "m-coord", x: -pad * 0.62, y: Y(yv), "font-size": 0.3 * k, "dominant-baseline": "central", text: String(yv) }));

  const [dx, dy] = inst.depot;
  root.append(svg("g", { transform: `translate(${X(dx)} ${Y(dy)}) scale(${k})` },
    svg("title", { text: `Depot (${dx}, ${dy})` }),
    svg("rect", { class: "m-depot", x: -0.32, y: -0.32, width: 0.64, height: 0.64, rx: 0.08 }),
    svg("text", { class: "m-depot-text", x: 0, y: 0.02, text: "D" })));

  const routeLayer = svg("g", {});
  const destLayer = svg("g", {});
  const pinLayer = svg("g", {});
  const carLayer = svg("g", {});
  root.append(routeLayer, destLayer, pinLayer, carLayer);

  const ringR = 0.34, circ = 2 * Math.PI * ringR;
  const pins = inst.trips.map((tr, i) => {
    const ring = svg("circle", { class: "m-pin-ring", r: ringR, transform: "rotate(-90)", "stroke-dasharray": `0 ${circ}` });
    const sats = list.map((s, j) => {
      const a = (-90 + (360 / Math.max(list.length, 1)) * j) * (Math.PI / 180);
      return svg("circle", { class: "m-sat", r: 0.1, cx: Math.cos(a) * 0.52, cy: Math.sin(a) * 0.52, style: `fill:${colorVar(s.slot)}` });
    });
    const title = svg("title", { text: "" });
    const g = svg("g", { transform: `translate(${X(tr.s[0])} ${Y(tr.s[1])}) scale(${k})`, display: "none" },
      title,
      svg("circle", { class: "m-pin-ring-bg", r: ringR }), ring,
      svg("circle", { class: "m-pin", r: 0.17 }),
      svg("text", { class: "m-pin-text", x: 0, y: -0.5, text: String(i) }),
      ...(overlay ? sats : []));
    pinLayer.append(g);
    return { g, ring, sats, title, circ };
  });

  const cars = [];
  const n = list.length;
  list.forEach((s, j) => {
    const off = overlay && n > 1 ? [Math.cos((2 * Math.PI * j) / n) * 0.2, Math.sin((2 * Math.PI * j) / n) * 0.2] : [0, 0];
    s.sched.legs.forEach((legs, c) => {
      const route = svg("polyline", { class: "m-route", style: `stroke:${colorVar(s.slot)};stroke-width:${0.07 * k}`, display: "none" });
      const dest = svg("rect", { class: "m-dest", x: -0.2 * k, y: -0.2 * k, width: 0.4 * k, height: 0.4 * k, rx: 0.06 * k,
        style: `stroke:${colorVar(s.slot)};stroke-width:${0.07 * k}`, display: "none" });
      const title = svg("title", { text: "" });
      const g = svg("g", {},
        title,
        svg("rect", { class: "m-car", x: -0.27, y: -0.27, width: 0.54, height: 0.54, rx: 0.12, style: `fill:${colorVar(s.slot)}` }),
        svg("text", { class: "m-car-text", x: 0, y: 0.02, style: `fill:${textVar(s.slot)}`, text: String(c + 1) }));
      routeLayer.append(route);
      destLayer.append(dest);
      carLayer.append(g);
      cars.push({ s, c, legs, g, route, dest, title, off });
    });
  });

  const stats = {
    waiting: el("b", {}, "0"), worst: el("b", {}, "0"),
  };
  const head = el("div", { class: "map-head" });
  if (overlay) {
    head.append(el("h3", {}, "All algorithms"));
  } else {
    const s = list[0];
    head.append(...[
      el("span", { class: "swatch", style: { background: colorVar(s.slot) } }),
      el("h3", {}, s.name),
      el("span", { class: "map-stat" }, "final longest wait", el("b", {}, `${fmt(s.sched.metrics.max_wait)}`), "min"),
      s.isOpt ? null : el("span", { class: "map-stat" }, "ratio", el("b", {}, ratioText(s.ratio, state.result.optimal, s.sched.metrics.max_wait))),
    ].filter(Boolean));
  }
  const live = el("div", { class: "map-live" },
    el("span", { class: "map-stat" }, "waiting now", stats.waiting),
    el("span", { class: "map-stat" }, "longest wait so far", stats.worst, "min"));
  const legend = buildLegend(overlay ? list : null);
  const card = el("article", { class: "map-card" }, head, live, root, legend);
  return { card, list, overlay, pins, cars, stats, k, X, Y, inst };
}

function buildLegend(list) {
  const icon = (...kids) => svg("svg", { viewBox: "-0.5 -0.5 1 1", width: 16, height: 16, "aria-hidden": "true" }, ...kids);
  const items = [];
  if (list) {
    for (const s of list) items.push(el("span", {}, el("span", { class: "swatch", style: { background: colorVar(s.slot) } }), s.name));
  }
  items.push(
    el("span", {}, icon(svg("rect", { x: -0.38, y: -0.38, width: 0.76, height: 0.76, rx: 0.16, style: "fill:var(--ink-2)" })), "Car, numbered"),
    el("span", {}, icon(svg("circle", { class: "m-pin-ring-bg", r: 0.36, "stroke-width": 0.12 }),
      svg("circle", { class: "m-pin-ring", r: 0.36, "stroke-width": 0.12, transform: "rotate(-90)", "stroke-dasharray": "1.4 3" }),
      svg("circle", { class: "m-pin", r: 0.17 })), "Waiting passenger, ring fills as the wait grows"),
    el("span", {}, icon(svg("rect", { x: -0.3, y: -0.3, width: 0.6, height: 0.6, rx: 0.08, style: "fill:none;stroke:var(--ink-2);stroke-width:0.12" })), "Drop-off for a passenger on board"),
  );
  if (list && list.length > 1) items.push(el("span", {}, icon(svg("circle", { r: 0.2, style: "fill:var(--ink-2)" })), "Dots show which algorithms still have that passenger waiting"));
  return el("div", { class: "legend" }, items);
}

// ------------------------------------------------------------------ drawing

function draw() {
  if (!state.result || !views.length && !timeline) return;
  const T = player.T;
  const whole = Math.floor(T + 1e-9);
  document.getElementById("pl-time").textContent = String(whole);
  document.getElementById("pl-scrub").value = String(whole);
  const inst = state.result.instance;
  const ringFull = Math.max(10, ...series.map((s) => s.sched.metrics.max_wait));

  for (const v of views) {
    let waitingNow = 0, worst = 0;
    inst.trips.forEach((tr, i) => {
      const statuses = v.list.map((s) => tripStatus(s.sched, tr, i, T));
      const waiting = statuses.map((st) => st.kind === "waiting");
      const pin = v.pins[i];
      const any = waiting.some(Boolean);
      for (const st of statuses) {
        if (st.kind !== "upcoming") worst = Math.max(worst, Math.min(T, st.o.pickup) - tr.t);
      }
      if (!any) { pin.g.setAttribute("display", "none"); return; }
      waitingNow += 1;
      const waited = T - tr.t;
      pin.g.setAttribute("display", "inline");
      pin.ring.setAttribute("stroke-dasharray", `${Math.min(1, waited / ringFull) * pin.circ} ${pin.circ}`);
      pin.title.textContent = `Trip ${i}: requested at minute ${tr.t}, waiting ${fmt(waited, 1)} min, going to (${tr.w.join(", ")})`;
      pin.sats.forEach((sat, j) => sat.setAttribute("display", waiting[j] ? "inline" : "none"));
    });
    v.stats.waiting.textContent = String(waitingNow);
    v.stats.worst.textContent = fmt(Math.floor(worst + 1e-9));

    for (const car of v.cars) {
      const st = carState(car.legs, inst.depot, T);
      const [px, py] = st.pos;
      const x = v.X(px) + car.off[0], y = v.Y(py) + car.off[1];
      car.g.setAttribute("transform", `translate(${x} ${y}) scale(${v.k})`);
      const what = st.kind === "ride" ? `carrying trip ${st.leg.trip}` : st.kind === "empty" ? `driving empty to trip ${st.leg.trip}`
        : st.kind === "idle" ? `waiting at the pickup for trip ${st.leg.trip}` : "parked";
      car.title.textContent = `${car.s.name}, car ${car.c + 1}: ${what}`;
      if (st.kind === "ride") {
        const tr = inst.trips[st.leg.trip];
        car.dest.setAttribute("display", "inline");
        car.dest.setAttribute("transform", `translate(${v.X(tr.w[0]) + car.off[0]} ${v.Y(tr.w[1]) + car.off[1]})`);
      } else car.dest.setAttribute("display", "none");
      if (player.showRoutes && st.leg && st.kind !== "idle") {
        const pts = remainingPath(st.leg.from, st.leg.to, st.k).map(([a, b]) => `${v.X(a) + car.off[0]},${v.Y(b) + car.off[1]}`).join(" ");
        car.route.setAttribute("points", pts);
        car.route.setAttribute("display", "inline");
        car.route.classList.toggle("is-empty", st.kind === "empty");
      } else car.route.setAttribute("display", "none");
    }
  }

  if (timeline) {
    const yy = timeline.y(T);
    timeline.head.setAttribute("transform", `translate(0 ${yy})`);
    timeline.head.querySelector("text").textContent = `min ${whole}`;
    for (const r of timeline.reqs) r.g.classList.toggle("past", r.t <= T);
    if (player.playing) {
      const box = timeline.box;
      const top = yy + 40;
      if (top > box.scrollTop + box.clientHeight - 40 || top < box.scrollTop) box.scrollTop = Math.max(0, top - box.clientHeight / 2);
    }
  }
  if (whole !== player.lastWhole) { player.lastWhole = whole; drawStatusTable(whole); }
}

function drawStatusTable(T) {
  const inst = state.result.instance;
  const vis = series.filter((s) => !player.hidden.has(s.key));
  const order = inst.trips.map((t, i) => ({ t, i })).sort((a, b) => a.t.t - b.t.t || a.i - b.i);
  const chip = (st) => {
    if (st.kind === "waiting") return el("span", { class: "chip waiting" }, `Waiting, ${fmt(Math.floor(st.waited + 1e-9))} min so far`);
    if (st.kind === "riding") return el("span", { class: "chip riding" }, `In car ${st.o.car + 1}`);
    return el("span", { class: "chip done" }, `Done, waited ${fmt(st.o.wait)} min`);
  };
  const rows = order.map(({ t, i }) => el("tr", {},
    el("td", {}, `Trip ${i}`), el("td", {}, `minute ${t.t}`),
    el("td", {}, `(${t.s.join(", ")}) to (${t.w.join(", ")})`),
    ...vis.map((s) => {
      const st = tripStatus(s.sched, t, i, T);
      return el("td", {}, st.kind === "upcoming" ? el("span", { class: "chip upcoming" }, "Not requested yet") : chip(st));
    })));
  document.getElementById("trip-status-table").replaceChildren(el("div", { class: "table-wrap" },
    el("table", { class: "data status" },
      el("thead", {}, el("tr", {}, el("th", {}, "Trip"), el("th", {}, "Requested"), el("th", {}, "Route"),
        ...vis.map((s) => el("th", {}, el("span", { class: "name-cell" }, el("span", { class: "swatch", style: { background: colorVar(s.slot) } }), s.name))))),
      el("tbody", {}, rows))));
}
