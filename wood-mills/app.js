/* US wood-products mills animation — local app.
 * Loads libraries from ./vendor if present (run fetch_assets.py once), otherwise from jsDelivr.
 * Base map: us-atlas states-10m.json (unprojected lon/lat, Census 1:10m), drawn with d3.geoAlbersUsa.
 */
const LIBS = [
  { test: () => window.d3, urls: ["vendor/d3.min.js", "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"] },
  { test: () => window.topojson, urls: ["vendor/topojson-client.min.js", "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js"] },
];
const STATES_URLS = ["vendor/states-10m.json", "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json"];
const DATA_URL = "data/mills.csv";

const W = 960, H = 600;
let d3, svg, gLand, gMills, gFx, tip, slider, zoomLayer, zoom;
let ztransform = null, pinnedMill = null;
let mills = [], projection, year = 1860, fYear = 1860, playing = false, last = 0, prevYear = null;
let filterMode = "all", typeFilter = "all", Y0 = 1860, Y1 = 2026;
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

function loadScript(urls) {
  return new Promise((res) => {
    const next = (i) => {
      if (i >= urls.length) return res(false);
      const s = document.createElement("script");
      s.src = urls[i];
      s.onload = () => res(true);
      s.onerror = () => { s.remove(); next(i + 1); };
      document.head.appendChild(s);
    };
    next(0);
  });
}

async function fetchFirst(urls, as = "json") {
  for (const u of urls) {
    try {
      const r = await fetch(u);
      if (r.ok) return as === "json" ? await r.json() : await r.text();
    } catch (_) { /* try next */ }
  }
  return null;
}

function parseMills(text, custom) {
  const rows = d3.csvParse(text);
  const need = ["name", "lat", "lon", "open"];
  const miss = need.filter((c) => !rows.columns.includes(c));
  if (miss.length) throw new Error(`Missing column(s): ${miss.join(", ")}.`);
  const blank = (v) => v == null || String(v).trim() === "";
  const parsed = rows.map((r, i) => ({
    id: (custom ? "u" : "m") + i, name: r.name, company: r.company || "", city: r.city || "", state: r.state || "",
    lat: +r.lat, lon: +r.lon, open: +r.open, close: blank(r.close) ? null : +r.close,
    checked: String(r.checked).trim() === "1", note: r.note || "", custom,
    type: (r.type || "pulp").trim() || "pulp",
    capacity: blank(r.capacity) ? null : +r.capacity, capacity_unit: r.capacity_unit || "",
  })).filter((m) => isFinite(m.lat) && isFinite(m.lon) && isFinite(m.open));
  return { parsed, dropped: rows.length - parsed.length };
}

const TYPE_LABEL = { pulp: "Pulp mill", sawmill: "Sawmill", osb: "OSB mill", plywood: "Plywood mill",
  mdf: "MDF/particleboard", paper: "Paper mill", "pulp/chip": "Pulp/chip mill", mill: "Mill" };
// SVG <path> "d" generators for a marker of side length ~2*s, centered at 0,0. Circle handled separately.
const TYPE_PATH = {
  sawmill: (s) => `M${-s},${-s} L${s},${-s} L${s},${s} L${-s},${s} Z`, // square
  plywood: (s) => `M0,${-1.15 * s} L${s},${0.7 * s} L${-s},${0.7 * s} Z`, // triangle
  osb: (s) => `M0,${-1.2 * s} L${1.2 * s},0 L0,${1.2 * s} L${-1.2 * s},0 Z`, // diamond
  mdf: (s) => { // 5-point star
    const pts = []; const R = 1.3 * s, r = 0.55 * s;
    for (let i = 0; i < 10; i++) { const rad = i % 2 === 0 ? R : r, a = -Math.PI / 2 + (i * Math.PI) / 5;
      pts.push(`${(rad * Math.cos(a)).toFixed(2)},${(rad * Math.sin(a)).toFixed(2)}`); }
    return "M" + pts.join(" L") + " Z";
  },
};

