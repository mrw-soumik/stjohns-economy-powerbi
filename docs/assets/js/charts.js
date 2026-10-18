/*
 * Chart components for the web version, built on D3 7.9.0 (docs/assets/vendor).
 * Conventions: one y axis per chart; 2 px lines; solid hairline gridlines; bars at most
 * 24 px thick with a 4 px rounded data end; 2 px surface gaps between stacked segments;
 * a legend for two or more series plus direct end labels; tooltips that list every series;
 * the same readout on keyboard focus; and a table view for every chart.
 * Colours come from CSS custom properties so each theme uses its own validated steps.
 * All text is inserted with textContent.
 */
(function (root) {
  "use strict";
  var d3 = root.d3;

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "class") node.className = attrs[k];
        else node.setAttribute(k, attrs[k]);
      });
    }
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  var counter = 0;
  function uid(prefix) { counter += 1; return prefix + "-" + counter; }

  /* ------------------------------------------------------------------ figure scaffold */

  function figure(parent, opts) {
    var fig = el("figure", { "class": "card chart", id: opts.id });
    var cap = el("figcaption");
    cap.appendChild(el("h3", null, opts.title));
    if (opts.subtitle) cap.appendChild(el("p", null, opts.subtitle));
    fig.appendChild(cap);
    var legend = el("ul", { "class": "legend", "aria-label": "Legend" });
    fig.appendChild(legend);
    var plot = el("div", { "class": "plot", tabindex: "0", role: "group",
      "aria-label": opts.alt + " " + (opts.keyHint || "") });
    fig.appendChild(plot);
    var tooltip = el("div", { "class": "tooltip", hidden: "" });
    plot.appendChild(tooltip);
    var live = el("p", { "class": "visually-hidden", "aria-live": "polite" });
    fig.appendChild(live);
    if (opts.note) fig.appendChild(el("p", { "class": "chart-note" }, opts.note));
    var actions = el("div", { "class": "chart-actions" });
    var tableId = uid("table");
    var btn = el("button", { "class": "btn", type: "button", "aria-expanded": "false", "aria-controls": tableId }, "Show table");
    actions.appendChild(btn);
    fig.appendChild(actions);
    var region = el("div", { "class": "table-region", id: tableId, role: "region", tabindex: "0",
      "aria-label": "Table: " + opts.title, hidden: "" });
    fig.appendChild(region);
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", open ? "false" : "true");
      btn.textContent = open ? "Show table" : "Hide table";
      if (open) region.setAttribute("hidden", ""); else region.removeAttribute("hidden");
    });
    parent.appendChild(fig);
    return { fig: fig, legend: legend, plot: plot, tooltip: tooltip, live: live, region: region };
  }

  function renderLegend(list, items) {
    list.textContent = "";
    if (items.length < 2) { list.setAttribute("hidden", ""); return; }
    list.removeAttribute("hidden");
    items.forEach(function (item) {
      var li = el("li");
      var key = el("span", { "class": item.kind === "rect" ? "key-rect" : item.kind === "band" ? "key-band" : "key-line",
        "aria-hidden": "true" });
      key.style.background = item.kind === "band" ? cssVar("--band") : cssVar(item.colourVar);
      if (item.kind === "band") key.style.border = "1px solid " + cssVar("--bound");
      li.appendChild(key);
      li.appendChild(document.createTextNode(item.label));
      list.appendChild(li);
    });
  }

  function renderTable(region, caption, columns, rows) {
    region.textContent = "";
    var table = el("table", { "class": "data" });
    table.appendChild(el("caption", null, caption));
    var thead = el("thead");
    var tr = el("tr");
    columns.forEach(function (c) { tr.appendChild(el("th", { scope: "col" }, c)); });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (r) {
      var row = el("tr");
      r.forEach(function (cell, i) { row.appendChild(el(i === 0 ? "th" : "td", i === 0 ? { scope: "row" } : null, cell)); });
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    region.appendChild(table);
  }

  function showTooltip(refs, header, rows, x, y) {
    var tt = refs.tooltip;
    tt.textContent = "";
    tt.appendChild(el("div", { "class": "tt-head" }, header));
    rows.forEach(function (r) {
      var row = el("div", { "class": "tt-row" });
      if (r.colourVar) {
        var key = el("span", { "class": r.kind === "rect" ? "key-rect" : "key-line", "aria-hidden": "true" });
        key.style.background = cssVar(r.colourVar);
        row.appendChild(key);
      }
      row.appendChild(el("span", { "class": "tt-value" }, r.value));
      row.appendChild(el("span", { "class": "tt-label" }, r.label));
      tt.appendChild(row);
    });
    tt.removeAttribute("hidden");
    var plotW = refs.plot.clientWidth;
    var w = tt.offsetWidth, h = tt.offsetHeight;
    var left = x + 14 + w > plotW ? Math.max(0, x - 14 - w) : x + 14;
    var top = Math.max(0, y - h - 8);
    tt.style.left = left + "px";
    tt.style.top = top + "px";
  }

  function hideTooltip(refs) { refs.tooltip.setAttribute("hidden", ""); }

  function announce(refs, header, rows) {
    clearTimeout(refs._announce);
    refs._announce = setTimeout(function () {
      refs.live.textContent = header + ": " + rows.map(function (r) { return r.label + " " + r.value; }).join("; ");
    }, 120);
  }

  function textWidth(text, size) { return String(text).length * (size || 11) * 0.58; }

  function svgRoot(refs, width, height) {
    d3.select(refs.plot).selectAll("svg").remove();
    return d3.select(refs.plot).insert("svg", ".tooltip")
      .attr("viewBox", "0 0 " + width + " " + height)
      .attr("width", width).attr("height", height)
      .attr("aria-hidden", "true").attr("focusable", "false");
  }

  function observe(refs, render) {
    var lastWidth = 0, timer = null;
    var ro = new ResizeObserver(function () {
      var w = refs.plot.clientWidth;
      if (Math.abs(w - lastWidth) < 2) return;
      lastWidth = w;
      clearTimeout(timer);
      timer = setTimeout(render, 60);
    });
    ro.observe(refs.plot);
    lastWidth = refs.plot.clientWidth;
    render();
    return ro;
  }

  function chartHeight(width) { return width < 420 ? 240 : 290; }

  function parseDate(iso) { return new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10))); }

  /* ------------------------------------------------------------------ line chart */

  function lineChart(parent, cfg) {
    var refs = figure(parent, { id: cfg.id, title: cfg.title, subtitle: cfg.subtitle, note: cfg.note, alt: cfg.alt,
      keyHint: "Use the left and right arrow keys to read values month by month." });
    var series = cfg.series.filter(function (s) { return s.points.length; });
    var legendItems = series.map(function (s) { return { label: s.label, colourVar: s.colourVar, kind: "line" }; });
    if (cfg.band) legendItems.push({ label: cfg.band.label, colourVar: "--bound", kind: "band" });
    renderLegend(refs.legend, legendItems);

    var dates = Array.from(new Set([].concat.apply([], series.map(function (s) {
      return s.points.map(function (p) { return p.date; });
    })))).sort();
    var byDate = series.map(function (s) {
      var m = {};
      s.points.forEach(function (p) { m[p.date] = p.value; });
      return m;
    });
    var bandByDate = {};
    if (cfg.band) cfg.band.points.forEach(function (p) { bandByDate[p.date] = p; });

    var columns = ["Month"].concat(series.map(function (s) { return s.label; }));
    if (cfg.band) columns = columns.concat(["Lower 95% bound", "Upper 95% bound"]);
    var rows = dates.slice().reverse().map(function (d) {
      var row = [cfg.dateLabel(d)].concat(byDate.map(function (m) { return m[d] === undefined ? "" : cfg.format(m[d]); }));
      if (cfg.band) {
        var b = bandByDate[d];
        row = row.concat([b && b.lower !== null ? cfg.format(b.lower) : "", b && b.upper !== null ? cfg.format(b.upper) : ""]);
      }
      return row;
    });
    renderTable(refs.region, cfg.title + ", by month (latest first)", columns, rows);

    if (!dates.length) {
      refs.plot.appendChild(el("p", { "class": "chart-note" }, "No data for the current selection."));
      return refs;
    }

    var activeIndex = null;

    function render() {
      var width = Math.max(260, refs.plot.clientWidth);
      var height = chartHeight(width);
      var all = [];
      series.forEach(function (s) { s.points.forEach(function (p) { if (p.value !== null) all.push(p.value); }); });
      if (cfg.band) cfg.band.points.forEach(function (p) { if (p.upper !== null) { all.push(p.upper); all.push(p.lower); } });
      var y = d3.scaleLinear().domain(d3.extent(all)).nice(5);
      var yTicks = y.ticks(5);
      var left = 10 + d3.max(yTicks, function (t) { return textWidth(cfg.axisFormat(t)); });
      var right = 14 + Math.min(110, d3.max(series, function (s) { return textWidth(s.label); }) || 0);
      var margin = { top: 10, right: right, bottom: 26, left: left };
      var innerW = width - margin.left - margin.right, innerH = height - margin.top - margin.bottom;
      var x = d3.scaleUtc().domain([parseDate(dates[0]), parseDate(dates[dates.length - 1])]).range([0, innerW]);
      y.range([innerH, 0]);

      var svg = svgRoot(refs, width, height);
      var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");

      g.selectAll("line.grid").data(yTicks).join("line")
        .attr("x1", 0).attr("x2", innerW).attr("y1", y).attr("y2", y)
        .attr("stroke", function (t) { return t === 0 && y.domain()[0] < 0 ? cssVar("--axis") : cssVar("--grid"); })
        .attr("stroke-width", 1).attr("shape-rendering", "crispEdges");
      g.selectAll("text.y").data(yTicks).join("text").attr("class", "axis-label")
        .attr("x", -8).attr("y", function (t) { return y(t) + 4; }).attr("text-anchor", "end")
        .text(function (t) { return cfg.axisFormat(t); });

      var years = (parseDate(dates[dates.length - 1]).getUTCFullYear() - parseDate(dates[0]).getUTCFullYear()) || 1;
      var step = Math.max(1, Math.ceil(years / Math.max(2, Math.floor(innerW / 56))));
      var xTicks = x.ticks(d3.utcYear.every(step));
      g.append("line").attr("x1", 0).attr("x2", innerW).attr("y1", innerH).attr("y2", innerH)
        .attr("stroke", cssVar("--axis")).attr("stroke-width", 1).attr("shape-rendering", "crispEdges");
      g.selectAll("text.x").data(xTicks).join("text").attr("class", "axis-label")
        .attr("x", x).attr("y", innerH + 18).attr("text-anchor", "middle")
        .text(function (t) { return t.getUTCFullYear(); });

      if (cfg.band) {
        var bandPts = cfg.band.points.filter(function (p) { return p.upper !== null; });
        g.append("path").datum(bandPts)
          .attr("fill", cssVar("--band"))
          .attr("d", d3.area().x(function (p) { return x(parseDate(p.date)); })
            .y0(function (p) { return y(p.lower); }).y1(function (p) { return y(p.upper); }));
        ["upper", "lower"].forEach(function (k) {
          g.append("path").datum(bandPts).attr("fill", "none").attr("stroke", cssVar("--bound")).attr("stroke-width", 1)
            .attr("d", d3.line().x(function (p) { return x(parseDate(p.date)); }).y(function (p) { return y(p[k]); }));
        });
      }

      series.forEach(function (s) {
        g.append("path").datum(s.points)
          .attr("fill", "none").attr("stroke", cssVar(s.colourVar)).attr("stroke-width", 2)
          .attr("stroke-linejoin", "round").attr("stroke-linecap", "round")
          .attr("d", d3.line().defined(function (p) { return p.value !== null; })
            .x(function (p) { return x(parseDate(p.date)); }).y(function (p) { return y(p.value); }));
      });

      /* direct end labels; collisions resolved with leader lines rather than silent nudges */
      var ends = series.map(function (s) {
        var last = s.points[s.points.length - 1];
        return { label: s.label, x: x(parseDate(last.date)), y: y(last.value), ly: y(last.value) };
      }).sort(function (a, b) { return a.y - b.y; });
      for (var i = 1; i < ends.length; i++) {
        if (ends[i].ly - ends[i - 1].ly < 14) ends[i].ly = ends[i - 1].ly + 14;
      }
      var overflow = ends.length ? ends[ends.length - 1].ly - (innerH - 4) : 0;
      if (overflow > 0) ends.forEach(function (e) { e.ly -= overflow; });
      ends.forEach(function (e) {
        var moved = Math.abs(e.ly - e.y) > 3;
        if (moved) {
          g.append("line").attr("x1", e.x + 2).attr("y1", e.y).attr("x2", e.x + 8).attr("y2", e.ly)
            .attr("stroke", cssVar("--muted")).attr("stroke-width", 1);
        }
        g.append("text").attr("class", "end-label").attr("x", e.x + (moved ? 10 : 6)).attr("y", e.ly + 4).text(e.label);
      });

      /* hover layer: crosshair snaps to the nearest month and lists every series */
      var cross = g.append("line").attr("y1", 0).attr("y2", innerH).attr("stroke", cssVar("--muted"))
        .attr("stroke-width", 1).style("display", "none");
      var dots = g.append("g").style("display", "none");
      var xs = dates.map(function (d) { return x(parseDate(d)); });

      function focusIndex(idx) {
        if (idx === null) return;
        activeIndex = idx;
        var d = dates[idx];
        var cx = xs[idx];
        cross.attr("x1", cx).attr("x2", cx).style("display", null);
        dots.style("display", null).selectAll("circle").data(series).join("circle")
          .attr("r", 4).attr("cx", cx)
          .attr("cy", function (s, si) { var v = byDate[si][d]; return v === undefined ? -100 : y(v); })
          .attr("fill", function (s) { return cssVar(s.colourVar); })
          .attr("stroke", cssVar("--surface")).attr("stroke-width", 2)
          .style("display", function (s, si) { return byDate[si][d] === undefined ? "none" : null; });
        var rows = series.map(function (s, si) {
          var v = byDate[si][d];
          return { label: s.label, value: v === undefined ? "no data" : cfg.format(v), colourVar: s.colourVar };
        });
        if (cfg.band && bandByDate[d] && bandByDate[d].upper !== null) {
          rows.push({ label: "95% range", value: cfg.format(bandByDate[d].lower) + " to " + cfg.format(bandByDate[d].upper) });
        }
        var top = d3.min(series, function (s, si) { var v = byDate[si][d]; return v === undefined ? innerH : y(v); });
        showTooltip(refs, cfg.dateLabel(d), rows, margin.left + cx, margin.top + top);
        announce(refs, cfg.dateLabel(d), rows);
      }
      function clear() { cross.style("display", "none"); dots.style("display", "none"); hideTooltip(refs); }

      g.append("rect").attr("width", innerW).attr("height", innerH).attr("fill", "transparent")
        .style("cursor", "crosshair")
        .on("pointermove", function (event) {
          var mx = d3.pointer(event)[0];
          var idx = d3.bisector(function (v) { return v; }).center(xs, mx);
          focusIndex(idx);
        })
        .on("pointerleave", function () { if (document.activeElement !== refs.plot) clear(); });

      refs.plot.onfocus = function () { focusIndex(activeIndex === null ? dates.length - 1 : activeIndex); };
      refs.plot.onblur = clear;
      refs.plot.onkeydown = function (event) {
        var idx = activeIndex === null ? dates.length - 1 : activeIndex;
        var moves = { ArrowLeft: -1, ArrowRight: 1, PageUp: -12, PageDown: 12 };
        if (moves[event.key] !== undefined) idx = Math.min(dates.length - 1, Math.max(0, idx + moves[event.key]));
        else if (event.key === "Home") idx = 0;
        else if (event.key === "End") idx = dates.length - 1;
        else if (event.key === "Escape") { clear(); return; }
        else return;
        event.preventDefault();
        focusIndex(idx);
      };
      if (document.activeElement === refs.plot && activeIndex !== null) focusIndex(activeIndex);
    }

    refs.render = render;
    refs.observer = observe(refs, render);
    return refs;
  }

  /* ------------------------------------------------------------------ bar and column charts */

  function roundedBar(x0, x1, y0, y1, radius, horizontal) {
    /* rectangle with the data end rounded and the baseline end square */
    var w = Math.abs(x1 - x0), h = Math.abs(y1 - y0);
    var r = Math.min(radius, horizontal ? w : h, horizontal ? h / 2 : w / 2);
    if (horizontal) {
      var positive = x1 >= x0, top = Math.min(y0, y1), bottom = Math.max(y0, y1);
      if (positive) return "M" + x0 + "," + top + "H" + (x1 - r) + "Q" + x1 + "," + top + " " + x1 + "," + (top + r) +
        "V" + (bottom - r) + "Q" + x1 + "," + bottom + " " + (x1 - r) + "," + bottom + "H" + x0 + "Z";
      return "M" + x0 + "," + top + "H" + (x1 + r) + "Q" + x1 + "," + top + " " + x1 + "," + (top + r) +
        "V" + (bottom - r) + "Q" + x1 + "," + bottom + " " + (x1 + r) + "," + bottom + "H" + x0 + "Z";
    }
    var up = y1 <= y0, left = Math.min(x0, x1), right = Math.max(x0, x1);
    if (up) return "M" + left + "," + y0 + "V" + (y1 + r) + "Q" + left + "," + y1 + " " + (left + r) + "," + y1 +
      "H" + (right - r) + "Q" + right + "," + y1 + " " + right + "," + (y1 + r) + "V" + y0 + "Z";
    return "M" + left + "," + y0 + "V" + (y1 - r) + "Q" + left + "," + y1 + " " + (left + r) + "," + y1 +
      "H" + (right - r) + "Q" + right + "," + y1 + " " + right + "," + (y1 - r) + "V" + y0 + "Z";
  }

  /* Horizontal clustered bars: categories down the side, one bar per series. */
  function barChart(parent, cfg) {
    var refs = figure(parent, { id: cfg.id, title: cfg.title, subtitle: cfg.subtitle, note: cfg.note, alt: cfg.alt,
      keyHint: "Use the up and down arrow keys to read each bar." });
    renderLegend(refs.legend, cfg.series.map(function (s) { return { label: s.label, colourVar: s.colourVar, kind: "rect" }; }));
    renderTable(refs.region, cfg.title, ["Category"].concat(cfg.series.map(function (s) { return s.label; })),
      cfg.categories.map(function (c) {
        return [c.label].concat(cfg.series.map(function (s) { var v = cfg.value(c.key, s.key); return v === null ? "not published" : cfg.format(v); }));
      }));
    var bars = [];
    cfg.categories.forEach(function (c) { cfg.series.forEach(function (s) { bars.push({ c: c, s: s, v: cfg.value(c.key, s.key) }); }); });
    var active = null;

    function render() {
      var width = Math.max(260, refs.plot.clientWidth);
      var labelW = Math.min(150, 12 + d3.max(cfg.categories, function (c) { return textWidth(c.label); }));
      var values = bars.filter(function (b) { return b.v !== null; }).map(function (b) { return b.v; }).concat([0]);
      var margin = { top: 6, right: 52, bottom: 24, left: labelW };
      var tickCount = Math.max(2, Math.min(6, Math.floor((width - labelW - 52) / 72)));
      var x = d3.scaleLinear().domain(d3.extent(values)).nice(tickCount);
      var groupH = Math.min(cfg.series.length * 18 + 14, 80);
      var height = margin.top + margin.bottom + cfg.categories.length * groupH;
      var innerW = width - margin.left - margin.right, innerH = height - margin.top - margin.bottom;
      x.range([0, innerW]);
      var yc = d3.scaleBand().domain(cfg.categories.map(function (c) { return c.key; })).range([0, innerH]).paddingInner(0.25).paddingOuter(0.1);
      var ys = d3.scaleBand().domain(cfg.series.map(function (s) { return s.key; })).range([0, yc.bandwidth()]).padding(0);
      var thick = Math.min(24, ys.bandwidth() - 2);

      var svg = svgRoot(refs, width, height);
      var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
      var ticks = x.ticks(tickCount);
      g.selectAll("line.grid").data(ticks).join("line").attr("x1", x).attr("x2", x).attr("y1", 0).attr("y2", innerH)
        .attr("stroke", function (t) { return t === 0 ? cssVar("--axis") : cssVar("--grid"); }).attr("stroke-width", 1)
        .attr("shape-rendering", "crispEdges");
      g.selectAll("text.x").data(ticks).join("text").attr("class", "axis-label").attr("x", x).attr("y", innerH + 16)
        .attr("text-anchor", "middle").text(function (t) { return cfg.axisFormat(t); });
      g.selectAll("text.cat").data(cfg.categories).join("text").attr("class", "axis-label")
        .attr("x", -10).attr("y", function (c) { return yc(c.key) + yc.bandwidth() / 2 + 4; }).attr("text-anchor", "end")
        .text(function (c) { return c.label; });

      var marks = g.selectAll("path.bar").data(bars).join("path").attr("class", "bar")
        .attr("fill", function (b) { return cssVar(b.s.colourVar); })
        .attr("d", function (b) {
          if (b.v === null) return null;
          var top = yc(b.c.key) + ys(b.s.key) + (ys.bandwidth() - thick) / 2;
          return roundedBar(x(0), x(b.v), top, top + thick, 4, true);
        });
      g.selectAll("text.val").data(bars.filter(function (b) { return b.v !== null; })).join("text").attr("class", "value-label")
        .attr("x", function (b) { return b.v >= 0 ? x(b.v) + 4 : x(b.v) - 4; })
        .attr("text-anchor", function (b) { return b.v >= 0 ? "start" : "end"; })
        .attr("y", function (b) { return yc(b.c.key) + ys(b.s.key) + ys.bandwidth() / 2 + 4; })
        .text(function (b) { return cfg.format(b.v); });

      function focusBar(i) {
        active = i;
        var b = bars[i];
        marks.attr("opacity", function (o, j) { return j === i ? 1 : 0.45; });
        var rows = [{ label: b.s.label, value: b.v === null ? "not published" : cfg.format(b.v), colourVar: b.s.colourVar, kind: "rect" }];
        var ty = yc(b.c.key) + ys(b.s.key);
        showTooltip(refs, b.c.label, rows, margin.left + (b.v === null ? 0 : Math.max(x(0), x(b.v))), margin.top + ty);
        announce(refs, b.c.label, rows);
      }
      function clear() { marks.attr("opacity", 1); hideTooltip(refs); }
      marks.on("pointerenter", function (event, b) { focusBar(bars.indexOf(b)); })
        .on("pointerleave", function () { if (document.activeElement !== refs.plot) clear(); });
      refs.plot.onfocus = function () { focusBar(active === null ? 0 : active); };
      refs.plot.onblur = clear;
      refs.plot.onkeydown = function (event) {
        var i = active === null ? 0 : active;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") i = Math.min(bars.length - 1, i + 1);
        else if (event.key === "ArrowUp" || event.key === "ArrowLeft") i = Math.max(0, i - 1);
        else if (event.key === "Home") i = 0;
        else if (event.key === "End") i = bars.length - 1;
        else if (event.key === "Escape") { clear(); return; }
        else return;
        event.preventDefault();
        focusBar(i);
      };
    }
    refs.render = render;
    refs.observer = observe(refs, render);
    return refs;
  }

  /* Vertical columns by category (years): stacked or clustered. */
  function columnChart(parent, cfg) {
    var refs = figure(parent, { id: cfg.id, title: cfg.title, subtitle: cfg.subtitle, note: cfg.note, alt: cfg.alt,
      keyHint: "Use the left and right arrow keys to read each year." });
    renderLegend(refs.legend, cfg.series.map(function (s) { return { label: s.label, colourVar: s.colourVar, kind: "rect" }; }));
    var columns = ["Year"].concat(cfg.series.map(function (s) { return s.label; }));
    if (cfg.stacked) columns.push("Total");
    renderTable(refs.region, cfg.title, columns, cfg.categories.map(function (c) {
      var vals = cfg.series.map(function (s) { return cfg.value(c.key, s.key); });
      var row = [c.label].concat(vals.map(function (v) { return v === null ? "" : cfg.format(v); }));
      if (cfg.stacked) row.push(cfg.format(vals.reduce(function (a, v) { return a + (v || 0); }, 0)));
      return row;
    }));
    var active = null;

    function render() {
      var width = Math.max(260, refs.plot.clientWidth);
      var height = chartHeight(width);
      var totals = cfg.categories.map(function (c) {
        return cfg.series.reduce(function (a, s) { return a + Math.max(0, cfg.value(c.key, s.key) || 0); }, 0);
      });
      var vals = [];
      cfg.categories.forEach(function (c) { cfg.series.forEach(function (s) { var v = cfg.value(c.key, s.key); if (v !== null) vals.push(v); }); });
      var domain = cfg.stacked ? [0, d3.max(totals) || 1] : d3.extent(vals.concat([0]));
      var y = d3.scaleLinear().domain(domain).nice(5);
      var yTicks = y.ticks(5);
      var margin = { top: 10, right: 8, bottom: 26, left: 10 + d3.max(yTicks, function (t) { return textWidth(cfg.axisFormat(t)); }) };
      var innerW = width - margin.left - margin.right, innerH = height - margin.top - margin.bottom;
      y.range([innerH, 0]);
      var x = d3.scaleBand().domain(cfg.categories.map(function (c) { return c.key; })).range([0, innerW]).paddingInner(0.3).paddingOuter(0.15);

      var svg = svgRoot(refs, width, height);
      var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
      g.selectAll("line.grid").data(yTicks).join("line").attr("x1", 0).attr("x2", innerW).attr("y1", y).attr("y2", y)
        .attr("stroke", function (t) { return t === 0 ? cssVar("--axis") : cssVar("--grid"); }).attr("stroke-width", 1)
        .attr("shape-rendering", "crispEdges");
      g.selectAll("text.y").data(yTicks).join("text").attr("class", "axis-label").attr("x", -8)
        .attr("y", function (t) { return y(t) + 4; }).attr("text-anchor", "end").text(function (t) { return cfg.axisFormat(t); });
      var every = Math.max(1, Math.ceil(cfg.categories.length / Math.max(2, Math.floor(innerW / 40))));
      g.selectAll("text.x").data(cfg.categories.filter(function (c, i) { return i % every === 0; })).join("text")
        .attr("class", "axis-label").attr("x", function (c) { return x(c.key) + x.bandwidth() / 2; })
        .attr("y", innerH + 18).attr("text-anchor", "middle").text(function (c) { return c.label; });

      var highlight = g.append("rect").attr("fill", cssVar("--grid")).attr("opacity", 0.5).style("display", "none")
        .attr("y", 0).attr("height", innerH);
      var segments = [];
      cfg.categories.forEach(function (c) {
        if (cfg.stacked) {
          var cum = 0, w = Math.min(24, x.bandwidth()), x0 = x(c.key) + (x.bandwidth() - w) / 2;
          var present = cfg.series.filter(function (s) { return (cfg.value(c.key, s.key) || 0) > 0; });
          present.forEach(function (s, si) {
            var v = cfg.value(c.key, s.key);
            var y0 = y(cum) - (si > 0 ? 2 : 0), y1 = y(cum + v);
            cum += v;
            var last = si === present.length - 1;
            segments.push({ c: c, s: s, d: last ? roundedBar(x0, x0 + w, y0, y1, 4, false)
              : "M" + x0 + "," + y0 + "V" + y1 + "H" + (x0 + w) + "V" + y0 + "Z" });
          });
        } else {
          var xs = d3.scaleBand().domain(cfg.series.map(function (s) { return s.key; })).range([0, x.bandwidth()]);
          var bw = Math.min(24, xs.bandwidth() - 2);
          cfg.series.forEach(function (s) {
            var v = cfg.value(c.key, s.key);
            if (v === null) return;
            var bx = x(c.key) + xs(s.key) + (xs.bandwidth() - bw) / 2;
            segments.push({ c: c, s: s, d: roundedBar(bx, bx + bw, y(0), y(v), 4, false) });
          });
        }
      });
      g.selectAll("path.seg").data(segments).join("path").attr("class", "seg")
        .attr("fill", function (sg) { return cssVar(sg.s.colourVar); }).attr("d", function (sg) { return sg.d; });

      function focusCat(i) {
        active = i;
        var c = cfg.categories[i];
        highlight.style("display", null).attr("x", x(c.key) - x.step() * x.paddingInner() / 2).attr("width", x.step());
        var rows = cfg.series.map(function (s) {
          var v = cfg.value(c.key, s.key);
          return { label: s.label, value: v === null ? "no data" : cfg.format(v), colourVar: s.colourVar, kind: "rect" };
        });
        if (cfg.stacked) {
          rows.push({ label: "Total", value: cfg.format(cfg.series.reduce(function (a, s) { return a + (cfg.value(c.key, s.key) || 0); }, 0)) });
        }
        showTooltip(refs, c.label + (c.note ? " (" + c.note + ")" : ""), rows, margin.left + x(c.key) + x.bandwidth(), margin.top + 20);
        announce(refs, c.label, rows);
      }
      function clear() { highlight.style("display", "none"); hideTooltip(refs); }
      g.append("rect").attr("width", innerW).attr("height", innerH).attr("fill", "transparent")
        .on("pointermove", function (event) {
          var mx = d3.pointer(event)[0];
          var i = Math.max(0, Math.min(cfg.categories.length - 1, Math.floor((mx - x.paddingOuter() * x.step()) / x.step())));
          focusCat(i);
        })
        .on("pointerleave", function () { if (document.activeElement !== refs.plot) clear(); });
      refs.plot.onfocus = function () { focusCat(active === null ? cfg.categories.length - 1 : active); };
      refs.plot.onblur = clear;
      refs.plot.onkeydown = function (event) {
        var i = active === null ? cfg.categories.length - 1 : active;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") i = Math.min(cfg.categories.length - 1, i + 1);
        else if (event.key === "ArrowLeft" || event.key === "ArrowUp") i = Math.max(0, i - 1);
        else if (event.key === "Home") i = 0;
        else if (event.key === "End") i = cfg.categories.length - 1;
        else if (event.key === "Escape") { clear(); return; }
        else return;
        event.preventDefault();
        focusCat(i);
      };
    }
    refs.render = render;
    refs.observer = observe(refs, render);
    return refs;
  }

  /* ------------------------------------------------------------------ KPI card */

  function kpiCard(parent, cfg) {
    var card = el("article", { "class": "card kpi", id: cfg.id, "aria-labelledby": cfg.id + "-title" });
    card.appendChild(el("h3", { id: cfg.id + "-title" }, cfg.title));
    if (cfg.period) card.appendChild(el("p", { "class": "kpi-period" }, cfg.period));
    card.appendChild(el("p", { "class": "kpi-value" }, cfg.value || "not available"));
    if (cfg.delta) card.appendChild(el("p", { "class": "kpi-delta tone-" + cfg.delta.tone }, cfg.delta.text));
    parent.appendChild(card);
    return card;
  }

  root.SJCharts = { lineChart: lineChart, barChart: barChart, columnChart: columnChart, kpiCard: kpiCard, el: el };
})(window);
