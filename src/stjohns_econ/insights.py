"""Compute the headline findings from data/processed/ and publish them.

Every number in docs/findings.md and in the README findings block is produced
here from the committed CSVs. Run: python -m stjohns_econ insights
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pandas as pd

from .paths import DOCS_DIR, POWERBI_DIR, PROCESSED_DIR, RAW_DIR, README

README_START = "<!-- findings:start -->"
README_END = "<!-- findings:end -->"


@dataclass
class Finding:
    key: str
    headline: str
    text: str
    tables: list[str]
    vectors: list[str]
    values: dict = field(default_factory=dict)


class Data:
    """Thin accessor over the processed star schema."""

    def __init__(self, processed_dir=PROCESSED_DIR):
        fact = pd.read_csv(processed_dir / "FactObservation.csv", parse_dates=["Date"])
        ind = pd.read_csv(processed_dir / "DimIndicator.csv")[["IndicatorKey", "IndicatorCode"]]
        geo = pd.read_csv(processed_dir / "DimGeography.csv")[["GeographyKey", "GeographyCode"]]
        self.fact = fact.merge(ind, on="IndicatorKey").merge(geo, on="GeographyKey")
        self.series_dim = pd.read_csv(processed_dir / "DimSeries.csv", dtype={"SourceGeographyCode": str})

    def s(self, indicator: str, geo: str) -> pd.Series:
        rows = self.fact[(self.fact["IndicatorCode"] == indicator) & (self.fact["GeographyCode"] == geo)]
        if rows.empty:
            raise KeyError(f"no data for {indicator} / {geo}")
        return rows.set_index("Date")["Value"].sort_index()

    def vector(self, indicator: str, geo: str) -> str:
        row = self.series_dim[(self.series_dim["IndicatorCode"] == indicator) & (self.series_dim["GeographyCode"] == geo)]
        return row["VectorLabel"].iloc[0]

    def table(self, indicator: str, geo: str) -> str:
        row = self.series_dim[(self.series_dim["IndicatorCode"] == indicator) & (self.series_dim["GeographyCode"] == geo)]
        return row["TableId"].iloc[0]


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def months_back(d: pd.Timestamp, n: int) -> pd.Timestamp:
    return d - pd.DateOffset(months=n)


def month_label(d: pd.Timestamp) -> str:
    return d.strftime("%B %Y")


def f1(x: float) -> str:
    return f"{x:.1f}"


def signed(x: float, unit: str = "%") -> str:
    # U+2212 minus sign: screen readers announce it as "minus".
    return f"{x:+.1f}{unit}".replace("-", "−")


def common_latest(*series: pd.Series) -> pd.Timestamp:
    return min(s.index.max() for s in series)


# ------------------------------------------------------------------ findings

def finding_headline_inflation(d: Data) -> Finding:
    sj, ca = d.s("CPI_ALL", "SJ"), d.s("CPI_ALL", "CA")
    latest = common_latest(sj, ca)
    year_ago = months_back(latest, 12)
    base = pd.Timestamp(2018, latest.month, 1)
    v = {
        "latest": latest.date().isoformat(), "base": base.date().isoformat(),
        "yoy_sj": pct(sj[latest], sj[year_ago]), "yoy_ca": pct(ca[latest], ca[year_ago]),
        "cum_sj": pct(sj[latest], sj[base]), "cum_ca": pct(ca[latest], ca[base]),
    }
    text = (
        f"St. John's all-items CPI rose {f1(v['yoy_sj'])}% in the 12 months to {month_label(latest)}, "
        f"compared with {f1(v['yoy_ca'])}% for Canada. Over the longer run the picture is reversed: from "
        f"{month_label(base)} to {month_label(latest)}, prices rose {f1(v['cum_sj'])}% in St. John's and "
        f"{f1(v['cum_ca'])}% nationally."
    )
    return Finding("inflation", "Prices in St. John's are rising faster than in Canada over the past year, but have risen less since 2018",
                   text, [d.table("CPI_ALL", "SJ")], [d.vector("CPI_ALL", "SJ"), d.vector("CPI_ALL", "CA")], v)


def finding_shelter(d: Data) -> Finding:
    codes = [("CPI_SHELTER", "shelter"), ("CPI_RENTED", "rented accommodation"),
             ("CPI_WFE", "water, fuel and electricity"), ("CPI_OWNED", "owned accommodation")]
    latest = common_latest(*(d.s(c, g) for c, _ in codes for g in ("SJ", "CA")))
    year_ago = months_back(latest, 12)
    v = {"latest": latest.date().isoformat()}
    for code, _ in codes:
        for g in ("SJ", "CA"):
            s = d.s(code, g)
            v[f"{code}_{g}"] = pct(s[latest], s[year_ago])
    text = (
        f"In {month_label(latest)}, St. John's shelter prices were {f1(v['CPI_SHELTER_SJ'])}% higher than a year "
        f"earlier, against {f1(v['CPI_SHELTER_CA'])}% for Canada. Within shelter, rented accommodation rose "
        f"{f1(v['CPI_RENTED_SJ'])}% (Canada {f1(v['CPI_RENTED_CA'])}%) and water, fuel and electricity "
        f"{f1(v['CPI_WFE_SJ'])}% (Canada {f1(v['CPI_WFE_CA'])}%), while owned accommodation rose "
        f"{f1(v['CPI_OWNED_SJ'])}% (Canada {f1(v['CPI_OWNED_CA'])}%)."
    )
    vectors = [d.vector(c, g) for c, _ in codes for g in ("SJ", "CA")]
    return Finding("shelter", "Shelter costs are rising much faster in St. John's than nationally",
                   text, [d.table("CPI_SHELTER", "SJ")], vectors, v)


def finding_rent(d: Data) -> Finding:
    sj, ca = d.s("CPI_RENTED", "SJ"), d.s("CPI_RENTED", "CA")
    latest = common_latest(sj, ca)
    year_ago = months_back(latest, 12)
    base = pd.Timestamp(2018, latest.month, 1)
    v = {
        "latest": latest.date().isoformat(), "year_ago": year_ago.date().isoformat(), "base": base.date().isoformat(),
        "to_year_ago_sj": pct(sj[year_ago], sj[base]), "to_year_ago_ca": pct(ca[year_ago], ca[base]),
        "cum_sj": pct(sj[latest], sj[base]), "cum_ca": pct(ca[latest], ca[base]),
        "yoy_sj": pct(sj[latest], sj[year_ago]), "yoy_ca": pct(ca[latest], ca[year_ago]),
    }
    text = (
        f"From {month_label(base)} to {month_label(year_ago)}, the rented accommodation index rose "
        f"{f1(v['to_year_ago_sj'])}% in St. John's, less than Canada's {f1(v['to_year_ago_ca'])}%. "
        f"One year of {f1(v['yoy_sj'])}% growth (Canada {f1(v['yoy_ca'])}%) reversed that: over the full period to "
        f"{month_label(latest)}, St. John's is up {f1(v['cum_sj'])}% against {f1(v['cum_ca'])}% for Canada."
    )
    return Finding("rent", "A single year of rent increases moved St. John's ahead of Canada",
                   text, [d.table("CPI_RENTED", "SJ")], [d.vector("CPI_RENTED", "SJ"), d.vector("CPI_RENTED", "CA")], v)


def finding_labour(d: Data) -> Finding:
    ur = {g: d.s("LFS_UR", g) for g in ("SJ", "CA", "NL")}
    latest = common_latest(*ur.values())
    year_ago = months_back(latest, 12)
    se_yoy = d.s("LFS_UR_SE_YOY", "SJ")[latest]
    emp_sj, emp_ca = d.s("LFS_EMP", "SJ"), d.s("LFS_EMP", "CA")
    v = {
        "latest": latest.date().isoformat(),
        "ur_sj": ur["SJ"][latest], "ur_ca": ur["CA"][latest], "ur_nl": ur["NL"][latest],
        "ur_sj_year_ago": ur["SJ"][year_ago], "ur_change": ur["SJ"][latest] - ur["SJ"][year_ago],
        "se_yoy": se_yoy, "margin_95": 1.96 * se_yoy,
        "emp_sj": emp_sj[latest], "emp_sj_2019": emp_sj[emp_sj.index.year == 2019].mean(),
        "emp_vs_2019_sj": pct(emp_sj[latest], emp_sj[emp_sj.index.year == 2019].mean()),
        "emp_vs_2019_ca": pct(emp_ca[latest], emp_ca[emp_ca.index.year == 2019].mean()),
    }
    v["ur_change_significant"] = abs(v["ur_change"]) > v["margin_95"]
    significance = ("larger than" if v["ur_change_significant"] else "within")
    text = (
        f"The St. John's CMA unemployment rate was {f1(v['ur_sj'])}% in {month_label(latest)} (three-month moving "
        f"average, seasonally adjusted), close to Canada's {f1(v['ur_ca'])}% and below the provincial "
        f"{f1(v['ur_nl'])}%. The change from {f1(v['ur_sj_year_ago'])}% a year earlier "
        f"({signed(v['ur_change'], ' points')}) is {significance} the 95% margin of error of "
        f"{v['margin_95']:.1f} points (1.96 standard errors), so it is "
        f"{'statistically significant' if v['ur_change_significant'] else 'not statistically significant'}. "
        f"Employment, at {v['emp_sj']:.1f} thousand, is {f1(v['emp_vs_2019_sj'])}% above its 2019 average "
        f"(Canada {f1(v['emp_vs_2019_ca'])}%)."
    )
    vectors = [d.vector("LFS_UR", g) for g in ("SJ", "CA", "NL")] + [d.vector("LFS_UR_SE_YOY", "SJ"), d.vector("LFS_EMP", "SJ"), d.vector("LFS_EMP", "CA")]
    return Finding("labour", "The St. John's job market is stable, with unemployment close to the national rate",
                   text, [d.table("LFS_UR", "SJ")], vectors, v)


def finding_housing_supply(d: Data) -> Finding:
    tot = {g: d.s("BP_UNITS", g) for g in ("SJ", "CA")}
    latest = common_latest(*tot.values())
    def window(s, end, n=12):
        return s[(s.index > months_back(end, n)) & (s.index <= end)].sum()
    sj_multi, sj_tot = d.s("BP_UNITS_MULTI", "SJ"), tot["SJ"]
    full_years = sorted(y for y in set(sj_tot.index.year) if (sj_tot.index.year == y).sum() == 12)
    last_full, first_full = full_years[-1], 2019
    share = lambda y: sj_multi[sj_multi.index.year == y].sum() / sj_tot[sj_tot.index.year == y].sum() * 100
    v = {
        "latest": latest.date().isoformat(),
        "units_12m_sj": window(tot["SJ"], latest), "units_prev_12m_sj": window(tot["SJ"], months_back(latest, 12)),
        "units_12m_ca": window(tot["CA"], latest), "units_prev_12m_ca": window(tot["CA"], months_back(latest, 12)),
        "last_full_year": last_full, "compare_year": first_full,
        "multi_share_last": share(last_full), "multi_share_compare": share(first_full),
        "units_last_full_year": sj_tot[sj_tot.index.year == last_full].sum(),
        "units_compare_year": sj_tot[sj_tot.index.year == first_full].sum(),
    }
    v["chg_sj"] = pct(v["units_12m_sj"], v["units_prev_12m_sj"])
    v["chg_ca"] = pct(v["units_12m_ca"], v["units_prev_12m_ca"])
    text = (
        f"Building permits in the St. John's CMA created {v['units_12m_sj']:,.0f} dwelling units in the 12 months to "
        f"{month_label(latest)}, {f1(abs(v['chg_sj']))}% {'more' if v['chg_sj'] >= 0 else 'fewer'} than in the previous "
        f"12 months (Canada {signed(v['chg_ca'])}). In {last_full}, {v['units_last_full_year']:,.0f} units were "
        f"permitted, against {v['units_compare_year']:,.0f} in {first_full}, and multiple-unit buildings "
        f"(doubles, row houses and apartments) accounted for {f1(v['multi_share_last'])}% of them, up from "
        f"{f1(v['multi_share_compare'])}% in {first_full}."
    )
    vectors = [d.vector("BP_UNITS", "SJ"), d.vector("BP_UNITS_MULTI", "SJ"), d.vector("BP_UNITS", "CA")]
    return Finding("housing_supply", "Permitted housing supply is rising, led by multi-unit buildings",
                   text, [d.table("BP_UNITS", "SJ")], vectors, v)


def finding_population(d: Data) -> Finding:
    pop = {g: d.s("POP", g) for g in ("SJ", "CA", "NL")}
    latest = pop["SJ"].index.max()
    start = pd.Timestamp(latest.year - 4, 7, 1)
    units = d.s("BP_UNITS", "SJ")
    in_window = units[(units.index >= start) & (units.index < latest)]
    v = {
        "start": start.date().isoformat(), "latest": latest.date().isoformat(),
        "pop_sj": pop["SJ"][latest], "added_sj": pop["SJ"][latest] - pop["SJ"][start],
        "growth_sj": pct(pop["SJ"][latest], pop["SJ"][start]),
        "growth_ca": pct(pop["CA"][latest], pop["CA"][start]),
        "growth_nl": pct(pop["NL"][latest], pop["NL"][start]),
        "units_window": in_window.sum(), "units_months": len(in_window),
    }
    v["residents_per_unit"] = v["added_sj"] / v["units_window"]
    text = (
        f"The St. John's CMA population grew {f1(v['growth_sj'])}% from July 1, {start.year} to July 1, "
        f"{latest.year} (to {v['pop_sj']:,.0f}, an increase of {v['added_sj']:,.0f}), faster than Canada "
        f"({f1(v['growth_ca'])}%) and the province ({f1(v['growth_nl'])}%). Over the same four years "
        f"(July {start.year} to June {latest.year}), building permits created {v['units_window']:,.0f} dwelling "
        f"units: one unit for every {v['residents_per_unit']:.1f} new residents. Permits are not completions, "
        f"and this ratio does not adjust for household size."
    )
    vectors = [d.vector("POP", g) for g in ("SJ", "CA", "NL")] + [d.vector("BP_UNITS", "SJ")]
    tables = sorted({d.table("POP", "SJ"), d.table("POP", "CA"), d.table("BP_UNITS", "SJ")})
    headline = (f"St. John's added {v['added_sj']:,.0f} residents in four years, about "
                f"{v['residents_per_unit']:.1f} for every dwelling unit permitted")
    return Finding("population", headline, text, tables, vectors, v)


FINDINGS = [finding_headline_inflation, finding_shelter, finding_rent, finding_labour,
            finding_housing_supply, finding_population]


# ------------------------------------------------------------------ DAX check query mirror

CHECK_QUERY_FILE = "check-query-expected.csv"


def round_half_away(x: float, digits: int) -> float:
    """DAX ROUND semantics (half away from zero), unlike Python's round()."""
    from decimal import ROUND_HALF_UP, Decimal
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def check_query_expected(processed_dir=PROCESSED_DIR) -> pd.DataFrame:
    """Reproduce, in pandas, the EVALUATE check query at the end of measures.dax.

    One row per published estimate series with the values that the measures
    [Latest Period Label], [Latest Value], [YoY Headline Change],
    [Gap vs Canada (Display)], [12-Month Rolling Total] and [YoY Assessment]
    should return. Changes are unformatted (0.0437 means +4.4%).
    """
    fact = pd.read_csv(processed_dir / "FactObservation.csv", parse_dates=["Date"])
    ind = pd.read_csv(processed_dir / "DimIndicator.csv", dtype=str, keep_default_na=False)
    geo = pd.read_csv(processed_dir / "DimGeography.csv", dtype=str, keep_default_na=False)
    ind_by_key = ind.set_index(ind["IndicatorKey"].astype(int))
    geo_by_key = geo.set_index(geo["GeographyKey"].astype(int))
    code_to_key = {c: int(k) for c, k in zip(ind["IndicatorCode"], ind["IndicatorKey"])}
    ca_key = int(geo.loc[geo["GeographyCode"] == "CA", "GeographyKey"].iloc[0])
    series = {k: g.set_index("Date")["Value"].sort_index() for k, g in fact.groupby(["IndicatorKey", "GeographyKey"])}

    rows = []
    for (ik, gk), s in sorted(series.items()):
        meta = ind_by_key.loc[ik]
        if meta["Statistic"] != "Estimate":
            continue
        latest = s.index.max()
        value = s[latest]
        year_ago = months_back(latest, 12)
        prior = s.get(year_ago)
        points = meta["ChangeType"] == "Points"
        yoy_change = value - prior if prior is not None else None
        yoy_pct = value / prior - 1 if prior is not None else None
        headline = yoy_change if points else yoy_pct

        canada = series.get((ik, ca_key))
        gap = None
        if canada is not None and latest in canada.index:
            if points:
                gap = value - canada[latest]
            elif yoy_pct is not None and year_ago in canada.index:
                gap = (yoy_pct - (canada[latest] / canada[year_ago] - 1)) * 100

        rolling = None
        if meta["AggregationMethod"] == "Sum":
            window = s[(s.index > months_back(latest, 12)) & (s.index <= latest)]
            rolling = window.sum() if len(window) == 12 else None

        assessment = None
        if headline is not None:
            rounded = round_half_away(headline, 1 if points else 3)
            significant = None
            if meta["StdErrYoYCode"]:
                se = series.get((code_to_key[meta["StdErrYoYCode"]], gk))
                if se is not None and latest in se.index:
                    significant = bool(abs(yoy_change) > 1.96 * se[latest])
            direction = meta["Direction"]
            if significant is False:
                assessment = "Not significant"
            elif rounded == 0 or direction == "Neutral":
                assessment = "Neutral"
            elif (rounded > 0 and direction == "Higher is better") or (rounded < 0 and direction == "Lower is better"):
                assessment = "Favourable"
            else:
                assessment = "Unfavourable"

        label = (f"{latest.strftime('%B')} {latest.day}, {latest.year}" if meta["Frequency"] == "Annual"
                 else latest.strftime("%B %Y"))
        rows.append({
            "SortOrder": int(meta["SortOrder"]),
            "IndicatorCode": meta["IndicatorCode"],
            "ShortName": geo_by_key.loc[gk, "ShortName"],
            "Latest period": label,
            "Latest value": value,
            "YoY headline change": headline,
            "Gap vs Canada": gap,
            "Rolling 12-month total": rolling,
            "Assessment": assessment,
        })
    out = pd.DataFrame(rows).sort_values(["SortOrder", "ShortName"]).reset_index(drop=True)
    for col in ("Latest value", "YoY headline change", "Gap vs Canada", "Rolling 12-month total"):
        out[col] = out[col].astype(float).round(4)
    return out