async function drawBase() {
  const topo = await fetchFirst(STATES_URLS);
  if (topo && topo.objects && topo.objects.states) {
    const states = topojson.feature(topo, topo.objects.states);
    projection.fitExtent([[10, 20], [W - 10, H - 10]], states);
    const path = d3.geoPath(projection);
    gLand.selectAll("path").data(states.features).join("path").attr("class", "state").attr("d", path);
  } else {
    document.getElementById("mapWarn").hidden = false;
    projection.fitExtent([[10, 20], [W - 10, H - 10]], { type: "MultiPoint", coordinates: mills.map((m) => [m.lon, m.lat]) });
  }
}

function project() {
  mills.forEach((m) => { const p = projection([m.lon, m.lat]); m.x = p ? p[0] : null; m.y = p ? p[1] : null; });
}
const status = (m, y) => (y < m.open ? "none" : m.close != null && y >= m.close ? "closed" : "open");
const visible = () => mills.filter((m) => m.x != null && (filterMode === "all" || m.close != null)
  && (typeFilter === "all" || m.type === typeFilter));

function populateTypeFilter() {
  const sel = document.getElementById("typeFilter");
  const types = Array.from(new Set(mills.map((m) => m.type))).sort();
  const current = typeFilter;
  sel.innerHTML = `<option value="all">All types</option>` +
    types.map((t) => `<option value="${esc(t)}">${esc(TYPE_LABEL[t] || t)}</option>`).join("");
  typeFilter = types.includes(current) ? current : "all";
  sel.value = typeFilter;
}
const fmtYears = (m) => (m.close == null ? `${m.open} to present` : `${m.open} to ${m.close}`);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function positionTip(m) {
  const box = document.getElementById("mapbox").getBoundingClientRect();
  const sc = box.width / W, t = ztransform;
  const sx = (m.x * t.k + t.x) * sc, sy = (m.y * t.k + t.y) * sc;
  let x = sx + 12, y = sy - 10;
  if (x + tip.offsetWidth > box.width) x = sx - tip.offsetWidth - 12;
  if (y + tip.offsetHeight > box.height) y = box.height - tip.offsetHeight - 4;
  tip.style.left = Math.max(0, x) + "px"; tip.style.top = Math.max(0, y) + "px";
}
function showTip(m, pin) {
  const s = status(m, year);
  const st = s === "open" ? "Operating" : s === "closed" ? `Closed ${m.close}` : `Opens ${m.open}`;
  const conf = m.custom ? "" : m.checked ? "Closure year checked against announcements." : "Years approximate; verify before citing.";
  const typeLabel = TYPE_LABEL[m.type] || m.type;
  const cap = m.capacity != null ? `<br>Capacity: ${m.capacity.toLocaleString()} ${esc(m.capacity_unit || "")}` : "";
  tip.innerHTML = (pin ? `<button type="button" class="close" aria-label="Close details">&times;</button>` : "") +
    `<b>${esc(m.name)}</b>${esc(typeLabel)} — ${esc(m.company)}<br>${esc(m.city)}, ${esc(m.state)}<br>
    <span class="st">${st}</span> (${fmtYears(m)})${cap}${m.note ? `<span class="note">${esc(m.note)}</span>` : ""}
    ${conf ? `<span class="note">${conf}</span>` : ""}`;
  tip.classList.toggle("pinned", !!pin);
  tip.style.display = "block";
  positionTip(m);
  if (pin) tip.querySelector(".close").onclick = (e) => { e.stopPropagation(); unpin(); };
}
const hideTip = () => { tip.style.display = "none"; tip.classList.remove("pinned"); };
function unpin() { pinnedMill = null; hideTip(); }
function toggleTip(e, d) {
  e.stopPropagation();
  if (pinnedMill && pinnedMill.id === d.id) unpin();
  else { pinnedMill = d; showTip(d, true); }
}

