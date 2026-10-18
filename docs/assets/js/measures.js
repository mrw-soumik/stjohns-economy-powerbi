/*
 * St. John's Economy and Housing Dashboard: measure functions for the web version.
 * Each function mirrors a DAX measure in powerbi/measures.dax; tests/web/check_measures.cjs
 * checks the results against powerbi/check-query-expected.csv.
 * Dates are ISO strings: "YYYY-MM-01" for monthly data, "YYYY-07-01" for annual population.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.SJMeasures = factory();
  }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December"];
  var MINUS = "−";

  function addMonths(iso, n) {
    var y = +iso.slice(0, 4);
    var m = +iso.slice(5, 7) - 1;
    var total = y * 12 + m + n;
    var ny = Math.floor(total / 12);
    var nm = total - ny * 12 + 1;
    return ny + "-" + (nm < 10 ? "0" : "") + nm + "-" + iso.slice(8, 10);
  }

  /* DAX ROUND: half away from zero. toFixed(6) on the scaled value removes binary noise. */
  function roundHalfAway(x, digits) {
    var f = Math.pow(10, digits);
    var scaled = Number((Math.abs(x) * f).toFixed(6));
    return (x < 0 ? -1 : 1) * Math.round(scaled) / f;
  }

  function monthLabel(iso) { return MONTHS[+iso.slice(5, 7) - 1] + " " + iso.slice(0, 4); }
  function monthLabelLong(iso) { return MONTHS_LONG[+iso.slice(5, 7) - 1] + " " + iso.slice(0, 4); }
  function periodLabel(iso, frequency) {
    if (!iso) return "";
    if (frequency === "Annual") return MONTHS_LONG[+iso.slice(5, 7) - 1] + " " + (+iso.slice(8, 10)) + ", " + iso.slice(0, 4);
    return monthLabelLong(iso);
  }

  /* Number formatting that follows the Power BI format strings in DimIndicator. */
  var grouping = typeof Intl !== "undefined" ? new Intl.NumberFormat("en-CA") : null;
  function group(x, decimals) {
    var fixed = Math.abs(x).toFixed(decimals);
    var parts = fixed.split(".");
    var whole = grouping ? grouping.format(+parts[0]) : parts[0];
    return whole + (parts.length > 1 ? "." + parts[1] : "");
  }
  function sign(x, text) { return (x < 0 ? MINUS : "") + text; }
  function formatByString(x, format) {
    if (x === null || x === undefined || isNaN(x)) return "";
    var match = /^(#,)?0(?:\.(0+))?(?:"(.*)")?$/.exec(format || "#,0.0");
    var decimals = match && match[2] ? match[2].length : 0;
    var suffix = match && match[3] ? match[3] : "";
    var body = match && match[1] ? group(x, decimals) : Math.abs(x).toFixed(decimals);
    return sign(x, body) + suffix;
  }
  function signedPercent(ratio) {
    if (ratio === null || ratio === undefined) return "";
    var r = roundHalfAway(ratio * 100, 1);
    return (r > 0 ? "+" : r < 0 ? MINUS : "") + Math.abs(r).toFixed(1) + "%";
  }
  function signedPoints(x) {
    if (x === null || x === undefined) return "";
    var r = roundHalfAway(x, 1);
    return (r > 0 ? "+" : r < 0 ? MINUS : "") + Math.abs(r).toFixed(1) + " pts";
  }

  function create(data) {
    var indicators = {};
    data.indicators.forEach(function (i) { indicators[i.code] = i; });
    var geographies = {};
    data.geographies.forEach(function (g) { geographies[g.code] = g; });
    var index = {};
    Object.keys(data.series).forEach(function (key) {
      var s = data.series[key];
      var map = {};
      s.dates.forEach(function (d, i) { map[d] = s.values[i]; });
      index[key] = { map: map, dates: s.dates, values: s.values, status: s.status, vector: s.vector, table: s.table };
    });

    function get(ind, geo) { return index[ind + "|" + geo] || null; }
    function meta(ind) { return indicators[ind]; }
    function valueAt(ind, geo, date) {
      var s = get(ind, geo);
      if (!s || !date) return null;
      var v = s.map[date];
      return v === undefined ? null : v;
    }
    function inRange(d, range) {
      return (!range || !range.from || d >= range.from) && (!range || !range.to || d <= range.to);
    }

    /* [Latest Date]: latest period with data inside the date range. */
    function latestDate(ind, geo, range) {
      var s = get(ind, geo);
      if (!s) return null;
      for (var i = s.dates.length - 1; i >= 0; i--) {
        if (inRange(s.dates[i], range)) return s.dates[i];
      }
      return null;
    }
    function points(ind, geo, range) {
      var s = get(ind, geo);
      if (!s) return [];
      var out = [];
      s.dates.forEach(function (d, i) { if (inRange(d, range)) out.push({ date: d, value: s.values[i] }); });
      return out;
    }

    /* [Value Year Ago], [YoY Change], [YoY %] at a given period. */
    function yoyAt(ind, geo, date) {
      var v = valueAt(ind, geo, date);
      var p = valueAt(ind, geo, date ? addMonths(date, -12) : null);
      if (v === null || p === null) return { date: date, value: v, prior: p, change: null, pct: null };
      return { date: date, value: v, prior: p, change: v - p, pct: v / p - 1 };
    }
    function yoy(ind, geo, range) { return yoyAt(ind, geo, latestDate(ind, geo, range)); }
    function yoySeries(ind, geo, range) {
      return points(ind, geo, range).map(function (pt) { return { date: pt.date, value: yoyAt(ind, geo, pt.date).pct }; })
        .filter(function (pt) { return pt.value !== null; });
    }

    /* [YoY Headline Change]: points for rates, ratio otherwise. */
    function headline(ind, geo, range) {
      var y = yoy(ind, geo, range);
      if (y.change === null) return null;
      return meta(ind).changeType === "Points" ? y.change : y.pct;
    }

    /* [Gap vs Canada (Display)] at the same period as the geography in context. */
    function gapVsCanada(ind, geo, range) {
      var y = yoy(ind, geo, range);
      if (!y.date || y.value === null) return null;
      var ca = valueAt(ind, "CA", y.date);
      if (ca === null) return null;
      if (meta(ind).changeType === "Points") return y.value - ca;
      var caPrior = valueAt(ind, "CA", addMonths(y.date, -12));
      if (caPrior === null || y.pct === null) return null;
      return (y.pct - (ca / caPrior - 1)) * 100;
    }

    /* [12-Month Rolling Total] / [12-Month Rolling Average]: blank unless 12 months exist. */
    function rolling12(ind, geo, date, how) {
      if (!date) return null;
      var total = 0;
      for (var k = 0; k < 12; k++) {
        var v = valueAt(ind, geo, addMonths(date, -k));
        if (v === null) return null;
        total += v;
      }
      return how === "average" ? total / 12 : total;
    }
    function rollingTotal(ind, geo, range) {
      var d = latestDate(ind, geo, range);
      return { date: d, value: rolling12(ind, geo, d, "sum") };
    }
    function rollingYoY(ind, geo, range) {
      var d = latestDate(ind, geo, range);
      var cur = rolling12(ind, geo, d, "sum");
      var prev = d ? rolling12(ind, geo, addMonths(d, -12), "sum") : null;
      return cur === null || prev === null ? null : cur / prev - 1;
    }

    /* [Base Date], [Index (Base = 100)]. */
    function baseDateFor(ind, baseMonth) {
      var m = meta(ind);
      if (m.frequency === "Annual" && m.referenceDay) return baseMonth.slice(0, 4) + "-" + m.referenceDay;
      return baseMonth;
    }
    function indexSeries(ind, geo, baseMonth, range) {
      var base = valueAt(ind, geo, baseDateFor(ind, baseMonth));
      if (base === null) return [];
      return points(ind, geo, range).map(function (pt) { return { date: pt.date, value: pt.value / base * 100 }; });
    }

    /* [Units Permitted per 1,000 Residents]: latest July 1 population on or before the month. */
    function perCapitaAt(geo, date) {
      var units = rolling12("BP_UNITS", geo, date, "sum");
      var pop = get("POP", geo);
      if (units === null || !pop) return null;
      var popDate = null;
      pop.dates.forEach(function (d) { if (d <= date) popDate = d; });
      return popDate ? units / pop.map[popDate] * 1000 : null;
    }
    function perCapita(geo, range) {
      var d = latestDate("BP_UNITS", geo, range);
      return { date: d, value: d ? perCapitaAt(geo, d) : null };
    }
    function perCapitaSeries(geo, range) {
      return points("BP_UNITS", geo, range).map(function (pt) { return { date: pt.date, value: perCapitaAt(geo, pt.date) }; })
        .filter(function (pt) { return pt.value !== null; });
    }

    /* Labour Force Survey precision: [Standard Error], [YoY Change Is Significant]. */
    function standardErrorAt(ind, geo, date) {
      var code = meta(ind).stdErrCode;
      return code ? valueAt(code, geo, date) : null;
    }
    function boundsSeries(ind, geo, range) {
      return points(ind, geo, range).map(function (pt) {
        var se = standardErrorAt(ind, geo, pt.date);
        return { date: pt.date, value: pt.value, upper: se === null ? null : pt.value + 1.96 * se,
          lower: se === null ? null : pt.value - 1.96 * se };
      });
    }
    function significance(ind, geo, range) {
      var code = meta(ind).stdErrYoYCode;
      if (!code) return null;
      var y = yoy(ind, geo, range);
      if (y.change === null) return null;
      var se = valueAt(code, geo, y.date);
      if (se === null) return null;
      return { se: se, margin: 1.96 * se, significant: Math.abs(y.change) > 1.96 * se };
    }

    /* Assessments: Favourable, Unfavourable, Neutral or Not significant. */
    function assess(change, direction, digits) {
      if (change === null || change === undefined) return null;
      var r = roundHalfAway(change, digits);
      if (r === 0 || direction === "Neutral") return "Neutral";
      if ((r > 0 && direction === "Higher is better") || (r < 0 && direction === "Lower is better")) return "Favourable";
      return "Unfavourable";
    }
    function yoyAssessment(ind, geo, range) {
      var h = headline(ind, geo, range);
      if (h === null) return null;
      var sig = significance(ind, geo, range);
      if (sig && !sig.significant) return "Not significant";
      return assess(h, meta(ind).direction, meta(ind).changeType === "Points" ? 1 : 3);
    }
    function gapAssessment(ind, geo, range) { return assess(gapVsCanada(ind, geo, range), meta(ind).direction, 1); }
    function rollingAssessment(ind, geo, range) { return assess(rollingYoY(ind, geo, range), meta(ind).direction, 3); }
    function tone(assessment) {
      return assessment === "Favourable" ? "good" : assessment === "Unfavourable" ? "bad" : "neutral";
    }
    function icon(change, digits) {
      if (change === null || change === undefined) return "";
      var r = roundHalfAway(change, digits);
      return r > 0 ? "▲" : r < 0 ? "▼" : "■";
    }

    /* Text labels that mirror the DAX display measures. */
    function yoyDelta(ind, geo, range) {
      var h = headline(ind, geo, range);
      if (h === null) return null;
      var m = meta(ind);
      var points = m.changeType === "Points";
      var y = yoy(ind, geo, range);
      var prior = addMonths(y.date, -12);
      var when = m.frequency === "Annual" ? prior.slice(0, 4) : monthLabel(prior);
      var assessment = yoyAssessment(ind, geo, range);
      return { text: icon(h, points ? 1 : 3) + " " + (points ? signedPoints(h) : signedPercent(h)) + " from " + when +
        " (" + assessment.toLowerCase() + ")", tone: tone(assessment) };
    }
    function gapDelta(ind, geo, range) {
      var gap = gapVsCanada(ind, geo, range);
      if (gap === null || geo === "CA") return null;
      var r = roundHalfAway(gap, 1);
      var suffix = meta(ind).changeType === "Points" ? "" : " (12-month change)";
      var text = r > 0 ? Math.abs(r).toFixed(1) + " pts above Canada" + suffix
        : r < 0 ? Math.abs(r).toFixed(1) + " pts below Canada" + suffix : "Same as Canada" + suffix;
      return { text: text, tone: tone(gapAssessment(ind, geo, range)) };
    }
    function rollingDelta(ind, geo, range) {
      var c = rollingYoY(ind, geo, range);
      if (c === null) return null;
      var assessment = rollingAssessment(ind, geo, range);
      return { text: icon(c, 3) + " " + signedPercent(c) + " vs previous 12 months (" + assessment.toLowerCase() + ")",
        tone: tone(assessment) };
    }
    function perCapitaDelta(geo, range) {
      var local = perCapita(geo, range).value;
      var canada = perCapita("CA", range).value;
      if (local === null || canada === null || geo === "CA") return null;
      var gap = roundHalfAway(local - canada, 1);
      var reference = " Canada (" + canada.toFixed(1) + ")";
      var text = gap > 0 ? gap.toFixed(1) + " above" + reference : gap < 0 ? Math.abs(gap).toFixed(1) + " below" + reference
        : "Same as" + reference;
      return { text: text, tone: gap > 0 ? "good" : gap < 0 ? "bad" : "neutral" };
    }

    return {
      indicators: indicators, geographies: geographies, get: get, meta: meta, valueAt: valueAt,
      latestDate: latestDate, points: points, yoy: yoy, yoyAt: yoyAt, yoySeries: yoySeries,
      headline: headline, gapVsCanada: gapVsCanada, rolling12: rolling12, rollingTotal: rollingTotal,
      rollingYoY: rollingYoY, indexSeries: indexSeries, baseDateFor: baseDateFor, perCapita: perCapita,
      perCapitaAt: perCapitaAt, perCapitaSeries: perCapitaSeries, boundsSeries: boundsSeries,
      significance: significance, yoyAssessment: yoyAssessment, gapAssessment: gapAssessment,
      rollingAssessment: rollingAssessment, yoyDelta: yoyDelta, gapDelta: gapDelta, rollingDelta: rollingDelta,
      perCapitaDelta: perCapitaDelta
    };
  }

  return {
    create: create, addMonths: addMonths, roundHalfAway: roundHalfAway, monthLabel: monthLabel,
    monthLabelLong: monthLabelLong, periodLabel: periodLabel, formatByString: formatByString,
    signedPercent: signedPercent, signedPoints: signedPoints, MINUS: MINUS
  };
});