def compute_findings(data: Data | None = None) -> list[Finding]:
    data = data or Data()
    return [fn(data) for fn in FINDINGS]


# ------------------------------------------------------------------ rendering

def snapshot_date() -> str:
    with open(RAW_DIR / "manifest.json", encoding="utf-8") as f:
        return json.load(f)["fetched_at_utc"][:10]


def render_readme_block(findings: list[Finding]) -> str:
    lines = [README_START,
             f"_Computed by `python -m stjohns_econ insights` from the data snapshot of {snapshot_date()}. "
             "Full sources, including vector IDs, are in [docs/findings.md](docs/findings.md)._", ""]
    for i, f in enumerate(findings, start=1):
        label = "Table" if len(f.tables) == 1 else "Tables"
        lines.append(f"{i}. **{f.headline}.** {f.text} _({label} {', '.join(f.tables)})_")
    lines.append(README_END)
    return "\n".join(lines)


def render_findings_md(findings: list[Finding]) -> str:
    out = [
        "# Headline findings",
        "",
        f"Generated by `python -m stjohns_econ insights` from `data/processed/` (Statistics Canada data snapshot of "
        f"{snapshot_date()}). Do not edit by hand: rerun the command after a refresh.",
        "",
        "Percentage changes compare the same calendar month in different years, because the CPI and the New Housing "
        "Price Index are not seasonally adjusted. Labour Force Survey figures are three-month moving averages, "
        "seasonally adjusted, as published for census metropolitan areas.",
        "",
    ]
    for i, f in enumerate(findings, start=1):
        out += [f"## {i}. {f.headline}", "", f.text, "",
                f"- Statistics Canada table(s): {', '.join(f.tables)}",
                f"- Vectors: {', '.join(f.vectors)}", ""]
    out += [
        "## Source",
        "",
        "Adapted from Statistics Canada, tables 18-10-0004-01, 14-10-0459-01, 17-10-0005-01, 17-10-0148-01, "
        "18-10-0205-01 and 34-10-0292-01 (reference periods as stated above). This does not constitute an "
        "endorsement by Statistics Canada of this product.",
        "",
    ]
    return "\n".join(out)


def update_readme(block: str) -> bool:
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(README_START) + r".*?" + re.escape(README_END), re.S)
    if not pattern.search(text):
        return False
    README.write_text(pattern.sub(lambda _: block, text), encoding="utf-8")
    return True


def run_insights() -> list[Finding]:
    findings = compute_findings()
    (DOCS_DIR / "findings.md").write_text(render_findings_md(findings), encoding="utf-8")
    update_readme(render_readme_block(findings))
    check = check_query_expected()
    check.to_csv(POWERBI_DIR / CHECK_QUERY_FILE, index=False, lineterminator="\n", float_format="%.10g")
    return findings