// Shape outline for a type, sized to match the open-circle radius below; circle types get a flag instead of a path.
const CIRCLE_TYPES = new Set(["pulp", "paper", "pulp/chip", "mill", undefined]);
const OPEN_R = 4.6, CLOSED_R = 3.6;
function unitPath(type) {
  if (!CIRCLE_TYPES.has(type) && TYPE_PATH[type]) return TYPE_PATH[type](OPEN_R);
  return null; // null => render as <circle>, not <path>
}
// Per-type categorical color (CSS custom properties in style.css; theme-aware via getComputedStyle).
const TYPE_VAR = { pulp: "--t-pulp", paper: "--t-paper", "pulp/chip": "--t-pulpchip", mill: "--t-mill",
  sawmill: "--t-sawmill", plywood: "--t-plywood", osb: "--t-osb", mdf: "--t-mdf" };
function typeColor(type) {
  return getComputedStyle(document.documentElement).getPropertyValue(TYPE_VAR[type] || TYPE_VAR.pulp).trim();
}

function render() {
  const data = visible();
  const dur = reduced ? 0 : 350;
  const sel = gMills.selectAll(".mill").data(data, (d) => d.id);
  sel.exit().remove();
  const ent = sel.enter().append(function (d) { return document.createElementNS(d3.namespaces.svg, unitPath(d.type) ? "path" : "circle"); })
    .attr("class", "mill").attr("tabindex", 0).attr("data-type", (d) => d.type)
    .attr("aria-label", (d) => `${TYPE_LABEL[d.type] || d.type}: ${d.name}, ${d.city} ${d.state}, ${fmtYears(d)}`)
    .on("mouseenter", (e, d) => { if (!pinnedMill) showTip(d, false); })
    .on("mouseleave", () => { if (!pinnedMill) hideTip(); })
    .on("focus", (e, d) => { if (!pinnedMill) showTip(d, false); })
    .on("blur", () => { if (!pinnedMill) hideTip(); })
    .on("click", (e, d) => toggleTip(e, d))
    .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleTip(e, d); } });
  ent.each(function (d) {
    const p = unitPath(d.type);
    if (p) d3.select(this).attr("d", p).attr("transform", `translate(${d.x},${d.y}) scale(0)`);
    else d3.select(this).attr("cx", d.x).attr("cy", d.y).attr("r", 0);
  });
  ent.merge(sel).each(function (d) {
    const s = status(d, year), el = d3.select(this), shaped = unitPath(d.type) != null;
    el.classed("op", s === "open").classed("cl", s === "closed").style("display", s === "none" ? "none" : null);
    const targetR = s === "open" ? OPEN_R : s === "closed" ? CLOSED_R : 0;
    if (shaped) el.transition().duration(dur).attr("transform", `translate(${d.x},${d.y}) scale(${targetR / OPEN_R})`);
    else el.transition().duration(dur).attr("r", targetR);
    if (!reduced && playing && s === "closed" && d.close === year) {
      gFx.append("circle").attr("class", "ripple").attr("cx", d.x).attr("cy", d.y).attr("r", 4)
        .attr("stroke", typeColor(d.type)).attr("stroke-width", 2).attr("opacity", 0.9)
        .transition().duration(900).ease(d3.easeCubicOut).attr("r", 22).attr("opacity", 0).remove();
    }
  });
  let o = 0, c = 0, e = 0;
  data.forEach((m) => { const s = status(m, year); if (s !== "none") e++; if (s === "open") o++; if (s === "closed") c++; });
  document.getElementById("nOpen").textContent = o;
  document.getElementById("nClosed").textContent = c;
  document.getElementById("nEver").textContent = e;
  document.getElementById("bigYear").textContent = year;
  slider.value = year;
  updateLog(data); moveCursor();
  if (pinnedMill) {
    const cur = data.find((m) => m.id === pinnedMill.id);
    if (cur) { pinnedMill = cur; showTip(cur, true); } else unpin();
  }
}

