/*
 * Web version of the Power BI report: pages, filters and visuals come from window.REPORT_SPEC
 * (generated from src/stjohns_econ/report_spec.py); numbers come from window.SJMeasures over
 * window.DASHBOARD (generated from data/processed/).
 */
(function () {
  "use strict";
  var data = window.DASHBOARD;
  var spec = window.REPORT_SPEC;
  var SJM = window.SJMeasures;
  var C = window.SJCharts;
  var M = SJM.create(data);
  var el = C.el;

  var GEO_ORDER = data.geographies.map(function (g) { return g.code; });
  var GEO_BY_SHORT = {};
  data.geographies.forEach(function (g) { GEO_BY_SHORT[g.short] = g.code; });
  var COLOUR_VAR = { "St. John's": "--geo-SJ", "Canada": "--geo-CA", "N.L.": "--geo-NL",
    "Single dwellings": "--bt-single", "Multiple dwellings": "--bt-multi" };

  var monthly = {};
  Object.keys(data.series).forEach(function (k) {
    if (M.meta(k.split("|")[0]).frequency === "Monthly") data.series[k].dates.forEach(function (d) { monthly[d] = true; });
  });
  var MONTHS = Object.keys(monthly).sort();
  var LAST_MONTH = MONTHS[MONTHS.length - 1];
  var state = { from: "2018-01-01", to: LAST_MONTH, geos: GEO_ORDER.slice(), base: "2018-01-01" };
  var charts = [];

  /* ------------------------------------------------------------------ helpers */

  function filterValues(visual, column) {
    var f = (visual.filters || []).filter(function (x) { return x.field.name === column; })[0];
    return f ? f.values : null;
  }
  function pageRange(page) {
    return page.id === "overview" ? { from: "2018-01-01", to: null } : { from: state.from, to: state.to };
  }
  function kpiRange(page) { return page.id === "overview" ? null : { from: state.from, to: state.to }; }
  function geosFor(visual) {
    var fixed = filterValues(visual, "GeographyCode");
    var chosen = visual.ignore_geography_slicer ? GEO_ORDER : state.geos;
    return GEO_ORDER.filter(function (g) { return chosen.indexOf(g) >= 0 && (!fixed || fixed.indexOf(g) >= 0); });
  }
  function geoLabel(code) { return M.geographies[code].short; }
  function percentAxis(v) { return (v < 0 ? SJM.MINUS : "") + Math.abs(Math.round(v * 1000) / 10) + "%"; }
  function plainAxis(decimals) {
    return function (v) { return (v < 0 ? SJM.MINUS : "") + Math.abs(v).toLocaleString("en-CA", { maximumFractionDigits: decimals }); };
  }
  function monthOptions(select, months, selected) {
    months.forEach(function (m) {
      var o = el("option", { value: m }, SJM.monthLabel(m));
      if (m === selected) o.selected = true;
      select.appendChild(o);
    });
  }

  /* ------------------------------------------------------------------ filters */

  function renderFilters(container, page) {
    var form = el("form", { "class": "filters", "aria-label": "Filters for this page" });
    form.addEventListener("submit", function (e) { e.preventDefault(); });

    var range = el("fieldset", { "class": "filter" });
    range.appendChild(el("legend", null, "Date range"));
    var row = el("div", { "class": "filter-range" });
    var from = el("select", { id: "from-month" });
    var to = el("select", { id: "to-month" });
    var months2018 = MONTHS.filter(function (m) { return m >= "2018-01-01"; });
    monthOptions(from, months2018, state.from);
    monthOptions(to, months2018, state.to);
    row.appendChild(el("label", { "for": "from-month", "class": "range-word" }, "From"));
    row.appendChild(from);
    row.appendChild(el("label", { "for": "to-month", "class": "range-word" }, "to"));
    row.appendChild(to);
    range.appendChild(row);
    form.appendChild(range);

    var geo = el("fieldset", { "class": "filter" });
    geo.appendChild(el("legend", null, "Geography"));
    var chips = el("div", { "class": "chips" });
    data.geographies.forEach(function (g) {
      var label = el("label", { "class": "chip" });
      var box = el("input", { type: "checkbox", value: g.code, name: "geo" });
      box.checked = state.geos.indexOf(g.code) >= 0;
      var span = el("span", null, g.short);
      span.style.setProperty("--chip-colour", "var(" + COLOUR_VAR[g.short] + ")");
      label.appendChild(box);
      label.appendChild(span);
      chips.appendChild(label);
    });
    geo.appendChild(chips);
    form.appendChild(geo);

    var base = el("div", { "class": "filter" });
    base.appendChild(el("label", { "for": "base-month" }, "Index base month"));
    var baseSel = el("select", { id: "base-month" });
    monthOptions(baseSel, MONTHS, state.base);
    base.appendChild(baseSel);
    form.appendChild(base);

    var status = el("p", { "class": "filter-status", role: "status", "aria-live": "polite" });
    form.appendChild(status);
    container.appendChild(form);

    function describe() {
      var names = state.geos.map(geoLabel);
      status.textContent = "Showing " + SJM.monthLabelLong(state.from) + " to " + SJM.monthLabelLong(state.to) +
        " for " + (names.length ? names.join(", ") : "no geography") + "; indexed charts use " +
        SJM.monthLabelLong(state.base) + " = 100. Cards always show St. John's.";
    }
    describe();

    form.addEventListener("change", function (event) {
      if (event.target === from || event.target === to) {
        state.from = from.value;
        state.to = to.value;
        if (state.from > state.to) {
          var t = state.from; state.from = state.to; state.to = t;
          from.value = state.from; to.value = state.to;
        }
      } else if (event.target === baseSel) {
        state.base = baseSel.value;
      } else if (event.target.name === "geo") {
        var checked = Array.prototype.slice.call(form.querySelectorAll("input[name=geo]:checked")).map(function (b) { return b.value; });
        if (!checked.length) { event.target.checked = true; checked = [event.target.value]; }
        state.geos = GEO_ORDER.filter(function (g) { return checked.indexOf(g) >= 0; });
      }
      describe();
      renderVisuals(page);
    });
  }

  /* ------------------------------------------------------------------ visuals */

  function kpiModel(visual, page) {
    var ind = (filterValues(visual, "IndicatorCode") || [null])[0];
    var range = kpiRange(page);
    var geo = "SJ";
    var meta = ind ? M.meta(ind) : null;
    var value = null, period = visual.subtitle || null, delta = null;
    switch (visual.value.name) {
      case "YoY %": value = SJM.signedPercent(M.yoy(ind, geo, range).pct); break;
      case "Latest Value": value = SJM.formatByString(M.yoy(ind, geo, range).value, meta.format); break;
      case "12-Month Rolling Total": value = SJM.formatByString(M.rollingTotal(ind, geo, range).value, "#,0"); break;
      case "Units Permitted per 1,000 Residents": {
        var pc = M.perCapita(geo, range);
        value = pc.value === null ? null : pc.value.toFixed(1);
        break;
      }
    }
    if (visual.subtitle_measure === "Latest Period Label" && ind) period = SJM.periodLabel(M.latestDate(ind, geo, range), meta.frequency);
    switch (visual.delta.name) {
      case "Gap vs Canada Label": delta = M.gapDelta(ind, geo, range); break;
      case "YoY Delta Label": delta = M.yoyDelta(ind, geo, range); break;
      case "Rolling 12-Month Delta Label": delta = M.rollingDelta(ind, geo, range); break;
      case "Units per 1,000 vs Canada Label": delta = M.perCapitaDelta(geo, range); break;
    }
    return { id: visual.id, title: visual.title, period: period, value: value, delta: delta };
  }

  function seriesFor(visual, page, measure) {
    var ind = (filterValues(visual, "IndicatorCode") || [null])[0];
    var range = pageRange(page);
    return geosFor(visual).map(function (geo) {
      var pts;
      if (measure === "YoY %") pts = M.yoySeries(ind, geo, range);
      else if (measure === "Index (Base = 100)") pts = M.indexSeries(ind, geo, state.base, range);
      else if (measure === "Units Permitted per 1,000 Residents") pts = M.perCapitaSeries(geo, range);
      else pts = M.points(ind, geo, range);
      return { key: geo, label: geoLabel(geo), colourVar: COLOUR_VAR[geoLabel(geo)], points: pts };
    }).filter(function (s) { return s.points.length; });
  }

  function lineVisual(container, visual, page) {
    var measures = visual.roles.Y.map(function (f) { return f.name; });
    var ind = (filterValues(visual, "IndicatorCode") || [null])[0];
    var meta = ind ? M.meta(ind) : null;
    var title = visual.title;
    if (visual.title_measure === "Index Chart Title") title = meta.short + ", indexed to " + SJM.monthLabel(state.base) + " = 100";
    var cfg = { id: "web-" + visual.id, title: title, subtitle: visual.subtitle, alt: visual.alt,
      dateLabel: SJM.monthLabel, note: visual.notes || null };
    if (measures.length === 3) {
      var b = M.boundsSeries(ind, "SJ", pageRange(page));
      cfg.series = [{ key: "SJ", label: "Estimate", colourVar: "--geo-SJ",
        points: b.map(function (p) { return { date: p.date, value: p.value }; }) }];
      cfg.band = { label: "95% confidence range", points: b };
      cfg.format = function (v) { return SJM.formatByString(v, meta.format); };
      cfg.axisFormat = function (v) { return plainAxis(1)(v) + "%"; };
      cfg.alt = visual.alt;
    } else {
      var measure = measures[0];
      cfg.series = seriesFor(visual, page, measure);
      if (measure === "YoY %") { cfg.format = SJM.signedPercent; cfg.axisFormat = percentAxis; }
      else if (measure === "Index (Base = 100)") { cfg.format = function (v) { return v.toFixed(1); }; cfg.axisFormat = plainAxis(0); }
      else if (measure === "Units Permitted per 1,000 Residents") { cfg.format = function (v) { return v.toFixed(1); }; cfg.axisFormat = plainAxis(1); }
      else {
        cfg.format = function (v) { return SJM.formatByString(v, meta.format); };
        cfg.axisFormat = meta.unit === "Percent" ? function (v) { return plainAxis(1)(v) + "%"; } : plainAxis(1);
      }
      if (meta && meta.code === "NHPI_TOTAL") cfg.note = "Newfoundland and Labrador is not shown: its index equals the St. John's index.";
    }
    charts.push(C.lineChart(container, cfg));
  }

  function barVisual(container, visual, page) {
    var codes = filterValues(visual, "IndicatorCode");
    var range = pageRange(page);
    var geos = geosFor(visual);
    var latest = M.latestDate(codes[0], "SJ", range);
    charts.push(C.barChart(container, {
      id: "web-" + visual.id, title: visual.title, alt: visual.alt,
      subtitle: "12-month change, " + SJM.monthLabelLong(latest || state.to),
      categories: codes.map(function (c) { return { key: c, label: M.meta(c).short }; }),
      series: geos.map(function (g) { return { key: g, label: geoLabel(g), colourVar: COLOUR_VAR[geoLabel(g)] }; }),
      value: function (code, geo) { return M.yoy(code, geo, range).pct; },
      format: SJM.signedPercent, axisFormat: percentAxis
    }));
  }

  function columnVisual(container, visual, page) {
    var codes = filterValues(visual, "IndicatorCode");
    var range = pageRange(page);
    var fromYear = +range.from.slice(0, 4), toYear = +(range.to || LAST_MONTH).slice(0, 4);
    var years = [];
    for (var y = fromYear; y <= toYear; y++) years.push(y);
    if (visual.kind === "column_stacked") {
      var geo = "SJ";
      var cats = years.map(function (yy) {
        var months = M.points(codes[0], geo, range).filter(function (p) { return +p.date.slice(0, 4) === yy; }).length;
        return { key: String(yy), label: String(yy), note: months && months < 12 ? months + " months" : null, months: months };
      }).filter(function (c) { return c.months > 0; });
      charts.push(C.columnChart(container, {
        id: "web-" + visual.id, title: visual.title, subtitle: visual.subtitle, alt: visual.alt, stacked: true,
        categories: cats,
        series: codes.map(function (c) { return { key: c, label: M.meta(c).short, colourVar: COLOUR_VAR[M.meta(c).short] }; }),
        value: function (year, code) {
          return M.points(code, geo, range).filter(function (p) { return p.date.slice(0, 4) === year; })
            .reduce(function (a, p) { return a + p.value; }, 0);
        },
        format: function (v) { return SJM.formatByString(v, "#,0"); }, axisFormat: plainAxis(0)
      }));
    } else {
      var geos = geosFor(visual);
      var popYears = years.filter(function (yy) { return geos.some(function (g) { return M.yoyAt(codes[0], g, yy + "-07-01").pct !== null; }); });
      charts.push(C.columnChart(container, {
        id: "web-" + visual.id, title: visual.title, subtitle: visual.subtitle, alt: visual.alt, stacked: false,
        categories: popYears.map(function (yy) { return { key: String(yy), label: String(yy) }; }),
        series: geos.map(function (g) { return { key: g, label: geoLabel(g), colourVar: COLOUR_VAR[geoLabel(g)] }; }),
        value: function (year, geo) { return M.yoyAt(codes[0], geo, year + "-07-01").pct; },
        format: SJM.signedPercent, axisFormat: percentAxis
      }));
    }
  }

  function renderVisuals(page) {
    charts.forEach(function (c) { if (c.observer) c.observer.disconnect(); });
    charts = [];
    var kpis = document.getElementById("kpis");
    var chartGrid = document.getElementById("charts");
    kpis.textContent = "";
    chartGrid.textContent = "";
    var visuals = page.visuals.slice().sort(function (a, b) { return a.tab - b.tab; });
    visuals.forEach(function (v) {
      if (v.kind === "kpi") C.kpiCard(kpis, kpiModel(v, page));
      else if (v.kind === "line") lineVisual(chartGrid, v, page);
      else if (v.kind === "bar_clustered") barVisual(chartGrid, v, page);
      else if (v.kind === "column_stacked" || v.kind === "column_clustered") columnVisual(chartGrid, v, page);
    });
  }

  /* ------------------------------------------------------------------ pages */

  function currentPage() {
    var id = (location.hash || "#overview").slice(1);
    return spec.pages.filter(function (p) { return p.id === id; })[0] || spec.pages[0];
  }

  function renderPage(focusHeading) {
    var page = currentPage();
    var main = document.getElementById("main");
    main.textContent = "";
    var title = page.visuals.filter(function (v) { return v.kind === "title"; })[0];
    var footer = page.visuals.filter(function (v) { return v.kind === "footer"; })[0];
    var head = el("div", { "class": "page-head" });
    var h2 = el("h2", { id: "page-title", tabindex: "-1" }, title.text[0]);
    head.appendChild(h2);
    head.appendChild(el("p", { "class": "page-question" }, title.text[1]));
    main.appendChild(head);
    if (page.visuals.some(function (v) { return v.kind.indexOf("slicer") === 0; })) renderFilters(main, page);
    var kpiCount = page.visuals.filter(function (v) { return v.kind === "kpi"; }).length;
    var kpiSection = el("section", { "aria-label": "Key indicators for St. John's" });
    kpiSection.appendChild(el("div", { "class": "kpis count-" + kpiCount, id: "kpis" }));
    main.appendChild(kpiSection);
    var chartSection = el("section", { "aria-label": "Charts" });
    var chartCount = page.visuals.filter(function (v) { return ["line", "bar_clustered", "column_stacked", "column_clustered"].indexOf(v.kind) >= 0; }).length;
    chartSection.appendChild(el("div", { "class": "charts count-" + chartCount, id: "charts" }));
    main.appendChild(chartSection);
    main.appendChild(el("p", { "class": "chart-note" }, footer.text[0]));
    renderVisuals(page);

    document.querySelectorAll(".page-nav a").forEach(function (a) {
      if (a.getAttribute("href") === "#" + page.id) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    document.title = page.name + " | St. John's Economy and Housing Dashboard (web version)";
    if (focusHeading) h2.focus();
  }

  function renderNav() {
    var list = document.querySelector(".page-nav ul");
    spec.pages.forEach(function (p) {
      var li = el("li");
      li.appendChild(el("a", { href: "#" + p.id }, p.name));
      list.appendChild(li);
    });
  }

  /* ------------------------------------------------------------------ theme */

  function storedTheme() { try { return localStorage.getItem("sje-theme"); } catch (e) { return null; } }
  function storeTheme(v) { try { localStorage.setItem("sje-theme", v); } catch (e) { /* storage unavailable */ } }
  function effectiveTheme() {
    var attr = document.documentElement.getAttribute("data-theme");
    if (attr) return attr;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function setupTheme() {
    var t = storedTheme();
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    var btn = document.getElementById("theme-toggle");
    function sync() {
      var dark = effectiveTheme() === "dark";
      btn.setAttribute("aria-pressed", dark ? "true" : "false");
      btn.textContent = dark ? "Dark theme: on" : "Dark theme: off";
    }
    btn.addEventListener("click", function () {
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      storeTheme(next);
      sync();
      charts.forEach(function (c) { c.render && c.render(); });
    });
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
        sync();
        charts.forEach(function (c) { c.render && c.render(); });
      });
    }
    sync();
  }

  /* ------------------------------------------------------------------ start */

  document.getElementById("snapshot-date").textContent = data.snapshot;
  renderNav();
  setupTheme();
  renderPage(false);
  window.addEventListener("hashchange", function () { renderPage(true); });
})();
