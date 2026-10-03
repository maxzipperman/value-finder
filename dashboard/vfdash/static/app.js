/* Value Finder dashboard. Reads the local server's JSON and draws it; it sends nothing anywhere else and has
   no way to change a file. Every piece of text from the server goes in with textContent, never as markup. */
"use strict";
(function () {
  const REFRESH_MS = 60000;
  const main = document.getElementById("main");
  const stampEl = document.getElementById("stamp");
  const bannerEl = document.getElementById("banner");
  const state = { openWaiting: new Set(), btOpen: new Set(), board: { sport: "all", signals: false },
    signals: { sport: "all", rule: "all", result: "all" }, last: null, seq: 0 };
  // The Signals screen's rules, as the server names them (vfdash/signals.py LOG_RULES), and its results.
  const LOG_RULES = { nfl_rule_b: "nfl", nfl_rule_b_backup: "nfl", nfl_lean: "nfl", cfb_rule_b: "cfb", cfb_rule_ht: "cfb" };
  const RESULTS = [["all", "All results"], ["won", "Won"], ["lost", "Lost"], ["push", "Push"], ["pending", "Pending"], ["void", "Void"]];

  // ------------------------------------------------------------------ small helpers
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      }
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false || kid === "") continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  function cols(widths) {
    return h("colgroup", null, widths.map((w) => { const c = h("col"); c.style.width = w; return c; }));
  }
  const fmtInt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : n);
  // +1.4, −0.35 (a true minus sign), 0: how the charts write a signed number
  function signedNum(x) {
    const r = Math.round(x * 100) / 100;
    return r > 0 ? "+" + r : r < 0 ? "−" + Math.abs(r) : "0";
  }
  const levelWords = { ok: "Healthy", warn: "Needs a look", fail: "Failed" };
  function dot(level) {
    return h("span", { class: "dot " + (level || ""), role: "img", "aria-label": levelWords[level] || "Unknown",
      title: levelWords[level] || "Unknown" });
  }
  function daysWords(d) {
    if (d === null || d === undefined) return "";
    if (d <= 0) return "today";
    if (d === 1) return "tomorrow";
    return "in " + d + " days";
  }

  // ------------------------------------------------------------------ badges and the legend
  // One colour for signals, used for nothing else: a filled "Signal" badge, the same colour outlined for a signal at
  // the NFL's backup price, and a tinted row. A watch is a quiet outlined badge in the neutral colour. Every badge
  // carries its word, so colour is never the only thing that says what it is.
  const BADGE_WORDS = { signal: "Signal", backup: "Signal, backup price", watch: "Watch" };
  function badge(kind) {
    return BADGE_WORDS[kind] ? h("span", { class: "badge " + kind }, BADGE_WORDS[kind]) : "";
  }
  function resultBadge(result, words) {
    return h("span", { class: "badge " + result }, words);
  }
  // A rule's status on a row: a signal is its badge alone; a watch is its badge and why.
  function ruleLine(c) {
    if (c.badge === "signal" || c.badge === "backup") return h("div", { class: "sig" }, c.rule + ": ", badge(c.badge));
    if (c.badge === "watch") return h("div", null, c.rule + ": ", badge("watch"), " " + c.words);
    return h("div", null, c.rule + ": " + c.words);
  }
  function legend(extra) {
    return h("div", { class: "legend", role: "note", "aria-label": "What the badges mean" },
      h("span", null, badge("signal"), "the rule fired at its registered price"),
      h("span", null, badge("backup"), "the NFL wind rule fired at the backup price (the consensus line); logged apart, not part of the decision"),
      h("span", null, badge("watch"), "a model lean, or a wind trigger that did not become a signal; never a bet"),
      h("span", null, h("span", { class: "tint", "aria-hidden": "true" }), extra || "a tinted row is a game whose newest row is a signal"));
  }

  // ------------------------------------------------------------------ routing
  function parseHash() {
    let raw;
    try {
      raw = decodeURIComponent((location.hash || "#home").slice(1));
    } catch (e) {
      raw = "home";                                   // a damaged address: show the home screen
    }
    const [path, query] = raw.split("?");
    const parts = path.split("/");
    const params = new URLSearchParams(query || "");
    return { screen: parts[0] || "home", arg: parts.slice(1).join("/"), params };
  }

  // Each screen: the address after "#", its answer from the server, the function that draws it, and its link in the
  // navigation (index.html). A new screen adds one entry here, one link there, and one route in vfdash/server.py.
  const SCREENS = {
    home: { url: () => "/api/home", draw: drawHome, nav: "home" },
    signals: { url: () => "/api/signals", draw: drawSignals, nav: "signals",
      waiting: "Running both scorers as previews; this takes a few seconds the first time." },
    backtests: { url: () => "/api/backtests", draw: drawBacktests, nav: "backtests" },
    board: { url: () => "/api/board", draw: drawBoard, nav: "board" },
    game: { url: (r) => "/api/game?id=" + encodeURIComponent(r.arg), draw: drawGame, nav: "board" },
    tests: { url: () => "/api/tests", draw: drawTests, nav: "tests",
      waiting: "Running both scorers as previews; this takes a few seconds the first time." },
    jobs: { url: (r) => (r.arg === "records" ? "/api/run-records" : "/api/jobs"),
      draw: (d, r) => (r.arg === "records" ? drawRecords(d) : drawJobs(d)), nav: "jobs" },
    pull: { url: () => "/api/pull", draw: drawPull, nav: "downloads" },
    downloads: { url: () => "/api/pull", draw: drawPull, nav: "downloads" },
    research: { url: () => "/api/research", draw: drawResearch, nav: "research" },
  };

  async function load(quiet) {
    const r = parseHash();
    const screen = SCREENS[r.screen] || SCREENS.home;
    if (r.screen === "board") {
      state.board.sport = ["nfl", "cfb"].includes(r.params.get("sport")) ? r.params.get("sport") : "all";
      state.board.signals = r.params.get("signals") === "1";
    }
    if (r.screen === "signals") {
      const s = state.signals;
      s.sport = ["nfl", "cfb"].includes(r.params.get("sport")) ? r.params.get("sport") : "all";
      const rule = r.params.get("rule");
      s.rule = Object.hasOwn(LOG_RULES, rule || "") && (s.sport === "all" || LOG_RULES[rule] === s.sport) ? rule : "all";
      s.result = RESULTS.some(([k]) => k === r.params.get("result")) ? r.params.get("result") : "all";
    }
    for (const a of document.querySelectorAll(".tabs a")) {
      if (a.dataset.screen === screen.nav) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    const seq = ++state.seq;
    if (!quiet && screen.waiting) main.replaceChildren(h("p", { class: "muted" }, screen.waiting));
    let data;
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 150000);
      const res = await fetch(screen.url(r), { cache: "no-store", signal: ctrl.signal });
      clearTimeout(timer);
      data = await res.json();
    } catch (e) {
      if (seq !== state.seq) return;
      const when = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
      stampEl.replaceChildren(h("span", null, "The dashboard server did not answer at " + when + ". "),
        h("strong", null, state.last ? "Showing the last read." : "Is it running?"));
      if (!state.last) main.replaceChildren(h("p", { class: "muted" }, "The dashboard server isn't answering. If it was just installed or the Mac just woke, give it a minute."));
      return;
    }
    if (seq !== state.seq) return;
    state.last = data;
    const y = window.scrollY;
    drawChrome(data);
    const out = [];
    if (data.error) out.push(h("div", { class: "notes" }, h("p", null, data.error)));
    if (data.notes && data.notes.length) {
      out.push(h("div", { class: "notes", role: "note" }, data.notes.map((n) => h("p", null, n))));
    }
    let body = null;
    if (!data.error || data.header) {
      try {
        body = screen.draw(data, r);
      } catch (e) {
        body = h("p", { class: "muted" }, "Part of this screen could not be drawn. The data it read is fine; this is a problem in the page itself.");
      }
    }
    main.replaceChildren(...out, body || "");
    if (quiet) window.scrollTo(0, y);
    else window.scrollTo(0, 0);
  }

  function drawChrome(data) {
    const hd = data.header;
    if (hd) {
      // the tab shows how many signals are live, so a signal is seen from any screen: "(1) Value Finder"
      const live = typeof hd.signals_live === "number" ? hd.signals_live : 0;
      document.title = (live > 0 ? "(" + live + ") " : "") + "Value Finder";
      stampEl.replaceChildren(h("strong", null, hd.last_written), " · " + hd.read_at);
      const level = hd.health;
      if (level === "fail" || level === "warn") {
        bannerEl.hidden = false;
        bannerEl.className = "banner " + level;
        bannerEl.replaceChildren(h("div", { role: "alert" },
          h("strong", null, level === "fail" ? "Something needs attention" : "Worth a look"),
          h("ul", null, (hd.problems || []).map((p) => h("li", null, p)))));
      } else {
        bannerEl.hidden = true;
        bannerEl.replaceChildren();
      }
    }
  }

  function panel(title, link, ...body) {
    return h("section", { class: "panel" },
      h("header", null, h("h2", null, title), link || ""),
      h("div", { class: "body" }, ...body));
  }

  // ------------------------------------------------------------------ home
  function tile(label, value, sub) {
    return h("div", { class: "tile" }, h("div", { class: "label" }, label),
      h("div", { class: "value" }, value), h("div", { class: "sub" }, sub || " "));
  }

  // Every signal live on the board, one row each (one per rule: a game can signal under Rule B and Rule HT), above the
  // four numbers; one quiet line when there is none. The tab, the tile and the menu-bar light count games, so the
  // heading says how many games too when that differs: "4 signals are live, on 3 games".
  function livePanel(d) {
    const live = d.live || [];
    if (!live.length) {
      return h("section", { class: "live none", "aria-label": "Live signals" }, d.live_none || "No signal is live.");
    }
    const games = new Set(live.map((s) => s.sport_key + " " + s.game_id)).size;
    const head = (live.length === 1 ? "1 signal is live" : fmtInt(live.length) + " signals are live") +
      (games !== live.length ? ", on " + fmtInt(games) + (games === 1 ? " game" : " games") : "");
    return h("section", { class: "live", "aria-label": "Live signals" },
      h("header", null, h("h2", null, head)),
      h("ul", { class: "rows" }, live.map((s) => h("li", null,
        badge(s.badge),
        h("span", null, h("span", { class: "tag" }, s.sport), h("a", { href: "#game/" + encodeURIComponent(s.game_id) }, s.matchup),
          h("div", { class: "faint" }, s.kickoff)),
        h("span", null, s.rule),
        h("span", null, h("strong", null, s.take), s.better ? h("div", { class: "faint" }, s.better) : ""),
        h("span", { class: "faint" }, s.until)))),
      h("p", { class: "note" }, d.live_note));
  }

  function drawHome(d) {
    const n = d.numbers || {};
    const tiles = h("div", { class: "tiles" },
      tile("Signals on the board", fmtInt(n.signals_live), "Games not yet kicked off with a Rule B or Rule HT signal, each counted once. " +
        (n.leans_live ? "Model leans, which are watches, not signals: " + fmtInt(n.leans_live) + "."
          : "Model leans are watches and aren’t counted.")),
      tile("Games on the board", fmtInt(n.games_on_board), "Not yet kicked off, as the board lists them"),
      tile("Next run", n.next_run, n.next_run_day ? "Both alert jobs, " + n.next_run_day : ""),
      tile("Credits left", n.credits === null || n.credits === undefined ? "Not known" : fmtInt(n.credits),
        n.credits_read ? "As the Odds API reported it at " + n.credits_read : "No reading yet"));

    const tests = panel("Forward tests", h("a", { href: "#tests" }, "Details"),
      h("ul", { class: "rows" }, (d.tests || []).map((t) => h("li", null,
        h("div", { class: "row-top" }, h("span", { class: "name" }, t.name), h("span", null, t.progress)),
        h("div", { class: "faint" }, t.decisions && t.decisions.length ? t.decisions[0].text + " " : "", t.money_gate)))));

    const jobs = panel("Scheduled jobs", h("a", { href: "#jobs" }, "Records"),
      h("ul", { class: "rows" }, (d.jobs || []).map((j) => h("li", null,
        h("div", { class: "row-top" }, h("span", { class: "status" }, dot(j.level), h("span", { class: "name" }, j.name)),
          h("span", null, (j.last_run_label || "Last run") + " " + j.last_run)),
        h("div", { class: "faint" }, j.result)))));

    const waiting = panel("Your decisions", null,
      (d.waiting || []).length ? h("ul", { class: "rows" }, d.waiting.map((w) => {
        const det = h("details", { class: "item", open: state.openWaiting.has(w.n) },
          h("summary", null, h("span", { class: "n" }, w.n + "."), h("span", { class: "t" }, w.title),
            w.due ? h("span", { class: "due status" }, dot(w.due_level), w.due) : ""),
          h("p", null, w.detail || w.first_sentence));
        det.addEventListener("toggle", () => { if (det.open) state.openWaiting.add(w.n); else state.openWaiting.delete(w.n); });
        return h("li", null, det);
      })) : h("p", { class: "muted" }, "No owner decisions are listed in this status snapshot."));

    const ev = panel("Research progress", h("a", { href: "#research" }, "All " + (d.evidence_total || 0) + " results"),
      h("p", { class: "muted" }, "Historical findings and forward tests remain separate. Downloaded data is not automatically ready for analysis."),
      variantsLine(d.variants, d.bar));

    const attention = (d.jobs || []).filter((j) => j.level !== "ok");
    const needs = panel("Needs attention", h("a", { href: "#jobs" }, "Job details"),
      attention.length ? h("ul", { class: "rows" }, attention.map((j) => h("li", null,
        h("strong", null, j.name), h("div", { class: "faint" }, j.result)))) :
        h("p", { class: "muted" }, "No job exceptions reported in this snapshot."));
    return h("div", null, h("div", { class: "grid2" }, needs, waiting),
      downloadPanel(d.operations || {}, true), livePanel(d), tiles,
      h("div", { class: "grid2" }, tests, ev), sourcePanel(d.sources || []),
      h("details", null, h("summary", null, "All scheduled jobs"), jobs));
  }

  function variantsLine(n, bar) {
    if (!n) return h("p", { class: "bar-note" }, "The running count of variants could not be read from STATUS.md.");
    return h("p", { class: "bar-note" }, fmtInt(n) + " variants recorded in the local status source; its reported bar is p < " + bar +
      " (0.05 / " + fmtInt(n) + ") to clear the multiple-testing bar.");
  }

  function evidenceRow(e) {
    const figs = [];
    if (e.record) figs.push(h("span", null, "Record " + e.record));
    if (e.win_rate) figs.push(h("span", null, e.win_rate));
    figs.push(h("span", null, e.n_words));
    if (e.p_value) figs.push(h("span", null, e.p_value));
    return h("li", null,
      h("div", { class: "name" }, e.title, e.kind ? h("span", { class: "kind" }, e.kind) : ""),
      h("div", null, e.result),
      h("div", { class: "ev-figs" }, figs),
      h("div", { class: "ev-bar" + (e.clears_bar ? " clears" : "") }, e.bar_sentence));
  }

  // ------------------------------------------------------------------ board
  function drawBoard(d) {
    const games = (d.games || []).filter((g) => (state.board.sport === "all" || g.sport_key === state.board.sport)
      && (!state.board.signals || g.signal));
    function setFilter(sport, signals) {
      const p = new URLSearchParams();
      if (sport !== "all") p.set("sport", sport);
      if (signals) p.set("signals", "1");
      const q = p.toString();
      location.hash = "board" + (q ? "?" + q : "");
    }
    const seg = h("div", { class: "seg", role: "group", "aria-label": "Sport" },
      [["all", "All"], ["nfl", "NFL"], ["cfb", "College football"]].map(([k, label]) =>
        h("button", { type: "button", "aria-pressed": String(state.board.sport === k),
          onclick: () => setFilter(k, state.board.signals) }, label)));
    const box = h("input", { type: "checkbox", checked: state.board.signals,
      onchange: (ev) => setFilter(state.board.sport, ev.target.checked) });
    const runs = d.runs || {};
    const summary = h("span", { class: "muted" }, fmtInt((d.games || []).length) + " games not yet kicked off, " +
      fmtInt(d.signals || 0) + " signalling. Latest runs: " +
      Object.values(runs).map((r) => r.sport + " " + r.latest_run).join(", ") + ".");
    const filters = h("div", { class: "filters" }, seg, h("label", { class: "check" }, box, "Signals only"), summary);

    if (!(d.games || []).length) {
      return h("div", null, h("h1", null, "Board"), filters,
        h("p", { class: "muted" }, "No game in the latest runs is still to kick off."));
    }
    function boardTable(list) {
      return h("div", { class: "tablewrap" }, h("table", null,
        cols(["13%", "16%", "10%", "13%", "9%", "9%", "17%", "13%"]),
        h("thead", null, h("tr", null, ["Kickoff (ET)", "Matchup", "Forecast", "Total and under", "Wind rule’s value", "Lean model’s chance of the under", "Rules", "Best number"].map((t) => h("th", { scope: "col" }, t)))),
        h("tbody", null, list.map((g) => {
          const tr = h("tr", { class: "clickable" + (g.signal ? " signal" : "") },
            h("td", { class: "stack" }, g.time_set === false ? [h("div", null, g.kick_day), h("div", null, g.time_note || "Time not set")] : h("div", null, g.kickoff),
              h("div", { class: "faint" }, daysWords(g.days))),
            h("td", null, h("span", { class: "tag" }, g.sport), h("a", { href: "#game/" + encodeURIComponent(g.game_id) }, g.matchup)),
            h("td", null, g.forecast),
            h("td", { class: "stack" }, g.total ? h("div", null, g.total + (g.under ? ", under " + g.under : "")) : h("div", { class: "faint" }, "No price"),
              g.source ? h("div", { class: "faint" }, g.source) : ""),
            windValueCell(g),
            leanChanceCell(g),
            h("td", { class: "stack small rulecell" }, g.rules.map(ruleLine)),
            h("td", null, g.best || h("span", { class: "faint" }, "Not logged")));
          tr.addEventListener("click", (ev) => { if (ev.target.tagName !== "A") location.hash = "game/" + encodeURIComponent(g.game_id); });
          return tr;
        }))));
    }
    const sig = games.filter((g) => g.signal), rest = games.filter((g) => !g.signal);
    const out = h("div", null, h("h1", null, "Board"), filters, legend(),
      h("h2", { class: "group" }, "Signals", h("span", { class: "count" }, fmtInt(sig.length))),
      sig.length ? boardTable(sig) : h("p", { class: "muted" }, "No game on the board is signalling."));
    if (!state.board.signals) {
      out.append(h("h2", { class: "group" }, "Everything else", h("span", { class: "count" }, fmtInt(rest.length))),
        rest.length ? boardTable(rest) : h("p", { class: "muted" }, "No other game is on the board."));
    }
    out.append(
      h("p", { class: "faint" }, windValueWords(d.wind_rule_bar) + " Lean model’s chance of the under is the NFL lean model’s own estimate, for outdoor NFL games only. Neither is a proven edge."),
      h("p", { class: "faint" }, "A signal is the rule firing on a pre-registered paper test, not a proven bet. Kickoffs are Eastern time, as the ledgers give them. A game whose kickoff time is not set stays on the board through the end of its date, Eastern time, with the last row logged for it."));
    return out;
  }

  // What the wind rule's value is and when it is shown; the server says, from the evidence list, whether Rule B
  // clears the project's bar.
  function windValueWords(bar) {
    return "Wind rule’s value is Rule B’s expected value for the under, from the rule’s registered pricing model. It is shown only when the wind rule has signalled, or when the value is not above zero, which is why it did not signal." +
      (bar ? " " + bar : "");
  }

  // Rule B's value, and the lean model's chance, each in its own cell and never side by side in one: a dash where
  // the server sends nothing (no wind rule signal; not an outdoor NFL game). The Rules column says why.
  function dash(why) {
    return h("span", { class: "faint", title: why }, "—");
  }
  function windValueCell(g) {
    if (!g.wind_value) return h("td", null, dash(g.wind_rule_met ? "Shown only when the wind rule signals; the Rules column says why it did not" : "The wind trigger was not met"));
    return h("td", { class: "stack" }, h("div", null, g.wind_value),
      g.wind_value_best ? h("div", { class: "faint" }, g.wind_value_best + " at the best number") : "");
  }
  function leanChanceCell(g) {
    return h("td", null, g.lean_chance || dash("Only for outdoor NFL games"));
  }

  // ------------------------------------------------------------------ game
  function niceStep(span) {
    const raw = span / 3;
    const p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * p) return m * p;
    return 10 * p;
  }

  function drawChart(host, title, unit, points, digits) {
    const wrap = h("div", { class: "panel chart" }, h("header", null, h("h2", null, title)));
    const body = h("div", { class: "body" });
    wrap.append(body);
    host.append(wrap);
    if (!points.length) {
      body.append(h("p", { class: "muted" }, "Nothing logged for this yet."));
      return;
    }
    const W = Math.max(280, body.clientWidth || 520), H = 190;
    const m = { l: 40, r: 60, t: 12, b: 26 };
    const ts = points.map((p) => Date.parse(p[0]));
    const vs = points.map((p) => p[1]);
    let lo = Math.min(...vs), hi = Math.max(...vs);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const x = (t) => (t1 === t0 ? m.l + (W - m.l - m.r) / 2 : m.l + ((t - t0) / (t1 - t0)) * (W - m.l - m.r));
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    body.insertAdjacentHTML("beforeend", "<svg></svg>");
    const svg = body.querySelector("svg");
    const NS = svg.namespaceURI;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", title + ": " + points.length + " readings, latest " + vs[vs.length - 1].toFixed(digits) + unit);
    const el = (tag, attrs, text) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
      if (text !== undefined) e.textContent = text;
      svg.append(e);
      return e;
    };
    for (let v = lo; v <= hi + 1e-9; v += step) {
      el("line", { class: "axis", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) });
      el("text", { class: "tick", x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, (Math.round(v * 10) / 10).toString());
    }
    el("text", { class: "tick", x: m.l, y: H - 6, "text-anchor": "start" }, points[0][2]);
    if (points.length > 1) el("text", { class: "tick", x: W - m.r, y: H - 6, "text-anchor": "end" }, points[points.length - 1][2]);
    if (points.length > 1) {
      el("path", { class: "series", d: points.map((p, i) => (i ? "L" : "M") + x(ts[i]).toFixed(1) + "," + y(p[1]).toFixed(1)).join(" ") });
    }
    const lx = x(ts[ts.length - 1]), ly = y(vs[vs.length - 1]);
    el("circle", { class: "end", cx: lx, cy: ly, r: 4 });
    el("text", { class: "endlabel", x: lx + 8, y: ly + 4 }, vs[vs.length - 1].toFixed(digits) + unit);
    const cross = el("line", { class: "cross", x1: 0, x2: 0, y1: m.t, y2: H - m.b, visibility: "hidden" });
    const hot = el("circle", { class: "hot", cx: 0, cy: 0, r: 4, visibility: "hidden" });
    const tip = h("div", { class: "tip", hidden: true });
    body.style.position = "relative";
    body.append(tip);
    const hit = el("rect", { x: m.l - 10, y: 0, width: W - m.l - m.r + 20, height: H, fill: "transparent" });
    function show(evt) {
      const box = svg.getBoundingClientRect();
      const px = ((evt.clientX - box.left) / box.width) * W;
      let best = 0;
      for (let i = 1; i < ts.length; i++) if (Math.abs(x(ts[i]) - px) < Math.abs(x(ts[best]) - px)) best = i;
      const cx = x(ts[best]), cy = y(vs[best]);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      hot.setAttribute("cx", cx); hot.setAttribute("cy", cy); hot.setAttribute("visibility", "visible");
      tip.replaceChildren(h("b", null, vs[best].toFixed(digits) + unit), points[best][2]);
      tip.hidden = false;
      const left = (cx / W) * box.width;
      tip.style.left = Math.min(Math.max(0, left - 60), box.width - 150) + "px";
      tip.style.top = Math.max(0, (cy / H) * box.height - 52) + "px";
    }
    function hide() { cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden"); tip.hidden = true; }
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerleave", hide);
  }

  function drawGame(d) {
    if (!d.game) return h("div", null, h("a", { class: "back", href: "#board" }, "← Back to the board"));
    const g = d.game;
    const out = h("div", null, h("a", { class: "back", href: "#board" }, "← Back to the board"),
      h("h1", null, g.matchup),
      h("p", { class: "lede" }, [g.sport, g.kickoff, g.venue].filter(Boolean).join(" · ") + " · game " + g.game_id),
      g.badge ? h("p", null, badge(g.badge), " " + (g.badge_words || "")) : "");
    const charts = h("div", { class: "charts" });
    out.append(charts);
    main.replaceChildren(out);                        // so the charts can measure their width
    drawChart(charts, "Total over time", "", d.charts.total, 1);
    drawChart(charts, "Forecast wind over time", " mph", d.charts.wind, 0);

    const closes = d.closes || [];
    out.append(panel("Closing lines captured", null, closes.length ? h("table", null,
      h("thead", null, h("tr", null, ["Captured", "Book", "Total", "Under", "Over"].map((t) => h("th", null, t)))),
      h("tbody", null, closes.map((c) => h("tr", null, h("td", null, c.captured), h("td", null, c.book),
        h("td", null, c.total), h("td", null, c.under), h("td", null, c.over)))))
      : h("p", { class: "muted" }, "No closing line has been captured for this game yet. Close capture records it 2 to 20 minutes before kickoff.")));

    const a = d.alerts || {};
    out.append(panel("What was alerted", null,
      a.note ? h("p", { class: "muted" }, a.note) : "",
      (a.sent || []).length ? h("ul", { class: "rows" }, a.sent.map((s) => h("li", null, h("div", { class: "name" }, s.words),
        s.first_seen ? h("div", { class: "faint" }, s.first_seen) : ""))) : h("p", { class: "muted" }, "No alert has been sent for this game."),
      (a.log_lines || []).length ? h("div", null, h("h3", null, "The alert log’s lines for this game"),
        h("p", { class: "muted" }, "These are the alert job’s own words, copied as it logged them. A watch is not a bet, and a signal is a paper entry for the forward test, not a proven bet."),
        h("p", { class: "faint" }, "The alert log doesn’t stamp each alert with a time. Where the ledger shows when an alert’s condition was first logged, that time is shown above."),
        h("pre", null, a.log_lines.join("\n"))) : ""));

    if ((d.fills || []).length) {
      out.append(panel("Paper fills logged", null, h("table", null,
        h("thead", null, h("tr", null, ["When", "Rule", "Total", "Price", "Book"].map((t) => h("th", null, t)))),
        h("tbody", null, d.fills.map((f) => h("tr", null, h("td", null, f.when), h("td", null, f.rule), h("td", null, f.line),
          h("td", null, f.price), h("td", null, f.book)))))));
    }

    const rows = d.rows || [];
    out.append(panel("Every logged row, oldest first", null, h("table", null,
      cols(["14%", "7%", "10%", "13%", "9%", "9%", "22%", "16%"]),
      h("thead", null, h("tr", null, ["Logged", "Days out", "Forecast", "Total and under", "Wind rule’s value", "Lean model’s chance of the under", "Rules", "Best number"].map((t) => h("th", null, t)))),
      h("tbody", null, rows.map((r) => h("tr", { class: r.signal ? "signal" : "" },
        h("td", null, r.logged), h("td", { class: "num" }, r.lead_days),
        h("td", null, r.forecast),
        h("td", { class: "stack" }, h("div", null, r.total ? r.total + (r.under ? ", under " + r.under : "") : "No price"),
          r.source ? h("div", { class: "faint" }, r.source) : ""),
        windValueCell(r),
        leanChanceCell(r),
        h("td", { class: "stack small rulecell" }, r.rules.map(ruleLine)),
        h("td", null, r.best))))),
      h("p", { class: "faint" }, fmtInt(rows.length) + " rows. Each row is one scheduled or manual run. " + windValueWords(d.wind_rule_bar) + " The lean model’s chance is shown only for an outdoor NFL game. Neither is a proven edge.")));
    return out;
  }

  // ------------------------------------------------------------------ a small time chart, drawn by this page
  // Inline SVG, no library, nothing loaded. o = {
  //   name     what is plotted ("Cumulative units by date"); title: what it found, in plain words (the server writes
  //            it, with the sample size and whether it clears the multiple-testing bar in the caption);
  //   scope    which bets; caption: the sentence under it; empty: the sentence shown instead of a chart;
  //   points   [[time (ISO), value, label, second value?], ...] in time order;
  //   layers   "line" (a line through the values) or "dots+mean" (a dot per value, a line through the second values);
  //   refs     [{y, label}]: reference lines such as break-even, always inside the axis;
  //   minSpan  the axis never spans less than this, so a small difference never fills the chart;
  //   floorAtMost  the axis starts no higher than this (a win-rate chart passes 40, with break-even as a ref);
  //   fmt      how a value is written; keys: [[class, words]] under the chart when it has two series }.
  function timeChart(host, o) {
    const head = h("h2", null, o.title || o.name,
      h("span", { class: "scope" }, (o.title ? o.name + (o.scope ? " · " : "") : "") + (o.scope || "")));
    const wrap = h("div", { class: "panel chart" }, h("header", null, head));
    const body = h("div", { class: "body" });
    wrap.append(body);
    host.append(wrap);
    const points = o.points || [];
    if (points.length < 2) {
      body.append(h("p", { class: "muted" }, o.empty || "Nothing to chart yet."));
      return wrap;
    }
    const fmt = o.fmt || ((v) => (Math.round(v * 100) / 100).toString());
    const W = Math.max(280, body.clientWidth || 520), H = 200;
    const m = { l: 44, r: 76, t: 12, b: 26 };
    const ts = points.map((p) => Date.parse(p[0]));
    const vs = points.map((p) => p[1]);
    const v2 = o.layers === "dots+mean" ? points.map((p) => p[3]) : [];
    const refs = o.refs || [];
    let lo = Math.min(...vs, ...v2, ...refs.map((r) => r.y)), hi = Math.max(...vs, ...v2, ...refs.map((r) => r.y));
    if (o.minSpan && hi - lo < o.minSpan) { const mid = (hi + lo) / 2; lo = mid - o.minSpan / 2; hi = mid + o.minSpan / 2; }
    if (o.floorAtMost !== undefined) lo = Math.min(lo, o.floorAtMost);
    const step = niceStep(hi - lo);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const t0 = Math.min(...ts), t1 = Math.max(...ts);
    const x = (t) => (t1 === t0 ? m.l + (W - m.l - m.r) / 2 : m.l + ((t - t0) / (t1 - t0)) * (W - m.l - m.r));
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    body.insertAdjacentHTML("beforeend", "<svg></svg>");
    const svg = body.querySelector("svg");
    const NS = svg.namespaceURI;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", (o.title || o.name) + ". " + points.length + " points.");
    const el = (tag, attrs, text) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
      if (text !== undefined) e.textContent = text;
      svg.append(e);
      return e;
    };
    for (let v = lo; v <= hi + 1e-9; v += step) {
      el("line", { class: "axis", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) });
      el("text", { class: "tick", x: m.l - 6, y: y(v) + 4, "text-anchor": "end" }, fmt(Math.round(v * 1e6) / 1e6));
    }
    for (const r of refs) {
      el("line", { class: "ref", x1: m.l, x2: W - m.r, y1: y(r.y), y2: y(r.y) });
      el("text", { class: "reflabel", x: W - m.r + 6, y: y(r.y) + 4 }, r.label);
    }
    const day = (t) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" });
    el("text", { class: "tick", x: m.l, y: H - 6, "text-anchor": "start" }, day(ts[0]));
    el("text", { class: "tick", x: W - m.r, y: H - 6, "text-anchor": "end" }, day(ts[ts.length - 1]));
    const line = (vals) => vals.map((v, i) => (i ? "L" : "M") + x(ts[i]).toFixed(1) + "," + y(v).toFixed(1)).join(" ");
    let endV;
    if (o.layers === "dots+mean") {
      for (let i = 0; i < ts.length; i++) el("circle", { class: "dot", cx: x(ts[i]), cy: y(vs[i]), r: 4 });
      el("path", { class: "series", d: line(v2) });
      endV = v2[v2.length - 1];
    } else {
      el("path", { class: "series", d: line(vs) });
      endV = vs[vs.length - 1];
    }
    const lx = x(ts[ts.length - 1]), ly = y(endV);
    el("circle", { class: "end", cx: lx, cy: ly, r: 4 });
    const cross = el("line", { class: "cross", x1: 0, x2: 0, y1: m.t, y2: H - m.b, visibility: "hidden" });
    const hot = el("circle", { class: "hot", cx: 0, cy: 0, r: 4, visibility: "hidden" });
    const tip = h("div", { class: "tip", hidden: true });
    body.style.position = "relative";
    body.append(tip);
    const hit = el("rect", { x: m.l - 10, y: 0, width: W - m.l - m.r + 20, height: H, fill: "transparent" });
    hit.addEventListener("pointermove", (evt) => {
      const box = svg.getBoundingClientRect();
      const px = ((evt.clientX - box.left) / box.width) * W;
      let best = 0;
      for (let i = 1; i < ts.length; i++) if (Math.abs(x(ts[i]) - px) < Math.abs(x(ts[best]) - px)) best = i;
      const cx = x(ts[best]), cy = y(vs[best]);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      hot.setAttribute("cx", cx); hot.setAttribute("cy", cy); hot.setAttribute("visibility", "visible");
      tip.replaceChildren(h("b", null, fmt(vs[best]) + (o.unit || "")), points[best][2],
        o.layers === "dots+mean" ? h("div", null, "Running mean " + fmt(v2[best]) + (o.unit || "")) : "");
      tip.hidden = false;
      tip.style.left = Math.min(Math.max(0, (cx / W) * box.width - 60), box.width - 180) + "px";
      tip.style.top = Math.max(0, (cy / H) * box.height - 60) + "px";
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hot.setAttribute("visibility", "hidden"); tip.hidden = true; });
    if (o.keys) body.append(h("div", { class: "serieskey" }, o.keys.map(([cls, words]) => h("span", null, h("i", { class: cls }), words))));
    if (o.caption) body.append(h("p", { class: "caption" }, o.caption));
    return wrap;
  }

  // ------------------------------------------------------------------ signals: every bet the scorers count
  function signalCard(name, s, together, note) {
    return h("div", { class: "card" + (together ? " together" : "") },
      h("h3", null, name),
      h("p", null, s.sample + "."),
      s.settled ? h("div", { class: "figs" },
        h("span", null, "Record ", h("b", null, s.record)),
        h("span", null, "Units ", h("b", null, s.units)),
        h("span", null, "Return ", h("b", null, s.roi))) : "",
      s.settled ? h("p", null, s.record_words + (s.win_rate ? "; won " + s.win_rate : "") + ".") : "",
      s.settled ? h("p", null, s.bar_win) : "",
      s.clv ? h("p", null, s.clv) : "",
      s.interval ? h("p", null, s.interval) : "",
      s.bar_clv ? h("p", null, s.bar_clv) : "",
      h("p", null, s.toward),
      s.decision ? h("p", null, s.decision) : "",
      note ? h("p", null, note) : "",
      h("p", { class: "paper" }, s.paper));
  }

  function drawSignals(d) {
    const f = state.signals;
    const out = h("div", null, h("h1", null, "Signals"),
      h("p", { class: "lede" }, "Every bet the scorers count on the forward tests, newest first, with its entry, its close and its result. " + (d.paper || "")));
    for (const t of d.trouble || []) out.append(h("div", { class: "notes", role: "note" }, h("p", null, t)));
    const fallback = d.fallback || [];
    if (d.empty) {
      out.append(h("p", { class: "big-sentence" }, d.empty.text), h("p", { class: "muted" }, d.empty.next),
        legend(d.legend_live));
      return out;
    }
    const go = (sport, rule, result) => {
      const p = new URLSearchParams();
      if (sport !== "all") p.set("sport", sport);
      if (rule !== "all" && (sport === "all" || LOG_RULES[rule] === sport)) p.set("rule", rule);
      if (result !== "all") p.set("result", result);
      const q = p.toString();
      location.hash = "signals" + (q ? "?" + q : "");
    };
    const rules = d.rules || [];
    const seg = h("div", { class: "seg", role: "group", "aria-label": "Sport" },
      [["all", "All"], ["nfl", "NFL"], ["cfb", "College football"]].map(([k, label]) =>
        h("button", { type: "button", "aria-pressed": String(f.sport === k), onclick: () => go(k, f.rule, f.result) }, label)));
    const ruleSel = h("select", { "aria-label": "Rule", onchange: (ev) => go(f.sport, ev.target.value, f.result) },
      h("option", { value: "all", selected: f.rule === "all" }, "All rules"),
      rules.filter((r) => f.sport === "all" || r.sport_key === f.sport).map((r) =>
        h("option", { value: r.id, selected: f.rule === r.id }, r.name)));
    const resultSel = h("select", { "aria-label": "Result", onchange: (ev) => go(f.sport, f.rule, ev.target.value) },
      RESULTS.map(([k, label]) => h("option", { value: k, selected: f.result === k }, label)));
    out.append(h("div", { class: "filters" }, seg, h("label", { class: "check" }, "Rule", ruleSel),
      h("label", { class: "check" }, "Result", resultSel)), legend(d.legend_live));

    // the numbers: each rule shown, and the signal rules together
    const shown = rules.filter((r) => (f.rule === "all" ? f.sport === "all" || r.sport_key === f.sport : r.id === f.rule));
    const cards = h("div", { class: "cards" });
    const together = (d.together || {})[f.sport];
    if (f.rule === "all" && together) cards.append(signalCard(together.name, together.summary, true, together.note));
    for (const r of shown) {
      cards.append(r.summary ? signalCard(r.name, r.summary, false) :
        h("div", { class: "card" }, h("h3", null, r.name), h("p", null, "Its scorer could not be read, so there are no numbers.")));
    }
    out.append(cards, h("p", { class: "faint" }, d.totals_note));
    const chosen = f.rule === "all" ? together : shown[0];
    const chartsHost = h("div", { class: "charts" });
    out.append(chartsHost);

    // the log
    const bets = (d.bets || []).filter((b) => (f.sport === "all" || b.sport_key === f.sport)
      && (f.rule === "all" || b.rule === f.rule) && (f.result === "all" || b.result === f.result));
    out.append(h("h2", { class: "group" }, "The log", h("span", { class: "count" }, fmtInt(bets.length) + " of " + fmtInt((d.bets || []).length) + " bets")));
    if (bets.length) {
      out.append(h("div", { class: "tablewrap" }, h("table", null,
        cols(["12%", "12%", "13%", "15%", "12%", "7%", "7%", "13%", "9%"]),
        h("thead", null, h("tr", null, [["Date and kickoff (ET)", ""], ["Game", ""], ["Rule", ""], ["Entry", ""], ["Close", ""],
          ["Closing-line value (points)", "num"], ["Final total", "num"], ["Result", ""], ["Units", "num"]].map(([t, cl]) => h("th", { scope: "col", class: cl || null }, t)))),
        h("tbody", null, bets.map((b) => {
          const tr = h("tr", { class: (b.game_id ? "clickable" : "") + (b.live ? " signal" : "") },
            h("td", null, b.kickoff),
            h("td", null, h("span", { class: "tag" }, b.sport), b.game_id ? h("a", { href: "#game/" + encodeURIComponent(b.game_id) }, b.matchup) : b.matchup),
            h("td", { class: "rulecell small" }, h("div", null, b.rule_name, b.rule_kind === "watch" ? badge("watch") : "",
              b.live ? badge(b.badge) : "")),
            h("td", { class: "stack" }, h("div", null, b.entry), h("div", { class: "faint" }, b.entry_source), b.logged ? h("div", { class: "faint" }, b.logged) : ""),
            h("td", { class: "stack" }, b.close ? [h("div", null, b.close), h("div", { class: "faint" }, b.close_source)] : h("span", { class: "faint" }, b.result === "pending" ? "Not closed yet" : b.result === "void" ? "Not graded" : "No close logged")),
            h("td", { class: "num" }, b.clv || dash(b.rule === "cfb_rule_ht" ? "Rule HT is graded on its results, not on closing-line value" : "No closing-line value")),
            h("td", { class: "num" }, b.final_total || dash("No final score yet")),
            h("td", { class: "stack" }, h("div", null, resultBadge(b.result, b.result_words)), b.void_reason ? h("div", { class: "faint" }, b.void_reason) : ""),
            h("td", { class: "num" }, b.units || dash(b.result === "pending" ? "Waiting for a result" : "Not graded")));
          if (b.game_id) tr.addEventListener("click", (ev) => { if (ev.target.tagName !== "A") location.hash = "game/" + encodeURIComponent(b.game_id); });
          return tr;
        })))));
    } else {
      out.append(h("p", { class: "muted" }, (d.bets || []).length ? "No bet matches this choice." : "No bet has been counted yet."));
    }
    if (fallback.length) {
      out.append(h("h2", { class: "group" }, "Games that signalled, from the ledgers", h("span", { class: "count" }, fmtInt(fallback.length))),
        h("p", { class: "muted" }, d.fallback_note),
        h("div", { class: "tablewrap" }, h("table", null,
          h("thead", null, h("tr", null, ["Date and kickoff (ET)", "Game", "Rule", "First signal logged", "Result"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", null, fallback.filter((b) => (f.sport === "all" || b.sport_key === f.sport) && (f.rule === "all" || b.rule === f.rule)).map((b) =>
            h("tr", null, h("td", null, b.kickoff),
              h("td", null, h("span", { class: "tag" }, b.sport), h("a", { href: "#game/" + encodeURIComponent(b.game_id) }, b.matchup)),
              h("td", { class: "rulecell small" }, h("div", null, b.rule_name, b.rule_kind === "watch" ? badge("watch") : "")),
              h("td", { class: "stack" }, h("div", null, b.entry), h("div", { class: "faint" }, b.entry_source + ". " + b.logged)),
              h("td", { class: "faint" }, "Not known: only the scorer grades")))))));
    }

    // the two charts, drawn once the page is in place (so they can measure their width)
    main.replaceChildren(out);
    const c = (chosen && chosen.charts) || {};
    const scope = chosen ? chosen.name : "";
    const u = c.units || {}, v = c.clv || {};
    timeChart(chartsHost, { name: "Cumulative units by date", title: u.title, scope, caption: u.caption, empty: u.empty,
      points: u.points, layers: "line", refs: [{ y: 0, label: "Break-even" }], minSpan: 4, unit: " units",
      fmt: signedNum });
    timeChart(chartsHost, { name: "Closing-line value per bet", title: v.title, scope, caption: v.caption, empty: v.empty,
      points: v.points, layers: "dots+mean", refs: [{ y: 0, label: "Zero" }], minSpan: 4, unit: " points",
      fmt: signedNum,
      keys: [["dotkey", "Each bet"], ["", "Running mean"]] });
    return out;
  }

  // ------------------------------------------------------------------ forward tests
  function drawTests(d) {
    const out = h("div", null, h("h1", null, "Forward tests"),
      h("p", { class: "lede" }, "Paper only. The counts below come from the ledgers as logged; the scorers decide what counts. A scorer’s interim read decides nothing, and each decision is written down once, at its horizon."));
    for (const grp of d.groups || []) {
      const sec = h("section", { class: "panel" }, h("header", null, h("h2", null, grp.sport)));
      for (const t of grp.tests) {
        const c = t.counts || {};
        const sigBits = (c.signals_by_status || []).map((s) => s.words + " " + fmtInt(s.games)).join(", ");
        sec.append(h("div", { class: "test" },
          h("h3", null, t.name),
          t.rule ? h("p", null, t.rule) : "",
          h("dl", { class: "facts" },
            h("dt", null, "Starts"), h("dd", null, t.starts || "Not written"),
            h("dt", null, "Decided"), h("dd", null, t.decided || "Not written"),
            h("dt", null, "So far"), h("dd", null, t.progress_detail || t.progress),
            h("dt", null, "Money gate"), h("dd", null, t.money_gate_value)),
          (t.decisions || []).map((x) => h("p", { class: "name" }, x.text)),
          h("div", { class: "counts" },
            h("span", null, "Games logged with a kickoff since the start: " + fmtInt(c.games_logged ?? 0)),
            h("span", null, "Games that signalled: " + fmtInt(c.signals ?? 0) + (sigBits ? " (" + sigBits + ")" : ""))),
          (c.by_latest_status || []).length ? h("div", { class: "counts" }, h("span", null, "Latest status of each game: " +
            c.by_latest_status.map((s) => s.words + " " + fmtInt(s.games)).join(", ") + ".")) : "",
          t.note ? h("p", { class: "faint" }, t.note) : ""));
      }
      const s = grp.scorer || {};
      sec.append(h("div", { class: "scorer" },
        h("h3", null, "The scorer’s read, as printed"),
        s.words ? h("p", { class: "muted" }, s.words) : "",
        s.ran ? h("p", { class: "faint" }, "Run as a preview (with --now) at " + s.ran + ". A preview never records a decision.") : "",
        s.text ? h("pre", null, s.text.replace(/\s+$/, "")) : (s.status === "ok" ? h("p", { class: "muted" }, "It printed nothing.") : ""),
        s.error ? h("details", null, h("summary", { class: "faint" }, s.error_label || "What it printed as an error"), h("pre", null, s.error)) : ""));
      out.append(sec);
    }
    out.append(variantsLine(d.variants, d.bar));
    return out;
  }

  // ------------------------------------------------------------------ jobs and records
  function drawJobs(d) {
    const out = h("div", null, h("h1", null, "Jobs and records"),
      h("p", { class: "lede" }, "The four scheduled jobs, the alert runs’ own records, the credit balance and the closing lines captured. ",
        h("a", { href: "#jobs/records" }, "How to read these records (ops/RUN_RECORDS.md)"), "."));
    const jobs = d.jobs || [];
    out.append(panel("Scheduled jobs", null, d.launchctl_note ? h("p", { class: "muted" }, d.launchctl_note) : "",
      h("table", null,
        cols(["20%", "22%", "16%", "14%", "28%"]),
        h("thead", null, h("tr", null, ["Job", "Schedule", "Last run", "Last exit", "Result"].map((t) => h("th", null, t)))),
        h("tbody", null, jobs.map((j) => h("tr", null,
          h("td", null, h("span", { class: "status" }, dot(j.level), h("span", { class: "name" }, j.name)),
            h("div", { class: "faint" }, j.running ? "Running now" : j.loaded === false ? "Not loaded" : "")),
          h("td", null, j.schedule),
          h("td", { class: "stack" }, h("div", null, j.last_run), j.last_run_note ? h("div", { class: "faint" }, j.last_run_note) : ""),
          h("td", null, j.exit_words),
          h("td", { class: "stack" }, h("div", null, j.result), j.log_line ? h("div", { class: "faint" }, "Its log’s last line: " + j.log_line) : "")))))));

    const c = d.credits;
    out.append(panel("Odds API credits", null, c ? h("div", null, h("p", { class: "big-sentence" }, c.text + "."),
      c.plan_words ? h("p", { class: "muted" }, c.plan_words + ".") : "", c.stale ? h("p", { class: "muted" }, c.stale) : "")
      : h("p", { class: "muted" }, d.credits_note || "No credit reading yet.")));

    for (const [project, r] of Object.entries(d.runs || {})) {
      out.append(panel(r.sport + " alert runs", null,
        r.note ? h("p", { class: "muted" }, r.note) : "",
        r.rows.length ? h("table", null,
          cols(["19%", "8%", "8%", "8%", "8%", "10%", "39%"]),
          h("thead", null, h("tr", null, [["When", ""], ["Result", ""], ["Games", "num"], ["Signals", "num"], ["Priced", "num"],
            ["At the rule’s book", "num"], ["Note", ""]].map(([t, cl]) => h("th", { class: cl || null }, t)))),
          h("tbody", null, r.rows.map((x) => h("tr", null, h("td", null, x.when),
            h("td", null, x.failed ? h("span", { class: "status" }, dot("fail"), "Failed") : x.result),
            h("td", { class: "num" }, x.games), h("td", { class: "num" }, x.signals), h("td", { class: "num" }, x.priced),
            h("td", { class: "num" }, x.rule_priced === "" ? "not recorded" : x.rule_priced),
            h("td", { class: "small" }, [x.error, x.unmapped ? "Unmatched team names: " + x.unmapped : ""].filter(Boolean).join(" · ")))))) : "",
        h("p", { class: "faint" }, "Showing the last " + fmtInt(r.rows.length) + " of " + fmtInt(r.total) + " runs, newest first. If “at the rule’s book” is 0, the odds service was down or out of credits.")));
    }

    const closes = d.closes || [];
    out.append(panel("Closing lines captured in the last 7 days", null, closes.length ? h("table", null,
      h("thead", null, h("tr", null, ["Game", "Kickoff (ET)", "Captured", "Books", "Closing line"].map((t) => h("th", null, t)))),
      h("tbody", null, closes.map((x) => h("tr", null, h("td", null, h("span", { class: "tag" }, x.sport), x.matchup),
        h("td", null, x.kickoff), h("td", null, x.captured), h("td", { class: "num" }, x.books), h("td", null, x.line)))))
      : h("p", { class: "muted" }, "No closing line was captured in the last 7 days.")));
    return out;
  }

  function drawRecords(d) {
    return h("div", null, h("a", { class: "back", href: "#jobs" }, "← Back to jobs and records"),
      h("h1", null, "How to read the run records"),
      h("p", { class: "faint" }, "ops/RUN_RECORDS.md, shown as plain text."),
      d.text ? h("pre", { class: "plain" }, d.text) : h("p", { class: "muted" }, "The file could not be read."));
  }

  // ------------------------------------------------------------------ Thursday's pull
  function sourcePanel(sources) {
    return panel("Source freshness", null, h("p", { class: "muted" },
      "Page refresh is not a data update. Old completed journals can be valid historical records; dates show when evidence last changed."),
      h("ul", { class: "rows" }, sources.map((s) => h("li", null,
        h("div", { class: "row-top" }, h("strong", null, s.name), h("span", { class: "tag" }, s.state)),
        h("div", { class: "faint" }, s.kind + ": " + s.at + ". " + s.note)))));
  }

  function downloadPanel(op, compact) {
    const total = op.total;
    const box = panel("Download progress", compact ? h("a", { href: "#downloads" }, "All downloads") : null,
      h("p", { class: "muted" }, "Reported from local acquisition journals. Completed responses are not verified usable pairs, settled bets or permission to analyze."));
    if (total) box.append(h("div", { class: "tiles" },
      tile("Recorded attempts", fmtInt(total.requests), "Unique across readable journals; excludes cache reuse"),
      tile("Completed responses", fmtInt(total.completed), fmtInt(total.missing) + " explicitly missing; " + fmtInt(total.pending) + " pending"),
      tile("Recorded charges", fmtInt(total.billed), total.unknown_bill ? fmtInt(total.unknown_bill) + (total.unknown_bill === 1 ? " attempt has" : " attempts have") + " unknown billing; this is a subtotal" : "Acquisition attempts only; excludes probe and live/other usage")));
    else box.append(h("p", { class: "muted" }, "Acquisition total unavailable. Missing or inconsistent records are not zero downloads."));
    const batches = compact ? (op.batches || []).slice(0, 3) : (op.batches || []);
    box.append(h("ul", { class: "rows" }, batches.map((b) => h("li", null,
      h("div", { class: "row-top" }, h("strong", null, b.name), h("span", { class: "tag" }, b.state)),
      h("div", null, fmtInt(b.completed) + " completed · " + fmtInt(b.missing) + " missing · " + fmtInt(b.pending) + " pending · " + fmtInt(b.billed) + " recorded credits"),
      h("div", { class: "faint" }, "Updated " + b.updated + (b.unknown_bill ? " · Some billing unknown" : "")),
      compact ? "" : h("details", null, h("summary", null, "Record details"),
        h("p", { class: "faint" }, "Batch " + b.root + ". Recorded state: " + b.recorded_state +
          ". Reservations: " + fmtInt(b.reserved) + " credits (not extra billed charges). Reconciled batches are retained history; a successor may have finished."))))));
    for (const note of op.notes || []) box.append(h("p", { class: "note" }, note));
    return box;
  }

  function drawPull(d) {
    const op = d.operations || {};
    const out = h("div", null, h("h1", null, "Downloads"), downloadPanel(op, false));
    out.append(panel("Plan and usable coverage", op.queue_url ? h("a", { href: op.queue_url, target: "_blank", rel: "noopener" }, "Canonical queue") : null,
      h("p", { class: "muted" }, "Document snapshot, not live execution or paid authority. Planned caps are not spending. A newer local journal may supersede a queued item; verify the source date. Coverage notes below are reported plan text, not recalculated eligibility."),
      (op.queue || []).length ? h("ul", { class: "rows" }, op.queue.map((q) => h("li", null,
        h("div", { class: "row-top" }, h("strong", null, q.name), h("span", { class: "tag" }, q.state + " · " + q.order)),
        h("div", null, "Maximum new credits: " + q.cap), h("div", { class: "faint" }, q.detail)))) :
        h("p", { class: "muted" }, "The canonical queue could not be read; queued work is unknown.")));
    out.append(sourcePanel(d.sources || []), h("details", null, h("summary", null, "Legacy request log (separate scope)"), drawLegacyPull(d)));
    return out;
  }

  function drawLegacyPull(d) {
    const out = h("div", null, h("h1", null, "Legacy request log"));
    if (!d.started) {
      out.append(h("p", { class: "big-sentence" }, d.text));
      out.append(h("p", { class: "muted" }, "This older log does not include the acquisition journals above. Its totals must not be added to those journals."));
      return out;
    }
    const t = d.total || {};
    const row = (p, total) => h("tr", null, h("td", { class: total ? "name" : "" }, total ? "Total" : p.name),
      h("td", { class: "num" }, fmtInt(p.requests)), h("td", { class: "num" }, fmtInt(p.billed)),
      h("td", { class: "num" }, fmtInt(p.upper)), h("td", { class: "num" }, p.lowest === null || p.lowest === undefined ? "not read" : fmtInt(p.lowest)));
    out.append(h("div", { class: "tablewrap" }, h("table", null,
      h("thead", null, h("tr", null, [["Pull", ""], ["Requests", "num"], ["Credits billed", "num"], ["Upper bound", "num"], ["Lowest balance seen", "num"]]
        .map(([x, cl]) => h("th", { class: cl || null }, x)))),
      h("tbody", null, (d.pulls || []).map((p) => row(p, false)), row(t, true)))));
    if (t.unreadable) {
      out.append(h("p", { class: "muted" }, fmtInt(t.unreadable) + " request" + (t.unreadable === 1 ? "" : "s") +
        " came back without a readable bill; each is counted at its upper bound."));
    }
    return out;
  }

  // ------------------------------------------------------------------ research
  function drawResearch(d) {
    return h("div", null, h("h1", null, "Research"),
      h("p", { class: "lede" }, "Every result written in the repo’s files, with its sample size and whether it clears the multiple-testing bar in force when it was measured. A result that clears the bar is a candidate for a forward test, not a proven bet."),
      variantsLine(d.variants, d.bar),
      (d.entries || []).length ? h("section", { class: "panel" }, h("div", { class: "body" }, h("ul", { class: "rows" }, d.entries.map((e) => {
        const li = evidenceRow(e);
        li.append(h("div", { class: "faint" }, [e.sport, e.date, "Source: " + e.source].filter(Boolean).join(" · ")));
        if (e.note) li.append(h("div", { class: "faint" }, e.note));
        return li;
      })))) : h("p", { class: "muted" }, "The evidence list is empty or could not be read."));
  }

  // ------------------------------------------------------------------ backtests: the research as charts
  // Every chart is drawn here as inline SVG from the numbers the server sends (prepared from committed tables by
  // dashboard/tools/build_charts.py; nothing is loaded). Two layouts: "columns" (seasons, wind bands, totals or dates
  // across, a value up) and "rows" (one row per case, a value across). The axis rules: a win-rate axis starts at 40% or
  // lower and draws break-even (52.4% at −110); a value axis marked "zero" always includes zero, so a small difference
  // never fills the chart; an axis with a fixed min or max keeps it. Hover shows the exact numbers, and each chart has
  // a table of the same numbers that opens beneath it.
  function pText(p) {
    if (p < 1e-6) return "below 0.000001";
    return p < 0.1 ? String(Number(p.toPrecision(3))) : p.toFixed(2);
  }
  // One rounding for every number a chart prints, the same as its table's (build_charts.py, fixed): half away from
  // zero on the number as the chart file writes it, so 2.05 is 2.1 in both (toFixed gives 2.0, from 2.05's binary
  // value). `a` is not negative; the caller adds the sign.
  function fixed(a, d) {
    const s = String(a);
    if (/e/i.test(s)) return a.toFixed(d);
    return Number(Math.round(Number(s + "e" + d)) + "e-" + d).toFixed(d);
  }
  function fmtV(v, ax, signed) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    if (ax.kind === "p") return pText(v);
    const s = fixed(Math.abs(v), ax.digits === undefined ? 1 : ax.digits);
    const zero = Number(s) === 0;
    return (v < 0 && !zero ? "−" : signed && v > 0 && !zero ? "+" : "") + s + (ax.unit || "");
  }
  function tickText(v, ax) {
    if (ax.log) return String(v);
    const r = Math.round(v * 1e6) / 1e6;
    return (r < 0 ? "−" + Math.abs(r) : String(r)) + (ax.unit === "%" ? "%" : "");
  }
  function niceTicks(lo, hi, want) {
    const span = hi - lo || 1;
    const raw = span / want;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    let step = 10 * p;
    for (const k of [1, 2, 2.5, 5, 10]) if (raw <= k * p) { step = k * p; break; }
    const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step;
    const ticks = [];
    for (let i = 0; a + i * step <= b + step * 1e-6; i++) ticks.push(Math.round((a + i * step) * 1e6) / 1e6);
    return { lo: a, hi: b, ticks };
  }
  // The value axis: its range and ticks, from the values, the reference lines and the chart's rules.
  function valueAxis(ax, vals, refs) {
    const all = vals.concat(refs).filter((v) => typeof v === "number" && Number.isFinite(v));
    if (!all.length) all.push(0, 1);
    if (ax.log) {
      const lo = Math.floor(Math.log10(Math.min(...all, 0.5)) - 1e-9);
      const ticks = [];
      for (let e = 0; e >= lo; e--) ticks.push(Number("1e" + e));
      return { log: true, lo: Number("1e" + lo), hi: 1, ticks, dLo: lo };
    }
    let lo = Math.min(...all), hi = Math.max(...all);
    if (ax.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (typeof ax.floor_at_most === "number") lo = Math.min(lo, ax.floor_at_most);
    if (typeof ax.min === "number") lo = Math.min(ax.min, lo);
    if (typeof ax.max === "number") hi = Math.max(ax.max, hi);
    if (typeof ax.min_span === "number" && hi - lo < ax.min_span) hi = lo + ax.min_span;
    if (!(hi > lo)) { lo -= 1; hi += 1; }
    const t = niceTicks(lo, hi, 5);
    if (typeof ax.min === "number" && ax.min === Math.min(...all, ax.min)) t.lo = ax.min;
    if (typeof ax.max === "number" && ax.max === Math.max(...all, ax.max)) t.hi = ax.max;
    t.ticks = t.ticks.filter((v) => v >= t.lo - 1e-9 && v <= t.hi + 1e-9);
    return t;
  }
  function newSvg(W, H, label, kind, dom) {
    const tmp = document.createElement("div");
    tmp.insertAdjacentHTML("beforeend", "<svg></svg>");
    const svg = tmp.querySelector("svg");
    const NS = svg.namespaceURI;
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("class", "plot");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
    svg.setAttribute("data-axis-kind", kind || "");
    svg.setAttribute("data-axis-min", String(dom.lo));
    svg.setAttribute("data-axis-max", String(dom.hi));
    svg.style.height = H + "px";
    const add = (tag, attrs, text, parent) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
      if (text !== undefined) e.textContent = text;
      (parent || svg).append(e);
      return e;
    };
    return { svg, add };
  }
  function seriesKey(series, refs) {
    const items = (series.length > 1 ? series : []).map((s) =>
      h("span", null, h("i", { class: "k-" + s.mark + " s-" + (s.color || "c1") }), s.name));
    for (const r of refs || []) items.push(h("span", null, h("i", { class: "k-ref r-" + (r.role || "line") }), r.label));
    return items.length ? h("div", { class: "serieskey" }, items) : "";
  }
  function tipBox(host) {
    const tip = h("div", { class: "tip", hidden: true });
    host.style.position = "relative";
    host.append(tip);
    return tip;
  }
  function placeTip(tip, host, svg, W, H, x, y, lines) {
    tip.replaceChildren(h("b", null, lines[0]), ...lines.slice(1).map((l) => h("div", null, l)));
    tip.hidden = false;
    const box = svg.getBoundingClientRect();
    const sx = box.width / W || 1, sy = box.height / H || 1;
    tip.style.left = Math.min(Math.max(0, x * sx - 90), Math.max(0, box.width - 250)) + "px";
    tip.style.top = Math.max(0, y * sy - 70) + "px";
  }
  // Reference lines (break-even, the pooled rate, zero, the project's bar): the line, and its value in the margin; the
  // full words are in the key under the chart.
  function refShort(r, ax) {
    if (r.role === "zero") return "";
    if (ax.kind === "p") return pText(r.value);
    const v = Math.sign(r.value) * Number(fixed(Math.abs(r.value), ax.digits === undefined ? 1 : ax.digits));
    return (v < 0 ? "−" + Math.abs(v) : String(v)) + (ax.unit === "%" ? "%" : "");
  }
  function refLines(add, refs, ax, from, to, pos, vertical) {
    const placed = [];                                // [line position, label position] of the labels drawn so far
    for (const r of refs) {
      const p = pos(r.value);
      const cls = "ref " + (r.role || "line");
      const words = refShort(r, ax);
      if (vertical) {
        add("line", { class: cls, x1: p, x2: p, y1: from, y2: to, "data-value": r.value });
        const near = placed.filter(([q]) => Math.abs(q - p) < 52).length;
        if (words) add("text", { class: "reflabel", x: p, y: from - 6 - 12 * (near % 2), "text-anchor": "middle" }, words);
        placed.push([p, 0]);
      } else {
        add("line", { class: cls, x1: from, x2: to, y1: p, y2: p, "data-value": r.value });
        let ly = p + 4;
        for (const [q, qy] of placed) if (Math.abs(ly - qy) < 12) ly = p < q ? qy - 12 : qy + 12;
        if (words) { add("text", { class: "reflabel", x: to + 4, y: ly }, words); placed.push([p, ly]); }
      }
    }
  }
  function tipLine(s, p, ax, signed) {
    if (s.sized) return s.name + ": " + fmtV(p[1], ax) + " (" + fmtInt(p[3]) + " of " + fmtInt(p[2]) + ")";
    const bare = Object.assign({}, ax, { unit: ax.unit === "%" ? "%" : "" });
    const iv = typeof p[2] === "number" && typeof p[3] === "number" ? " (" + fmtV(p[2], bare, signed) + " to " + fmtV(p[3], bare, signed) + ")" : "";
    return s.name + ": " + fmtV(p[1], ax, signed) + iv;
  }

  // Seasons, wind bands, totals or dates across; a value up. An optional strip of counts (signals a season) sits
  // under the plot on its own small scale, never on the value axis.
  const withValues = (list) => (list || []).map((s) => Object.assign({}, s, {
    points: (s.points || []).filter((p) => Array.isArray(p) && typeof p[1] === "number" && Number.isFinite(p[1])) }));
  function drawColumns(host, pn, title) {
    const W = Math.max(300, host.clientWidth || 600);
    const series = withValues(pn.series), refs = pn.refs || [], ax = pn.y || {}, xk = (pn.x || {}).kind || "category";
    const counts = pn.counts && (pn.counts.points || []).length ? pn.counts : null;
    const m = { l: 50, r: refs.some((r) => r.role !== "zero") ? 46 : 14, t: 20, b: 26 };
    const plotH = W < 520 ? 190 : 220, stripH = counts ? 54 : 0;
    const H = m.t + plotH + stripH + m.b;
    const vals = [];
    for (const s of series) for (const p of s.points || []) {
      vals.push(p[1]);
      if (!s.sized && typeof p[2] === "number") vals.push(p[2], p[3]);
    }
    const dom = valueAxis(ax, vals, refs.map((r) => r.value));
    const signed = dom.lo < 0;
    const { svg, add } = newSvg(W, H, title, ax.kind, dom);
    const y = (v) => m.t + (1 - (v - dom.lo) / (dom.hi - dom.lo)) * plotH;
    const x0 = m.l, x1 = W - m.r;
    let xOf, labels = [], band = 0, xsSorted = [];
    if (xk === "category") {
      labels = (pn.x.labels || []).map(String);
      band = (x1 - x0) / Math.max(1, labels.length);
      const idx = new Map(labels.map((l, i) => [l, i]));
      xOf = (k) => x0 + band * ((idx.has(String(k)) ? idx.get(String(k)) : 0) + 0.5);
    } else {
      const xsAll = [];
      for (const s of series) for (const p of s.points || []) xsAll.push(xk === "time" ? Date.parse(p[0]) : Number(p[0]));
      let a = Math.min(...xsAll), b = Math.max(...xsAll);
      if (xk === "number") { a -= 0.5; b += 0.5; }
      if (!(b > a)) { a -= 1; b += 1; }
      xOf = (k) => x0 + (((xk === "time" ? Date.parse(k) : Number(k)) - a) / (b - a)) * (x1 - x0);
      xsSorted = [...new Set(xsAll)].sort((p, q) => p - q);
      xOf.range = [a, b];
    }
    // grid and value ticks
    for (const v of dom.ticks) {
      add("line", { class: "axis", x1: x0, x2: x1, y1: y(v), y2: y(v) });
      add("text", { class: "tick", x: x0 - 6, y: y(v) + 4, "text-anchor": "end" }, tickText(v, ax));
    }
    if (ax.label) add("text", { class: "axislabel", x: 0, y: 11 }, ax.label);
    // x labels
    const baseY = H - 8;
    if (xk === "category") {
      const widest = Math.max(...labels.map((l) => l.length)) * 6.6 + 6;
      const every = Math.max(1, Math.ceil(widest / band));
      labels.forEach((l, i) => { if (i % every === 0) add("text", { class: "tick", x: x0 + band * (i + 0.5), y: baseY, "text-anchor": "middle" }, l); });
    } else if (xk === "time") {
      const [a, b] = xOf.range;
      const y0 = new Date(a).getUTCFullYear(), y1 = new Date(b).getUTCFullYear();
      const every = Math.max(1, Math.ceil((y1 - y0 + 1) * 40 / (x1 - x0)));
      for (let yr = y0; yr <= y1 + 1; yr++) {
        const t = Date.UTC(yr, 0, 1);
        if (t < a || t > b || (yr - y0) % every) continue;
        const px = x0 + ((t - a) / (b - a)) * (x1 - x0);
        add("line", { class: "axis", x1: px, x2: px, y1: m.t, y2: m.t + plotH });
        add("text", { class: "tick", x: px, y: baseY, "text-anchor": "middle" }, String(yr));
      }
    } else {
      const [a, b] = xOf.range;
      const step = (pn.x && pn.x.step) || 5;
      for (let v = Math.ceil(a / step) * step; v <= b; v += step) {
        add("text", { class: "tick", x: xOf(v), y: baseY, "text-anchor": "middle" }, String(v));
      }
    }
    refLines(add, refs, ax, x0, x1, y, false);
    // marks
    const dodged = series.filter((s) => s.mark !== "line");
    series.forEach((s, si) => {
      const cls = "s-" + (s.color || "c1");
      const pts = s.points || [];
      const di = dodged.indexOf(s), dn = dodged.length;
      const off = xk === "category" && di >= 0 && dn > 1 ? (di - (dn - 1) / 2) * Math.min(12, band / (dn + 1)) : 0;
      if (s.mark === "line") {
        if (pts.length > 1) add("path", { class: "sline " + cls, d: pts.map((p, i) => (i ? "L" : "M") + xOf(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join(" ") });
        if (xk === "category" && pts.length <= 40) for (const p of pts) add("circle", { class: "sdot small " + cls, cx: xOf(p[0]), cy: y(p[1]), r: 2.5 });
        const e = pts[pts.length - 1];
        if (e && xk === "time") {
          add("circle", { class: "sdot " + cls, cx: xOf(e[0]), cy: y(e[1]), r: 4 });
          add("text", { class: "endlabel", x: xOf(e[0]) - 6, y: y(e[1]) - 8, "text-anchor": "end" }, fmtV(e[1], ax, signed));
        }
      } else if (s.mark === "bar") {
        const bw = Math.max(3, Math.min(28, (band || 12) * 0.6 / Math.max(1, dn)));
        for (const p of pts) {
          const top = y(Math.max(0, p[1])), bot = y(Math.min(0, p[1]));
          add("rect", { class: "sbar " + cls, x: xOf(p[0]) + off - bw / 2, y: top, width: bw, height: Math.max(1, bot - top), rx: 2 });
        }
      } else {
        const nmax = s.sized ? Math.max(1, ...pts.map((p) => p[2] || 0)) : 1;
        for (const p of pts) {
          const cx = xOf(p[0]) + off;
          if (!s.sized && typeof p[2] === "number" && typeof p[3] === "number") {
            add("line", { class: "whisker " + cls, x1: cx, x2: cx, y1: y(p[2]), y2: y(p[3]) });
          }
          const r = s.sized ? 2 + 4.5 * Math.sqrt((p[2] || 0) / nmax) : 4;
          add("circle", { class: "sdot " + cls, cx, cy: y(p[1]), r: r.toFixed(2), "data-value": p[1] });
        }
      }
    });
    // the counts strip
    if (counts) {
      const top = m.t + plotH + 20, hgt = stripH - 22;
      const cmax = Math.max(1, ...counts.points.map((p) => p[1]));
      add("text", { class: "tick", x: x0 - 6, y: top + 8, "text-anchor": "end" }, String(cmax));
      add("text", { class: "axislabel", x: x0 - 6, y: top + hgt + 2, "text-anchor": "end" }, counts.name);
      const bw = Math.max(2, Math.min(20, band * 0.5));
      for (const p of counts.points) {
        const hh = (p[1] / cmax) * hgt;
        add("rect", { class: "sbar s-ink2", x: xOf(p[0]) - bw / 2, y: top + hgt - hh, width: bw, height: Math.max(1, hh), rx: 1 });
      }
    }
    // hover
    const cross = add("line", { class: "cross", x1: 0, x2: 0, y1: m.t, y2: m.t + plotH, visibility: "hidden" });
    const tip = tipBox(host);
    host.append(svg);
    const hit = add("rect", { x: x0, y: 0, width: x1 - x0, height: H, fill: "transparent" });
    const at = (px) => {
      if (xk === "category") {
        const i = Math.min(labels.length - 1, Math.max(0, Math.floor((px - x0) / band)));
        return { key: labels[i], x: x0 + band * (i + 0.5) };
      }
      const [a, b] = xOf.range;
      const want = a + ((px - x0) / (x1 - x0)) * (b - a);
      let best = xsSorted[0];
      for (const v of xsSorted) if (Math.abs(v - want) < Math.abs(best - want)) best = v;
      return { key: best, x: x0 + ((best - a) / (b - a)) * (x1 - x0) };
    };
    hit.addEventListener("pointermove", (evt) => {
      const box = svg.getBoundingClientRect();
      const px = ((evt.clientX - box.left) / box.width) * W;
      const spot = at(px);
      const lines = [];
      if (xk === "category") {
        lines.push(String(spot.key));
        for (const s of series) {
          const p = (s.points || []).find((q) => String(q[0]) === String(spot.key));
          if (p) lines.push(tipLine(s, p, ax, signed));
        }
        if (counts) {
          const c = counts.points.find((q) => String(q[0]) === String(spot.key));
          if (c) lines.push(counts.name + ": " + fmtInt(c[1]));
        }
        for (const t of (pn.tips || {})[spot.key] || []) lines.push(t);
      } else if (xk === "time") {
        lines.push(new Date(spot.key).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }));
        for (const s of series) {
          let p = null;
          for (const q of s.points || []) { if (Date.parse(q[0]) <= spot.key) p = q; else break; }
          if (p) lines.push(s.name + ": " + fmtV(p[1], ax, signed) + (Date.parse(p[0]) === spot.key && p[2] ? " · " + p[2] : ""));
        }
      } else {
        lines.push(((pn.x.label || "") + " " + spot.key).trim());
        for (const s of series) {
          const p = (s.points || []).find((q) => Number(q[0]) === spot.key);
          if (p) lines.push(tipLine(s, p, ax, signed));
        }
      }
      cross.setAttribute("x1", spot.x); cross.setAttribute("x2", spot.x); cross.setAttribute("visibility", "visible");
      placeTip(tip, host, svg, W, H, spot.x, m.t + 30, lines);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; });
  }

  // One row per case, a value across: labels on the left (wrapped), bars or dots with intervals, reference lines
  // standing up through every row, and a note (a sample size) beside each row's marks.
  function wrapWords(text, chars) {
    const out = [];
    let cur = "";
    for (const w of String(text).split(" ")) {
      if (cur && (cur + " " + w).length > chars) { out.push(cur); cur = w; } else cur = cur ? cur + " " + w : w;
    }
    if (cur) out.push(cur);
    return out;
  }
  const CHAR_W = 6.6;                   // a generous width for one character of an 11-pixel chart label
  function drawRows(host, pn, title) {
    const W = Math.max(300, host.clientWidth || 600);
    const series = withValues(pn.series), refs = pn.refs || [], ax = pn.x || {}, rows = pn.rows || [];
    const notes = pn.notes || {};
    const LW = Math.min(Math.round(W * 0.42), 300);
    const hasNotes = Object.keys(notes).length > 0;
    const m = { l: LW + 12, r: hasNotes ? 76 : 16, t: 34, b: 36 };
    const chars = Math.max(18, Math.floor((LW - 4) / 6.3));
    const wrapped = rows.map((r) => wrapWords(r, chars));
    const marks = series.length;
    const vals = [];
    for (const s of series) for (const p of s.points || []) {
      vals.push(p[1]);
      if (typeof p[2] === "number") vals.push(p[2], p[3]);
    }
    const dom = valueAxis(ax, vals, refs.map((r) => r.value));
    const signed = dom.lo < 0;
    const x0 = m.l, x1 = W - m.r;
    const xOf = dom.log
      ? (v) => x0 + ((ax.reverse ? -Math.log10(v) : Math.log10(v) - dom.dLo) / -dom.dLo) * (x1 - x0)
      : (v) => x0 + ((v - dom.lo) / (dom.hi - dom.lo)) * (x1 - x0);
    const refXs = refs.map((r) => xOf(r.value)).filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
    // Each row's note (its sample size) sits right of the row's marks, else left of them, and never across a reference
    // line from them: on the chart of every result against the bar, a label past the bar would stand in the region of
    // results that clear it. When neither side has room, it takes a line of its own under the marks, between the same
    // two lines, and the row grows by that line.
    const spots = rows.map((r, ri) => {
      if (!notes[r]) return null;
      const xs = [];
      for (const s of series) {
        const p = (s.points || []).find((q) => q[0] === r);
        if (!p) continue;
        if (s.mark === "bar") xs.push(xOf(Math.max(dom.lo, Math.min(0, p[1]))), xOf(Math.max(0, p[1])));
        else xs.push(xOf(p[1]), ...(typeof p[2] === "number" && typeof p[3] === "number" ? [xOf(p[2]), xOf(p[3])] : []));
      }
      const near = xs.length ? Math.min(...xs) : x0, far = xs.length ? Math.max(...xs) : x0;
      const left = Math.max(-Infinity, ...refXs.filter((x) => x < near).map((x) => x + 4));
      const hi = Math.min(W - 2, ...refXs.filter((x) => x > far).map((x) => x - 4));
      const w = String(notes[r]).length * CHAR_W;
      // beside the marks, clear of the row's own label (12-pixel text) on the left
      const label = Math.max(0, ...wrapped[ri].map((l) => l.length)) * CHAR_W * 12 / 11 + 6;
      if (far + 8 + w <= hi) return { x: far + 8, anchor: "start", below: false };
      if (near - 8 - w >= Math.max(x0, label, left)) return { x: near - 8, anchor: "end", below: false };
      // under the marks, below the row's label, so it may start left of the plot
      return { x: Math.max(Math.max(2, left), Math.min((near + far - w) / 2, hi - w)), anchor: "start", below: true };
    });
    const baseH = wrapped.map((ls) => Math.max(15 * ls.length + 10, (series.some((s) => s.mark === "bar") ? 9 : 12) * marks + 12));
    const rowH = baseH.map((h0, i) => h0 + (spots[i] && spots[i].below ? 13 : 0));
    const H = m.t + rowH.reduce((a, b) => a + b, 0) + m.b;
    const { svg, add } = newSvg(W, H, title, ax.kind, dom);
    const plotBottom = H - m.b;
    // the tick labels, left to right; one that would run into the label before it (a narrow chart, a log scale) is
    // left out, and its grid line stays
    let lastRight = -Infinity;
    for (const [px, v] of dom.ticks.map((v) => [xOf(v), v]).sort((a, b) => a[0] - b[0])) {
      add("line", { class: "axis", x1: px, x2: px, y1: m.t, y2: plotBottom });
      const words = tickText(v, ax), half = words.length * CHAR_W / 2;
      if (px - half < lastRight + 4) continue;
      add("text", { class: "tick", x: px, y: plotBottom + 16, "text-anchor": "middle" }, words);
      lastRight = px + half;
    }
    if (ax.label) add("text", { class: "axislabel", x: x1, y: H - 1, "text-anchor": "end" }, ax.label);
    const band = add("rect", { class: "rowhot", x: 0, y: 0, width: W, height: 0, visibility: "hidden" });
    let top = m.t;
    const bands = [];
    rows.forEach((r, ri) => {
      const hgt = rowH[ri], h0 = baseH[ri];
      bands.push([top, hgt, r]);
      if (ri) add("line", { class: "rowline", x1: 0, x2: x1, y1: top, y2: top });
      wrapped[ri].forEach((ln, li) => add("text", { class: "rowlabel", x: 0, y: top + 14 + li * 15 }, ln));
      const step = (h0 - 12) / Math.max(1, marks);
      series.forEach((s, si) => {
        const p = (s.points || []).find((q) => q[0] === r);
        if (!p) return;
        const cy = top + 6 + step * (si + 0.5);
        const cls = "s-" + (s.color || "c1");
        if (s.mark === "bar") {
          const a = xOf(Math.max(dom.lo, Math.min(0, p[1]))), b = xOf(Math.max(0, p[1]));
          add("rect", { class: "sbar " + cls, x: Math.min(a, b), y: cy - Math.min(4, step / 2 - 1), width: Math.max(1, Math.abs(b - a)), height: Math.max(2, Math.min(8, step - 2)), rx: 2, "data-value": p[1] });
        } else {
          if (typeof p[2] === "number" && typeof p[3] === "number") {
            add("line", { class: "whisker " + cls, x1: xOf(p[2]), x2: xOf(p[3]), y1: cy, y2: cy });
          }
          add("circle", { class: "sdot " + cls, cx: xOf(p[1]), cy, r: 4.5, "data-value": p[1] });
        }
      });
      const spot = spots[ri];
      if (spot) {
        add("text", { class: "note", x: spot.x, y: spot.below ? top + h0 + 7 : top + h0 / 2 + 4,
          "text-anchor": spot.anchor }, notes[r]);
      }
      top += hgt;
    });
    refLines(add, refs, ax, m.t, plotBottom, xOf, true);
    const tip = tipBox(host);
    host.append(svg);
    const hit = add("rect", { x: 0, y: m.t, width: W, height: plotBottom - m.t, fill: "transparent" });
    hit.addEventListener("pointermove", (evt) => {
      const box = svg.getBoundingClientRect();
      const py = ((evt.clientY - box.top) / box.height) * H;
      const b = bands.find(([t, hh]) => py >= t && py < t + hh);
      if (!b) return;
      const lines = [b[2]];
      for (const s of series) {
        const p = (s.points || []).find((q) => q[0] === b[2]);
        if (p) lines.push(tipLine(s, p, ax, signed));
      }
      if (notes[b[2]]) lines.push(notes[b[2]]);
      for (const t of (pn.tips || {})[b[2]] || []) lines.push(t);
      band.setAttribute("y", b[0]); band.setAttribute("height", b[1]); band.setAttribute("visibility", "visible");
      placeTip(tip, host, svg, W, H, W * 0.55, b[0] + b[1], lines);
    });
    hit.addEventListener("pointerleave", () => { band.setAttribute("visibility", "hidden"); tip.hidden = true; });
  }

  function drawPlot(body, c) {
    const plot = c.plot || {};
    for (const pn of plot.panels || []) {
      if (pn.name) body.append(h("h3", { class: "panelname" }, pn.name));
      const host = h("div", { class: "bt-plot" });
      body.append(host);
      if (plot.layout === "rows") drawRows(host, pn, c.title);
      else drawColumns(host, pn, c.title);
      body.append(seriesKey(pn.series || [], pn.refs || []));
    }
  }

  function btTable(c) {
    const t = c.table || {};
    const num = t.num || [];
    const det = h("details", { class: "bt-table", open: state.btOpen.has(c.id) },
      h("summary", null, "Show the numbers"),
      h("div", { class: "tablewrap" }, h("table", null,
        h("thead", null, h("tr", null, (t.columns || []).map((x, i) => h("th", { scope: "col", class: num[i] ? "num" : null }, x)))),
        h("tbody", null, (t.rows || []).map((r) => h("tr", null, r.map((x, i) => h("td", { class: num[i] ? "num" : null }, x))))))),
      t.note ? h("p", { class: "faint" }, t.note) : "");
    det.addEventListener("toggle", () => { if (det.open) state.btOpen.add(c.id); else state.btOpen.delete(c.id); });
    return det;
  }

  function fileLink(f) {
    return f.url ? h("a", { href: f.url, target: "_blank", rel: "noreferrer noopener" }, f.path) : f.path;
  }
  function btWords(c) {
    const src = (c.sources || []).map((s, i) => [i ? "; " : "", fileLink(s),
      s.blob ? " (blob " + s.blob + ", changed " + s.changed + ")" : s.changed ? " (" + s.changed + ")" : ""]);
    const ups = (c.writeups || []).map((w, i) => [i ? "; " : "", fileLink(w), w.section ? ", “" + w.section + "”" : ""]);
    return h("div", { class: "bt-words" },
      h("p", null, c.shows),
      h("p", null, c.not_shows),
      h("p", null, h("b", null, "Sample: "), String(c.sample).replace(/\.?$/, ".")),
      (c.bar_lines || []).map((l) => h("p", { class: "bt-bar" + (c.clears ? " clears" : "") }, l)),
      h("p", { class: "faint" }, (c.sources || []).length > 1 ? "Sources: " : "Source: ", src),
      ups.length ? h("p", { class: "faint" }, "Write-up: ", ups) : "");
  }

  function drawBacktests(d) {
    const out = h("div", null, h("h1", null, "Backtests"),
      h("div", { class: "lede" }, (d.intro || []).map((s) => h("p", null, s))));
    const todo = [];
    for (const g of d.groups || []) {
      out.append(h("h2", { class: "group" }, g.heading));
      const grid = h("div", { class: "bt-grid" });
      out.append(grid);
      for (const c of g.charts || []) {
        if (c.not_charted) {
          grid.append(h("section", { class: "panel btchart", "data-chart": c.id }, h("div", { class: "body" }, h("p", { class: "muted" }, c.not_charted))));
          continue;
        }
        if (c.missing) {
          grid.append(h("section", { class: "panel btchart", "data-chart": c.id }, h("header", null, h("h2", null, c.name || c.id)),
            h("div", { class: "body" }, h("p", { class: "muted" }, c.missing))));
          continue;
        }
        const body = h("div", { class: "body" });
        grid.append(h("section", { class: "panel btchart", "data-chart": c.id },
          h("header", null, h("h2", null, c.title, h("span", { class: "scope" }, c.name))), body));
        todo.push([body, c]);
      }
    }
    main.replaceChildren(out);                        // in place first, so each chart can measure its width
    for (const [body, c] of todo) {
      try {
        drawPlot(body, c);
      } catch (e) {
        body.append(h("p", { class: "muted" }, "This chart could not be drawn; its numbers are in the table below."));
      }
      body.append(btWords(c), btTable(c));
    }
    return out;
  }

  // ------------------------------------------------------------------ start
  window.addEventListener("hashchange", () => load(false));
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (!["game", "backtests"].includes(parseHash().screen)) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => load(true), 250);
  });
  setInterval(() => { if (!document.hidden) load(true); }, REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(true); });
  load(false);
})();