function updateLog(data) {
  const ev = [];
  data.forEach((m) => {
    if (m.open <= year) ev.push({ y: m.open, k: "o", m });
    if (m.close != null && m.close <= year) ev.push({ y: m.close, k: "c", m });
  });
  ev.sort((a, b) => b.y - a.y || (a.k === "c" ? -1 : 1));
  document.getElementById("log").innerHTML = ev.slice(0, 14).map((e) => `<li class="${e.y === year ? "now" : ""}"><span class="y">${e.y}</span>
    <span><span class="k-${e.k}">${e.k === "c" ? "Closed" : "Opened"}</span> ${esc(e.m.name)}, ${esc(e.m.state)}</span></li>`).join("")
    || `<li><span class="y"></span><span>Press Play or drag the slider to start.</span></li>`;
}

let cs, cx, cy, cursor;
const cm = { l: 28, r: 6, t: 6, b: 18 }, cw = 290, ch = 130;
function drawChart() {
  cs.selectAll("*").remove();
  const data = visible();
  const series = d3.range(Y0, Y1 + 1).map((y) => {
    let o = 0, c = 0;
    data.forEach((m) => { const s = status(m, y); if (s === "open") o++; if (s === "closed") c++; });
    return { y, o, c };
  });
  cx = d3.scaleLinear([Y0, Y1], [cm.l, cw - cm.r]);
  cy = d3.scaleLinear([0, d3.max(series, (d) => Math.max(d.o, d.c)) || 1], [ch - cm.b, cm.t]).nice();
  cs.append("g").attr("class", "axis").attr("transform", `translate(0,${ch - cm.b})`)
    .call(d3.axisBottom(cx).ticks(5).tickFormat(d3.format("d")).tickSizeOuter(0));
  cs.append("g").attr("class", "axis").attr("transform", `translate(${cm.l},0)`).call(d3.axisLeft(cy).ticks(4).tickSizeOuter(0));
  const line = (k) => d3.line().x((d) => cx(d.y)).y((d) => cy(d[k]));
  cs.append("path").datum(series).attr("fill", "none").attr("stroke", "var(--open)").attr("stroke-width", 2).attr("d", line("o"));
  cs.append("path").datum(series).attr("fill", "none").attr("stroke", "var(--closed)").attr("stroke-width", 2).attr("stroke-dasharray", "4 3").attr("d", line("c"));
  cursor = cs.append("line").attr("y1", cm.t).attr("y2", ch - cm.b).attr("stroke", "var(--ink)").attr("opacity", 0.5);
  moveCursor();
}
function moveCursor() { if (cursor) cursor.attr("x1", cx(year)).attr("x2", cx(year)); }

function setYear(y) {
  y = Math.max(Y0, Math.min(Y1, Math.round(y)));
  if (y === prevYear) return;
  year = y; prevYear = y; render();
}
function tick(t) {
  if (!playing) return;
  if (!last) last = t;
  const dt = (t - last) / 1000; last = t;
  fYear += dt * +document.getElementById("speed").value;
  if (fYear >= Y1) { fYear = Y1; setYear(Y1); stop(); return; }
  setYear(Math.floor(fYear));
  requestAnimationFrame(tick);
}
function start() {
  if (year >= Y1) { fYear = Y0; setYear(Y0); }
  playing = true; last = 0; fYear = year;
  const b = document.getElementById("play"); b.textContent = "Pause"; b.setAttribute("aria-label", "Pause animation");
  requestAnimationFrame(tick);
}
function stop() {
  playing = false;
  const b = document.getElementById("play"), done = year >= Y1;
  b.textContent = done ? "Replay" : "Play"; b.setAttribute("aria-label", done ? "Replay animation" : "Play animation");
}

function setRange() {
  Y0 = Math.floor((d3.min(mills, (m) => m.open) - 2) / 5) * 5;
  Y1 = Math.max(2026, d3.max(mills, (m) => m.close || 0));
  slider.min = Y0; slider.max = Y1;
}

