"""Regenerate the data-driven blocks of docs/data-dictionary.md.

The hand-written text stays as is; only the content between marker comments
(<!-- name:start --> ... <!-- name:end -->) is replaced, so the tables of
sources, indicators and vectors always match data/processed/.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .paths import DOCS_DIR, PROCESSED_DIR, RAW_DIR

DATA_DICTIONARY = DOCS_DIR / "data-dictionary.md"


def _md_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _month(d: str, frequency: str) -> str:
    ts = pd.Timestamp(d)
    return f"July 1, {ts.year}" if frequency == "Annual" else ts.strftime("%b %Y")


def sources_block(series: pd.DataFrame, cubes: list[dict]) -> str:
    rows = []
    for table_id, g in series.groupby("TableId", sort=True):
        pid = int(table_id.replace("-", "")[:8])
        cube = next(c for c in cubes if int(c["productId"]) == pid)
        freq = g["Frequency"].iloc[0]
        rows.append([
            f"[{table_id}](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid={pid}01)",
            cube["cubeTitleEn"],
            freq,
            str(len(g)),
            f"{_month(g['FirstDate'].min(), freq)} to {_month(g['LastDate'].max(), freq)}",
            (cube.get("releaseTime") or "")[:10],
        ])
    return _md_table(["Table", "Title", "Frequency", "Vectors used", "Coverage in this repository", "Table last released"], rows)


def indicators_block(indicators: pd.DataFrame) -> str:
    rows = [[f"`{r.IndicatorCode}`", r.IndicatorName, r.Topic, r.Unit, r.Frequency, r.Adjustment, r.Statistic,
             r.AggregationMethod, r.ChangeType, r.Direction]
            for r in indicators.sort_values("SortOrder").itertuples()]
    return _md_table(["Code", "Indicator", "Topic", "Unit", "Frequency", "Adjustment", "Statistic",
                      "Aggregation", "Change type", "Direction"], rows)


def catalogue_block(series: pd.DataFrame, indicators: pd.DataFrame) -> str:
    order = indicators.set_index("IndicatorCode")["SortOrder"].to_dict()
    geo_order = {"SJ": 1, "CA": 2, "NL": 3}
    s = series.assign(_o=series["IndicatorCode"].map(order), _g=series["GeographyCode"].map(geo_order))
    rows = []
    for r in s.sort_values(["_o", "_g"]).itertuples():
        unit = r.UnitOfMeasure if r.ScalarFactor == "units" else f"{r.UnitOfMeasure} ({r.ScalarFactor})"
        rows.append([f"`{r.IndicatorCode}`", r.GeographyName, r.VectorLabel, r.TableId, f"`{r.Coordinate}`",
                     unit, r.Frequency, _month(r.FirstDate, r.Frequency), _month(r.LastDate, r.Frequency),
                     str(r.ObservationCount)])
    return _md_table(["Indicator", "Geography", "Vector", "Table", "Coordinate", "Unit (as published)",
                      "Frequency", "First period", "Last period", "Observations"], rows)


def replace_block(text: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:start -->).*?(<!-- {name}:end -->)", re.S)
    if not pattern.search(text):
        raise ValueError(f"marker block '{name}' not found")
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(2)}", text)


def update_data_dictionary(path: Path = DATA_DICTIONARY, processed_dir: Path = PROCESSED_DIR, raw_dir: Path = RAW_DIR) -> bool:
    if not path.exists():
        return False
    series = pd.read_csv(processed_dir / "DimSeries.csv", dtype=str, keep_default_na=False)
    indicators = pd.read_csv(processed_dir / "DimIndicator.csv", dtype=str, keep_default_na=False)
    indicators["SortOrder"] = indicators["SortOrder"].astype(int)
    with open(raw_dir / "cube_metadata.json", encoding="utf-8") as f:
        cubes = json.load(f)
    text = path.read_text(encoding="utf-8")
    text = replace_block(text, "sources", sources_block(series, cubes))
    text = replace_block(text, "indicators", indicators_block(indicators))
    text = replace_block(text, "catalogue", catalogue_block(series, indicators))
    path.write_text(text, encoding="utf-8")
    return True


# ---------------------------------------------------------------- report spec

REPORT_SPEC = DOCS_DIR / "report-spec.md"
KIND_LABELS = {
    "title": "Text box", "footer": "Text box", "slicer_date": "Slicer, between (date range)",
    "slicer_list": "Slicer, tiles (multi-select)", "slicer_dropdown": "Slicer, dropdown (single select)",
    "kpi": "KPI card", "line": "Line chart", "bar_clustered": "Clustered bar chart",
    "column_clustered": "Clustered column chart", "column_stacked": "Stacked column chart",
}
ROLE_LABELS = {"Category": "X axis", "Y": "Y axis", "Series": "Legend", "Values": "Field"}


def _fields_text(v) -> str:
    if v.kind == "kpi":
        parts = [f"Value: {v.value.ref}", f"Delta: {v.delta.ref}", f"Delta colour (fx): {v.delta_colour.ref}"]
        if v.subtitle_measure:
            parts.append(f"Subtitle (fx): [{v.subtitle_measure}]")
        return "; ".join(parts)
    if v.kind in ("title", "footer"):
        return "Static text"
    parts = [f"{ROLE_LABELS.get(role, role)}: {', '.join(f.ref for f in fields)}" for role, fields in v.roles.items()]
    if v.tooltips:
        parts.append(f"Tooltips: {', '.join(f.ref for f in v.tooltips)}")
    if v.title_measure:
        parts.append(f"Title (fx): [{v.title_measure}]")
    if v.subtitle_measure:
        parts.append(f"Subtitle (fx): [{v.subtitle_measure}]")
    return "; ".join(parts)


def page_block(page) -> str:
    rows = []
    for v in sorted(page.visuals, key=lambda x: x.tab):
        title = v.text[0] if v.kind == "title" else ("Source and licence notice" if v.kind == "footer" else (v.title or v.title_measure))
        filters = "; ".join(f.describe() for f in v.filters) or "none"
        if v.ignore_geography_slicer and v.kind != "kpi":
            filters += " (ignores the geography slicer)"
        rows.append([str(v.tab), f"`{v.id}`", KIND_LABELS[v.kind], title, _fields_text(v), filters,
                     f"{v.x}, {v.y}, {v.w} x {v.h}", v.alt])
    return _md_table(["Tab", "ID", "Visual", "Title", "Fields and measures", "Visual filters", "Position (x, y, w x h)", "Alt text"], rows)


def update_report_spec(path: Path = REPORT_SPEC) -> bool:
    from . import report_spec as rs
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    for page in rs.pages():
        text = replace_block(text, f"visuals-{page.id}", page_block(page))
        filters = "; ".join(f.describe() for f in page.filters) or "none"
        text = replace_block(text, f"page-{page.id}", f"Page-level filters: {filters}. {page.interactions}")
    path.write_text(text, encoding="utf-8")
    return True
