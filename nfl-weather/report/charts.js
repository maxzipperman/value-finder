/* Hand-rolled SVG charts for the report. Every chart re-renders to its
   container width (ResizeObserver) so type stays legible on phones.
   Colors come from CSS custom properties, so both themes work. */
const NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}
function styled(e, s) { Object.assign(e.style, s); return e; }
function lin(d0, d1, r0, r1) { const f = v => r0 + (v - d0) * (r1 - r0) / (d1 - d0); f.d0 = d0; f.d1 = d1; return f; }
function ticks(min, max, n) {
  const span = max - min, raw = span / Math.max(n, 1), mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function fmt(v, d = 1, sign = false) {
  if (v == null || !isFinite(v)) return "–";
  const s = Math.abs(v).toFixed(d);
  return (v < 0 ? "−" : sign && v > 0 ? "+" : "") + s;
}
function textW(str, size) { return str.length * size * 0.52; }

/* ---------- tooltip ---------- */
const tip = document.getElementById("tip");
function showTip(evt, title, lines) {
  tip.replaceChildren();
  if (title) { const h = document.createElement("div"); h.className = "tip-title"; h.textContent = title; tip.appendChild(h); }
  for (const ln of lines) {
    const row = document.createElement("div"); row.className = "tip-row";
    if (ln.color) { const k = document.createElement("span"); k.className = "tip-key"; k.style.background = ln.color; row.appendChild(k); }
    const v = document.createElement("strong"); v.textContent = ln.value; row.appendChild(v);
    const l = document.createElement("span"); l.className = "tip-label"; l.textContent = ln.label; row.appendChild(l);
    tip.appendChild(row);
  }
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let x = evt.clientX + 14, y = evt.clientY + 14;
  if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - 14;
  if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - 14;
  tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
}
function hideTip() { tip.hidden = true; }
function hoverable(node, title, lines) {
  node.setAttribute("tabindex", "0");
  node.addEventListener("pointermove", e => showTip(e, title, lines()));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("focus", () => { const b = node.getBoundingClientRect(); showTip({ clientX: b.right, clientY: b.top }, title, lines()); });
  node.addEventListener("blur", hideTip);
}

function mount(container, draw) {
  let last = 0;
  const run = () => {
    const w = Math.round(container.clientWidth);
    if (!w || w === last) return;
    last = w; container.replaceChildren(); draw(container, w);
  };
  new ResizeObserver(run).observe(container);
  run();
}

function axisText(svg, x, y, str, anchor = "middle", cls = "ax") {
  const t = svgEl("text", { x, y, "text-anchor": anchor, class: cls }, svg); t.textContent = str; return t;
}

/* ---------- horizontal dot + whisker (rows x series) ----------
   rows: [{label, sub, values: [{v, lo, hi, sig}]}], series: [{name, color}] */
function dotWhisker(container, { rows, series, unit = "", domain, rowH, labelW = 250, decimals = 1, zeroLabel }) {
  mount(container, (c, W) => {
    const narrow = W < Math.max(300, labelW + 170);
    const lw = narrow ? 0 : Math.min(labelW, W * 0.42);
    const ns = series.length;
    const rh = rowH || (ns > 1 ? 16 + ns * 10 : 26);
    const top = 8, labTop = narrow ? 30 : 0;
    const rowFull = rh + labTop;
    const H = top + rows.length * rowFull + 30;
    const svg = svgEl("svg", { width: W, height: H, role: "img" }, c);
    let lo = 0, hi = 0;
    rows.forEach(r => r.values.forEach(v => { if (v && v.v != null) { lo = Math.min(lo, v.lo ?? v.v, v.v); hi = Math.max(hi, v.hi ?? v.v, v.v); } }));
    if (domain) { lo = domain[0]; hi = domain[1]; }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const x0 = lw + 8, x1 = W - 12;
    const x = lin(lo, hi, x0, x1);
    const tk = ticks(lo, hi, Math.max(3, Math.floor((x1 - x0) / 70)));
    const plotBottom = top + rows.length * rowFull;
    tk.forEach(t => {
      svgEl("line", { x1: x(t), x2: x(t), y1: top, y2: plotBottom, class: t === 0 ? "zero" : "grid" }, svg);
      axisText(svg, x(t), plotBottom + 18, (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t) + unit);
    });
    if (!tk.includes(0) && lo < 0 && hi > 0) svgEl("line", { x1: x(0), x2: x(0), y1: top, y2: plotBottom, class: "zero" }, svg);
    rows.forEach((r, i) => {
      const y0 = top + i * rowFull;
      if (i % 2 === 1) svgEl("rect", { x: 0, y: y0, width: W, height: rowFull, class: "band" }, svg);
      if (narrow) {
        const t = axisText(svg, 0, y0 + 16, r.label, "start", "rowlab"); if (r.sub) { const s = svgEl("tspan", { class: "rowsub", dx: 6 }, t); s.textContent = r.sub; }
      } else {
        const cy = y0 + rh / 2;
        axisText(svg, lw, cy + (r.sub ? -1 : 4), r.label, "end", "rowlab");
        if (r.sub) axisText(svg, lw, cy + 13, r.sub, "end", "rowsub");
      }
      const g = svgEl("g", { class: "hit" }, svg);
      svgEl("rect", { x: 0, y: y0, width: W, height: rowFull, fill: "transparent" }, g);
      r.values.forEach((v, j) => {
        if (!v || v.v == null) return;
        const cy = y0 + labTop + (ns === 1 ? rh / 2 : 8 + 5 + j * 10 + (rh - 16 - ns * 10) / 2);
        if (v.lo != null && v.hi != null) {
          const a = x(Math.min(v.lo, v.hi)), b = x(Math.max(v.lo, v.hi));
          styled(svgEl("line", { x1: a, x2: b, y1: cy, y2: cy, "stroke-width": 2, "stroke-linecap": "round" }, g), { stroke: series[j].color, opacity: 0.55 });
        }
        const dot = svgEl("circle", { cx: x(v.v), cy, r: 4.5, "stroke-width": 2 }, g);
        styled(dot, { fill: v.hollow ? "var(--surface)" : series[j].color, stroke: v.hollow ? series[j].color : "var(--surface)" });
        if (v.hollow) dot.setAttribute("stroke-width", 2);
      });
      hoverable(g, r.label + (r.sub ? " · " + r.sub : ""), () => r.values.map((v, j) => v && v.v != null ? ({
        color: series[j].color,
        value: fmt(v.v, decimals, true) + unit + (v.sig ? " " + v.sig : ""),
        label: series[j].name + (v.lo != null ? `  [${fmt(Math.min(v.lo, v.hi), decimals, true)}, ${fmt(Math.max(v.lo, v.hi), decimals, true)}]` : ""),
      }) : null).filter(Boolean));
    });
    if (zeroLabel) axisText(svg, x(0), H - 1, zeroLabel, "middle", "ax faint");
  });
}

/* ---------- vertical dot + whisker by category (grouped series) ----------
   cats: [label], series: [{name, color, values:[{v, lo, hi, n}]}], ref: {v, label} */
function columnDots(container, { cats, series, unit = "%", domain, ref, height = 280, decimals = 1, xTitle }) {
  mount(container, (c, W) => {
    const H = height, top = 16, bottom = xTitle ? 48 : 32, left = 44, right = 12;
    const svg = svgEl("svg", { width: W, height: H, role: "img" }, c);
    const y = lin(domain[0], domain[1], H - bottom, top);
    const tk = ticks(domain[0], domain[1], 5);
    tk.forEach(t => { svgEl("line", { x1: left, x2: W - right, y1: y(t), y2: y(t), class: "grid" }, svg); axisText(svg, left - 6, y(t) + 4, t + unit, "end"); });
    if (ref) {
      svgEl("line", { x1: left, x2: W - right, y1: y(ref.v), y2: y(ref.v), class: "ref" }, svg);
      axisText(svg, left + 6, y(ref.v) - 6, ref.label, "start", "ax reflab");
    }
    const band = (W - left - right) / cats.length;
    cats.forEach((cat, i) => {
      const cx = left + band * (i + 0.5);
      axisText(svg, cx, H - bottom + 18, cat);
      const g = svgEl("g", { class: "hit" }, svg);
      svgEl("rect", { x: left + band * i, y: top, width: band, height: H - bottom - top, fill: "transparent" }, g);
      series.forEach((s, j) => {
        const v = s.values[i]; if (!v || v.v == null) return;
        const off = (j - (series.length - 1) / 2) * Math.min(22, band / (series.length + 1));
        const px = cx + off;
        if (v.lo != null) styled(svgEl("line", { x1: px, x2: px, y1: y(Math.max(domain[0], v.lo)), y2: y(Math.min(domain[1], v.hi)), "stroke-width": 2, "stroke-linecap": "round" }, g), { stroke: s.color, opacity: 0.55 });
        styled(svgEl("circle", { cx: px, cy: y(v.v), r: 5, "stroke-width": 2 }, g), { fill: s.color, stroke: "var(--surface)" });
      });
      hoverable(g, cat + (xTitle ? " " + xTitle.replace(/^.*\(|\)$/g, "") : ""), () => series.map(s => {
        const v = s.values[i]; if (!v || v.v == null) return null;
        return { color: s.color, value: fmt(v.v, decimals) + unit, label: s.name + (v.n != null ? ` · ${v.n.toLocaleString()} games` : "") + (v.lo != null ? ` · 95% CI ${fmt(v.lo, decimals)}–${fmt(v.hi, decimals)}` : "") };
      }).filter(Boolean));
    });
    if (xTitle) axisText(svg, left + (W - left - right) / 2, H - 6, xTitle, "middle", "ax faint");
  });
}

/* ---------- paired horizontal bars around zero ----------
   rows: [{label, a, b}], series: [{name, color}] (a -> series[0], b -> series[1]) */
function pairedBars(container, { rows, series, unit = "", decimals = 1, labelW = 150 }) {
  mount(container, (c, W) => {
    const narrow = W < Math.max(300, labelW + 170);
    const lw = narrow ? 0 : labelW, labTop = narrow ? 22 : 0;
    const barH = 12, gap = 2, rowH = barH * 2 + gap + 18 + labTop, top = 6;
    const H = top + rows.length * rowH + 26;
    const svg = svgEl("svg", { width: W, height: H, role: "img" }, c);
    let lo = 0, hi = 0;
    rows.forEach(r => { lo = Math.min(lo, r.a, r.b); hi = Math.max(hi, r.a, r.b); });
    const padL = (hi - lo) * 0.18; lo -= padL; hi += padL * 0.6;
    const x0 = lw + 10, x1 = W - 14, x = lin(lo, hi, x0, x1);
    const tk = ticks(lo, hi, Math.max(3, Math.floor((x1 - x0) / 70)));
    const bottom = top + rows.length * rowH;
    tk.forEach(t => { svgEl("line", { x1: x(t), x2: x(t), y1: top, y2: bottom, class: t === 0 ? "zero" : "grid" }, svg); axisText(svg, x(t), bottom + 18, (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t) + unit); });
    rows.forEach((r, i) => {
      const y0 = top + i * rowH;
      if (narrow) axisText(svg, 0, y0 + 15, r.label, "start", "rowlab");
      else axisText(svg, lw, y0 + 9 + barH + 4, r.label, "end", "rowlab");
      const g = svgEl("g", { class: "hit" }, svg);
      svgEl("rect", { x: 0, y: y0, width: W, height: rowH, fill: "transparent" }, g);
      [r.a, r.b].forEach((v, j) => {
        const yy = y0 + labTop + 9 + j * (barH + gap);
        const a = x(Math.min(0, v)), b = x(Math.max(0, v)), w = Math.max(1, b - a);
        const rad = Math.min(4, w / 2);
        // 4px rounded data end, square at the baseline
        const d = v >= 0
          ? `M${a},${yy} h${w - rad} a${rad},${rad} 0 0 1 ${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 1 -${rad},${rad} h-${w - rad} z`
          : `M${b},${yy} h-${w - rad} a${rad},${rad} 0 0 0 -${rad},${rad} v${barH - 2 * rad} a${rad},${rad} 0 0 0 ${rad},${rad} h${w - rad} z`;
        styled(svgEl("path", { d }, g), { fill: series[j].color });
        const lab = fmt(v, decimals, true);
        const tx = v >= 0 ? b + 5 : a - 5;
        axisText(g, tx, yy + barH - 2, lab, v >= 0 ? "start" : "end", "val");
      });
      hoverable(g, r.label, () => [
        { color: series[0].color, value: fmt(r.a, decimals, true) + unit, label: series[0].name },
        { color: series[1].color, value: fmt(r.b, decimals, true) + unit, label: series[1].name },
        ...(r.note ? [{ value: r.note, label: "" }] : []),
      ]);
    });
  });
}

/* ---------- line chart (numeric or date x) with crosshair ----------
   series: [{name, color, points:[[x,y]], area?}] */
function lineChart(container, { series, xType = "num", yUnit = "", xUnit = "", height = 300, yDomain, xTicks, label, endLabels = [], decimals = 1, xFmt }) {
  mount(container, (c, W) => {
    const H = height, top = 14, bottom = 30, left = 46, right = endLabels.length ? Math.min(150, W * 0.28) : 16;
    const svg = svgEl("svg", { width: W, height: H, role: "img" }, c);
    const all = series.flatMap(s => s.points);
    const xs = all.map(p => p[0]);
    const xmin = Math.min(...xs), xmax = Math.max(...xs);
    let [ymin, ymax] = yDomain || [Math.min(...all.map(p => p[1])), Math.max(...all.map(p => p[1]))];
    const x = lin(xmin, xmax, left, W - right), y = lin(ymin, ymax, H - bottom, top);
    ticks(ymin, ymax, 5).forEach(t => { svgEl("line", { x1: left, x2: W - right, y1: y(t), y2: y(t), class: t === 0 ? "zero" : "grid" }, svg); axisText(svg, left - 6, y(t) + 4, (t > 0 && yUnit === " u" ? "+" : "") + (t < 0 ? "−" + Math.abs(t) : t) + (yUnit === " u" ? "" : yUnit), "end"); });
    const xt = xTicks || ticks(xmin, xmax, Math.max(3, Math.floor((W - left - right) / 80)));
    xt.forEach(t => axisText(svg, x(t), H - bottom + 18, xFmt ? xFmt(t) : t + xUnit));
    series.forEach(s => {
      const d = s.points.map((p, i) => (i ? "L" : "M") + x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join("");
      if (s.area) styled(svgEl("path", { d: d + `L${x(s.points.at(-1)[0])},${y(Math.max(ymin, 0))}L${x(s.points[0][0])},${y(Math.max(ymin, 0))}Z` }, svg), { fill: s.color, opacity: 0.1 });
      styled(svgEl("path", { d, fill: "none", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg), { stroke: s.color });
      if (s.markers) s.points.forEach(p => styled(svgEl("circle", { cx: x(p[0]), cy: y(p[1]), r: 4, "stroke-width": 2 }, svg), { fill: s.color, stroke: "var(--surface)" }));
      const lp = s.points.at(-1);
      styled(svgEl("circle", { cx: x(lp[0]), cy: y(lp[1]), r: 4.5, "stroke-width": 2 }, svg), { fill: s.color, stroke: "var(--surface)" });
      if (endLabels.includes(s.name)) axisText(svg, x(lp[0]) + 9, y(lp[1]) + 4, `${s.name} ${fmt(lp[1], decimals)}${yUnit === " u" ? "" : yUnit}`, "start", "val");
    });
    // crosshair
    const cross = svgEl("line", { y1: top, y2: H - bottom, class: "cross", visibility: "hidden" }, svg);
    const hit = svgEl("rect", { x: left, y: top, width: W - left - right, height: H - top - bottom, fill: "transparent", tabindex: 0 }, svg);
    const xsU = [...new Set(xs)].sort((a, b) => a - b);
    const nearest = px => { const v = lin(left, W - right, xmin, xmax)(px); return xsU.reduce((a, b) => Math.abs(b - v) < Math.abs(a - v) ? b : a); };
    hit.addEventListener("pointermove", e => {
      const b = svg.getBoundingClientRect(), xv = nearest(e.clientX - b.left);
      cross.setAttribute("x1", x(xv)); cross.setAttribute("x2", x(xv)); cross.setAttribute("visibility", "visible");
      showTip(e, (label ? label(xv) : xv + xUnit), series.map(s => { const p = s.points.find(q => q[0] === xv); return p ? { color: s.color, value: fmt(p[1], decimals) + (yUnit === " u" ? " units" : yUnit), label: s.name } : null; }).filter(Boolean));
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(); });
  });
}

/* ---------- table helper (textContent only) ---------- */
function table(container, cols, data) {
  const wrap = document.createElement("div"); wrap.className = "tablewrap";
  const t = document.createElement("table");
  const thead = t.createTHead().insertRow();
  cols.forEach(c => { const th = document.createElement("th"); th.textContent = c.h; if (c.num) th.className = "num"; thead.appendChild(th); });
  const tb = t.createTBody();
  data.forEach(r => {
    const tr = tb.insertRow();
    cols.forEach(c => {
      const td = tr.insertCell();
      const v = c.f ? c.f(r) : r[c.k];
      if (v instanceof Node) td.appendChild(v); else td.textContent = v == null ? "–" : v;
      if (c.num) td.className = "num";
    });
  });
  wrap.appendChild(t); container.appendChild(wrap); return t;
}
function pill(text, kind) { const s = document.createElement("span"); s.className = "pill " + kind; s.textContent = text; return s; }