const CSV_COLS = ["name", "company", "city", "state", "lat", "lon", "open", "close", "checked", "note", "type", "capacity", "capacity_unit"];
function downloadSubset() {
  const rows = visible();
  if (!rows.length) { alert("No mills match the current filters."); return; }
  const csv = d3.csvFormat(rows.map((m) => ({
    name: m.name, company: m.company, city: m.city, state: m.state, lat: m.lat, lon: m.lon,
    open: m.open, close: m.close == null ? "" : m.close, checked: m.checked ? 1 : 0,
    note: m.note, type: m.type, capacity: m.capacity == null ? "" : m.capacity, capacity_unit: m.capacity_unit,
  })), CSV_COLS);
  const bits = ["mills"];
  if (filterMode === "closed") bits.push("closed-only");
  if (typeFilter !== "all") bits.push(typeFilter.replace(/[^a-z0-9]+/gi, "-"));
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `${bits.join("_")}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

function resetView() {
  gMills.selectAll("*").remove(); prevYear = null; unpin(); stop(); fYear = Y0; drawChart(); setYear(Y0);
}

(async function init() {
  const foot = document.getElementById("foot");
  for (const lib of LIBS) {
    if (!(await loadScript(lib.urls)) || !lib.test()) {
      foot.textContent = "Couldn't load the chart libraries. Run python fetch_assets.py once with internet access, or check your connection.";
      return;
    }
  }
  d3 = window.d3;
  svg = d3.select("#map");
  zoomLayer = svg.append("g");
  const bgCapture = zoomLayer.append("rect").attr("class", "bg-capture").attr("width", W).attr("height", H);
  gLand = zoomLayer.append("g"); gMills = zoomLayer.append("g"); gFx = zoomLayer.append("g");
  cs = d3.select("#chart"); tip = document.getElementById("tip"); slider = document.getElementById("slider");
  projection = d3.geoAlbersUsa();

  ztransform = d3.zoomIdentity;
  zoom = d3.zoom().scaleExtent([1, 10]).translateExtent([[0, 0], [W, H]])
    .on("start", () => svg.node().classList.add("panning"))
    .on("zoom", (event) => { ztransform = event.transform; zoomLayer.attr("transform", ztransform); if (pinnedMill) positionTip(pinnedMill); })
    .on("end", () => svg.node().classList.remove("panning"));
  svg.call(zoom);
  bgCapture.on("click", () => { if (pinnedMill) unpin(); });
  document.getElementById("zoomIn").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1.6);
  document.getElementById("zoomOut").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1 / 1.6);
  document.getElementById("zoomReset").onclick = () => svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && pinnedMill) unpin(); });

  const text = await fetchFirst([DATA_URL], "text");
  if (text == null) {
    foot.textContent = "Couldn't read data/mills.csv. Start the app with python serve.py (browsers block file:// data loads).";
    return;
  }
  try { mills = parseMills(text, false).parsed; }
  catch (err) { foot.textContent = `data/mills.csv has a problem: ${err.message}`; return; }

  await drawBase(); project(); setRange(); populateTypeFilter(); drawChart(); setYear(Y0);

  document.getElementById("play").onclick = () => (playing ? stop() : start());
  slider.oninput = () => { stop(); fYear = +slider.value; setYear(+slider.value); };
  document.getElementById("filter").onchange = (e) => { filterMode = e.target.value; prevYear = null; drawChart(); setYear(year); };
  document.getElementById("typeFilter").onchange = (e) => { typeFilter = e.target.value; prevYear = null; drawChart(); setYear(year); };
  document.getElementById("csv").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    try {
      const { parsed, dropped } = parseMills(await f.text(), true);
      if (!parsed.length) throw new Error("No rows had numeric lat, lon and open values.");
      mills = parsed; project(); setRange(); typeFilter = "all"; populateTypeFilter();
      const offMap = mills.filter((m) => m.x == null).length;
      foot.textContent = `Showing ${parsed.length} mills from ${f.name}.` +
        (dropped ? ` ${dropped} row(s) skipped for missing coordinates or open year.` : "") +
        (offMap ? ` ${offMap} mill(s) fall outside the US projection and are hidden.` : "");
      resetView();
    } catch (err) { alert("Couldn't load that CSV. " + err.message); }
  };
  document.getElementById("download").onclick = downloadSubset;

  if (!reduced) setTimeout(start, 600);
})();
