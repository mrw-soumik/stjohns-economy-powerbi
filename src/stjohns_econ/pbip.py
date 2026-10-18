"""Generate the Power BI Project (PBIP) in powerbi/project/.

The semantic model is written in TMDL and the report in PBIR, both from the
same sources as the rest of the repository:
  powerbi/queries.pq     parameter, function, table partitions and column types
  powerbi/measures.dax   measures, display folders and format strings
  powerbi/theme.json     custom report theme
  report_spec.py         pages, visuals, filters, tab order and alt text
Run: python -m stjohns_econ design   (writes the project, then the tests check it)
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import report_spec as rs
from .paths import POWERBI_DIR

PROJECT_DIR = POWERBI_DIR / "project"
NAME = "StJohnsEconomy"
REPORT_DIR = PROJECT_DIR / f"{NAME}.Report"
MODEL_DIR = PROJECT_DIR / f"{NAME}.SemanticModel"
NAMESPACE = uuid.UUID("6f1c0a5e-2b7d-4c1e-9a43-5d3b8e0f7a21")  # fixed, so IDs are stable between runs

FABRIC = "https://developer.microsoft.com/json-schemas/fabric/"
SCHEMAS = {
    "pbip": FABRIC + "pbip/pbipProperties/1.0.0/schema.json",
    "pbir": FABRIC + "item/report/definitionProperties/2.0.0/schema.json",
    "pbism": FABRIC + "item/semanticModel/definitionProperties/1.0.0/schema.json",
    "platform": FABRIC + "gitIntegration/platformProperties/2.0.0/schema.json",
    "version": FABRIC + "item/report/definition/versionMetadata/1.0.0/schema.json",
    "report": FABRIC + "item/report/definition/report/3.3.0/schema.json",
    "pages": FABRIC + "item/report/definition/pagesMetadata/1.1.0/schema.json",
    "page": FABRIC + "item/report/definition/page/2.1.0/schema.json",
    "visual": FABRIC + "item/report/definition/visualContainer/2.13.0/schema.json",
}
BASE_THEME = "Fluent2-CY26SU08"  # the base theme Power BI Desktop wrote in August to October 2026
VERSION_AT_IMPORT = {"visual": "2.12.0", "report": "3.4.0", "page": "2.3.1"}
CUSTOM_THEME = "StJohnsEconomyTheme.json"
COMPATIBILITY_LEVEL = 1601  # 1601 or later is needed for dynamic format strings

# Dynamic format string expressions (documented at the top of measures.dax).
DYNAMIC_FORMATS = {
    "F1": 'SELECTEDVALUE ( DimIndicator[FormatString], "#,0.0" )',
    "F2": 'IF ( SELECTEDVALUE ( DimIndicator[Unit] ) = "Percent", "+0.0"" pts"";-0.0"" pts"";0.0"" pts""", '
          '"+" & SELECTEDVALUE ( DimIndicator[FormatString], "#,0.0" ) & ";-" & SELECTEDVALUE ( DimIndicator[FormatString], "#,0.0" ) '
          '& ";" & SELECTEDVALUE ( DimIndicator[FormatString], "#,0.0" ) )',
    "F3": 'IF ( SELECTEDVALUE ( DimIndicator[ChangeType] ) = "Points", "+0.0"" pts"";-0.0"" pts"";0.0"" pts""", "+0.0%;-0.0%;0.0%" )',
}

# Model settings documented in powerbi/model.md.
TABLE_ORDER = ["_Measures", "FactObservation", "DimDate", "DimGeography", "DimIndicator", "DimSeries", "BasePeriod"]
HIDDEN = {("FactObservation", c) for c in ("GeographyKey", "IndicatorKey", "SeriesKey", "Value")} | {
    ("DimGeography", "GeographyKey"), ("DimIndicator", "IndicatorKey"), ("DimSeries", "SeriesKey"), ("_Measures", "Placeholder")}
SORT_BY = {
    ("DimDate", "MonthLabel"): "MonthSort", ("DimDate", "MonthName"): "Month", ("DimDate", "MonthShort"): "Month",
    ("DimGeography", "ShortName"): "SortOrder", ("DimGeography", "GeographyName"): "SortOrder",
    ("DimIndicator", "ShortName"): "SortOrder", ("DimIndicator", "IndicatorName"): "SortOrder",
    ("BasePeriod", "BaseLabel"): "BaseSort",
}
DATA_CATEGORY = {("DimSeries", "TableUrl"): "WebUrl", ("DimSeries", "TableDoi"): "WebUrl"}
FORMAT_OVERRIDES = {("DimDate", "MonthStart"): "mmm yyyy", ("BasePeriod", "BaseDate"): "mmm yyyy"}
DATE_TABLE, DATE_KEY = "DimDate", "Date"
DERIVED_COLUMNS = {"BasePeriod": [("BaseDate", "type date"), ("BaseLabel", "type text"), ("BaseSort", "Int64.Type")],
                   "_Measures": [("Placeholder", "type text")]}
RELATIONSHIPS = [("FactObservation", "Date", "DimDate", "Date"),
                 ("FactObservation", "GeographyKey", "DimGeography", "GeographyKey"),
                 ("FactObservation", "IndicatorKey", "DimIndicator", "IndicatorKey"),
                 ("FactObservation", "SeriesKey", "DimSeries", "SeriesKey")]
M_TYPES = {"Int64.Type": ("int64", "0"), "type number": ("double", "#,0.0###"), "type text": ("string", None),
           "type date": ("dateTime", "yyyy-mm-dd"), "type logical": ("boolean", None)}


def guid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


# ------------------------------------------------------------------ sources

def query_sections(text: str) -> dict[str, str]:
    """Split queries.pq into {query name: M code}, dropping comment-only head and tail lines."""
    header = re.compile(r"^// -{20,}\n// Query: (\w+)[^\n]*\n(?:// ?[^\n]*\n)*?// -{20,}\n", re.M)
    matches = list(header.finditer(text))
    out = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        lines = text[m.end():end].split("\n")
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("//")):
            lines.pop(0)
        while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("//")):
            lines.pop()
        out[m.group(1)] = "\n".join(lines)
    return out


def typed_columns(m_code: str) -> list[tuple[str, str]]:
    return re.findall(r'\{"([^"]+)",\s*(type \w+|Int64\.Type)\}', m_code)


@dataclass
class Measure:
    name: str
    folder: str
    expression: str
    format: str | None = None  # static format string
    dynamic: str | None = None  # key into DYNAMIC_FORMATS
    description: str = ""


def parse_measures(text: str) -> list[Measure]:
    lines = text.split("\n")
    folder, out, i = "", [], 0
    header = re.compile(r"^    // \[(.+?)\]\s+Format:\s*(.+?)\s*$")
    while i < len(lines):
        line = lines[i]
        f = re.match(r"^\s*// Display folder: (.+?)\s*$", line)
        if f:
            folder = f.group(1)
        h = header.match(line)
        if h:
            name, fmt = h.group(1), h.group(2)
            desc = []
            i += 1
            while lines[i].startswith("    //"):
                desc.append(lines[i].strip()[2:].strip())
                i += 1
            decl = re.match(r"^    MEASURE '_Measures'\[(.+?)\] =\s*$", lines[i])
            if not decl or decl.group(1) != name:
                raise ValueError(f"measures.dax: header [{name}] is not followed by its MEASURE line")
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith("    //") and not lines[i].startswith("//") \
                    and not lines[i].startswith("EVALUATE") and not lines[i].startswith("    MEASURE"):
                body.append(lines[i])
                i += 1
            while body and not body[-1].strip():
                body.pop()
            indent = min(len(b) - len(b.lstrip(" ")) for b in body if b.strip())
            m = Measure(name=name, folder=folder, expression="\n".join(b[indent:] for b in body), description=" ".join(desc))
            dyn = re.match(r"Dynamic (F\d)", fmt)
            if dyn:
                m.dynamic = dyn.group(1)
            elif not fmt.startswith("Text"):
                m.format = fmt
            out.append(m)
            continue
        i += 1
    return out


# ------------------------------------------------------------------ TMDL

def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


def indent_block(code: str, tabs: int) -> list[str]:
    return [("\t" * tabs + ln) if ln.strip() else "" for ln in code.split("\n")]


def column_tmdl(table: str, col: str, mtype: str) -> list[str]:
    data_type, fmt = M_TYPES[mtype]
    fmt = FORMAT_OVERRIDES.get((table, col), fmt)
    out = [f"\tcolumn {q(col)}", f"\t\tdataType: {data_type}"]
    if (table, col) in HIDDEN:
        out.append("\t\tisHidden")
    if (table, col) == (DATE_TABLE, DATE_KEY):
        out.append("\t\tisKey")
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    out.append(f"\t\tlineageTag: {guid('column', table, col)}")
    if (table, col) in DATA_CATEGORY:
        out.append(f"\t\tdataCategory: {DATA_CATEGORY[(table, col)]}")
    out.append("\t\tsummarizeBy: none")
    out.append(f"\t\tsourceColumn: {col}")
    if (table, col) in SORT_BY:
        out.append(f"\t\tsortByColumn: {q(SORT_BY[(table, col)])}")
    out += ["", "\t\tannotation SummarizationSetBy = User"]
    if data_type == "dateTime":
        out += ["", "\t\tannotation UnderlyingDateTimeDataType = Date"]
    return out + [""]


def measure_tmdl(m: Measure) -> list[str]:
    out = []
    if m.description:
        out.append(f"\t/// {m.description}")
    out.append(f"\tmeasure {q(m.name)} = ```")
    out += indent_block(m.expression, 3)
    out.append("\t\t\t```")
    if m.format:
        out.append(f"\t\tformatString: {m.format}")
    out.append(f"\t\tdisplayFolder: {m.folder}")
    out.append(f"\t\tlineageTag: {guid('measure', m.name)}")
    if m.dynamic:
        # formatStringDefinition is a child object: it must follow the measure's properties.
        out += ["", f"\t\tformatStringDefinition = {DYNAMIC_FORMATS[m.dynamic]}"]
    return out + [""]


def table_tmdl(table: str, columns: list[tuple[str, str]], m_code: str, measures: list[Measure]) -> str:
    out = [f"table {q(table)}", f"\tlineageTag: {guid('table', table)}"]
    if table == DATE_TABLE:
        out.append("\tdataCategory: Time")
    out.append("")
    for m in measures:
        out += measure_tmdl(m)
    for col, mtype in columns:
        out += column_tmdl(table, col, mtype)
    out += [f"\tpartition {q(table)} = m", "\t\tmode: import", "\t\tsource ="]
    out += indent_block(m_code, 4)
    out += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(out)


def model_tmdl(query_order: list[str]) -> str:
    out = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
           "\tdiscourageImplicitMeasures", "\tsourceQueryCulture: en-US", "\tdataAccessOptions",
           "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
           "annotation __PBI_TimeIntelligenceEnabled = 0", "",
           f"annotation PBI_QueryOrder = {json.dumps(query_order, separators=(',', ':'))}", ""]
    out += [f"ref table {q(t)}" for t in TABLE_ORDER]
    return "\n".join(out) + "\n"


def expressions_tmdl(sections: dict[str, str]) -> str:
    param, fn = sections["RepoPath"], sections["fnLoadCsv"]
    out = [f"expression RepoPath = {param.strip()}", f"\tlineageTag: {guid('expression', 'RepoPath')}", "",
           "\tannotation PBI_ResultType = Text", "", "expression fnLoadCsv ="]
    out += indent_block(fn, 2)
    out += [f"\tlineageTag: {guid('expression', 'fnLoadCsv')}", "", "\tannotation PBI_ResultType = Function", ""]
    return "\n".join(out)


def relationships_tmdl() -> str:
    out = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        out += [f"relationship {guid('relationship', ft, fc, tt, tc)}", f"\tfromColumn: {q(ft)}.{q(fc)}",
                f"\ttoColumn: {q(tt)}.{q(tc)}", ""]
    return "\n".join(out)


def semantic_model_files() -> dict[str, str]:
    sections = query_sections((POWERBI_DIR / "queries.pq").read_text(encoding="utf-8"))
    measures = parse_measures((POWERBI_DIR / "measures.dax").read_text(encoding="utf-8"))
    files = {
        "definition/database.tmdl": f"database\n\tcompatibilityLevel: {COMPATIBILITY_LEVEL}\n",
        "definition/model.tmdl": model_tmdl(list(sections)),
        "definition/expressions.tmdl": expressions_tmdl(sections),
        "definition/relationships.tmdl": relationships_tmdl(),
    }
    for table in TABLE_ORDER:
        columns = DERIVED_COLUMNS.get(table) or typed_columns(sections[table])
        files[f"definition/tables/{table}.tmdl"] = table_tmdl(
            table, columns, sections[table], measures if table == "_Measures" else [])
    return files


# ------------------------------------------------------------------ PBIR helpers

def lit(value) -> dict:
    """Wrap a formatting value the way Power BI stores it."""
    if isinstance(value, bool):
        s = "true" if value else "false"
    elif isinstance(value, int):
        s = f"{value}L"
    elif isinstance(value, float):
        s = f"{value:g}D"
    else:
        s = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def text_literal(value: str) -> dict:
    return {"Literal": {"Value": "'" + value.replace("'", "''") + "'"}}


def colour(hex_value: str) -> dict:
    return {"solid": {"color": lit(hex_value)}}


def measure_ref(name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": name}}


def field_ref(f: rs.Field) -> dict:
    kind = "Measure" if f.kind == "measure" else "Column"
    return {kind: {"Expression": {"SourceRef": {"Entity": f.table}}, "Property": f.name}}


def projection(f: rs.Field, active: bool | None = None) -> dict:
    p = {"field": field_ref(f), "queryRef": f"{f.table}.{f.name}", "nativeQueryRef": f.name}
    if active is not None:
        p["active"] = active
    return p


def pbir_filter(name: str, f: rs.Filter) -> dict:
    table, column = f.field.table, f.field.name
    alias = table[0].lower()
    source_col = {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": column}}
    if f.values:
        condition = {"In": {"Expressions": [source_col], "Values": [[text_literal(str(v))] for v in f.values]}}
        kind = "Categorical"
    else:
        condition = {"Comparison": {"ComparisonKind": 2, "Left": source_col,
                                    "Right": {"Literal": {"Value": f"datetime'{f.on_or_after}T00:00:00'"}}}}
        kind = "Advanced"
    return {"name": name, "field": field_ref(f.field), "type": kind,
            "filter": {"Version": 2, "From": [{"Name": alias, "Entity": table, "Type": 0}], "Where": [{"Condition": condition}]},
            "howCreated": "User"}


def container_objects(title: str = "", title_measure: str = "", subtitle: str = "", subtitle_measure: str = "",
                      alt: str = "", centred: bool = False) -> dict:
    vco = {}
    if title or title_measure:
        props = {"show": lit(True), "text": {"expr": measure_ref(title_measure)} if title_measure else lit(title)}
        if centred:
            props["alignment"] = lit("center")
        vco["title"] = [{"properties": props}]
    if subtitle or subtitle_measure:
        props = {"show": lit(True), "text": {"expr": measure_ref(subtitle_measure)} if subtitle_measure else lit(subtitle)}
        if centred:
            props["alignment"] = lit("center")
        vco["subTitle"] = [{"properties": props}]
    if alt:
        vco["general"] = [{"properties": {"altText": lit(alt)}}]
    return vco


def series_colours(v: rs.Visual) -> list[dict]:
    entries = []
    for series, hex_value in v.colours.items():
        if series in rs.BOUND_COLOURS and "Series" not in v.roles:
            selector = {"metadata": f"_Measures.{series}"}
        else:
            column = "ShortName"
            table = "DimIndicator" if series in rs.BUILDING_TYPE_COLOURS else "DimGeography"
            selector = {"data": [{"scopeId": {"Comparison": {
                "ComparisonKind": 0,
                "Left": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}},
                "Right": text_literal(series)}}}]}
        entries.append({"properties": {"fill": colour(hex_value)}, "selector": selector})
    return entries


def visual_file(name: str, x: int, y: int, w: int, h: int, z: int, tab: int, visual: dict, filters: list | None = None) -> dict:
    out = {"$schema": SCHEMAS["visual"], "name": name,
           "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": tab}, "visual": visual}
    if filters:
        out["filterConfig"] = {"filters": filters}
    return out


# ------------------------------------------------------------------ visuals

def textbox(v: rs.Visual) -> dict:
    if v.kind == "title":
        paragraphs = [
            {"textRuns": [{"value": v.text[0], "textStyle": {"fontFamily": "Segoe UI Semibold", "fontSize": "18pt", "color": "#0b0b0b"}}]},
            {"textRuns": [{"value": v.text[1], "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#52514e"}}]},
        ]
    else:
        paragraphs = [{"textRuns": [{"value": v.text[0], "textStyle": {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": "#52514e"}}]}]
    visual = {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paragraphs}}]},
              "visualContainerObjects": {**container_objects(alt=v.alt),
                                         "background": [{"properties": {"show": lit(False)}}],
                                         "border": [{"properties": {"show": lit(False)}}]}}
    return visual_file(v.id, v.x, v.y, v.w, v.h, v.tab * 100, v.tab * 10, visual)


SYNC_GROUPS = {"slicer_date": "DateRange", "slicer_list": "Geography", "slicer_dropdown": "IndexBaseMonth"}


def slicer(v: rs.Visual) -> dict:
    mode = {"slicer_date": "Between", "slicer_list": "Basic", "slicer_dropdown": "Dropdown"}[v.kind]
    objects = {"data": [{"properties": {"mode": lit(mode)}}],
               "header": [{"properties": {"show": lit(True), "text": lit(v.title)}}]}
    if v.kind == "slicer_list":
        objects["general"] = [{"properties": {"orientation": lit(1.0)}}]
    if v.kind == "slicer_dropdown":
        objects["selection"] = [{"properties": {"strictSingleSelect": lit(True)}}]
        default = rs.Filter(v.roles["Values"][0], ["Jan 2018"])
        saved = pbir_filter("unused", default)["filter"]
        objects["general"] = [{"properties": {"filter": {"filter": saved}}}]
    visual = {"visualType": "slicer",
              "query": {"queryState": {"Values": {"projections": [projection(v.roles["Values"][0], active=True)]}}},
              "objects": objects,
              "visualContainerObjects": container_objects(alt=v.alt),
              "syncGroup": {"groupName": SYNC_GROUPS[v.kind], "fieldChanges": True, "filterChanges": True}}
    return visual_file(v.id, v.x, v.y, v.w, v.h, v.tab * 100, v.tab * 10, visual)


DELTA_HEIGHT = 30


def kpi_cards(v: rs.Visual) -> list[dict]:
    filters = [pbir_filter(f"{v.id}_f{i}", f) for i, f in enumerate(v.filters)]
    value = {"visualType": "card",
             "query": {"queryState": {"Values": {"projections": [projection(v.value)]}}},
             "objects": {"labels": [{"properties": {"fontSize": lit(24.0), "fontFamily": lit("Segoe UI Semibold"),
                                                    "color": colour("#0b0b0b"), "labelDisplayUnits": lit(1.0)}}],
                         "categoryLabels": [{"properties": {"show": lit(False)}}]},
             "visualContainerObjects": {
                 **container_objects(title=v.title, subtitle=v.subtitle, subtitle_measure=v.subtitle_measure,
                                     alt=v.alt, centred=True),
                 "padding": [{"properties": {"bottom": lit(float(DELTA_HEIGHT + 2))}}]}}
    delta = {"visualType": "card",
             "query": {"queryState": {"Values": {"projections": [projection(v.delta)]}}},
             "objects": {"labels": [{"properties": {"fontSize": lit(10.0 if v.w >= 320 else 9.0), "fontFamily": lit("Segoe UI Semibold"),
                                                    "color": {"solid": {"color": {"expr": measure_ref(v.delta_colour.name)}}}}}],
                         "categoryLabels": [{"properties": {"show": lit(False)}}]},
             "visualContainerObjects": {
                 **container_objects(alt=f"Change for {v.title}: icon, amount, comparison and assessment in words."),
                 "title": [{"properties": {"show": lit(False)}}],
                 "background": [{"properties": {"show": lit(False)}}],
                 "border": [{"properties": {"show": lit(False)}}],
                 "visualHeader": [{"properties": {"show": lit(False)}}],
                 "padding": [{"properties": {"top": lit(0.0), "bottom": lit(0.0), "left": lit(0.0), "right": lit(0.0)}}]}}
    return [
        visual_file(v.id, v.x, v.y, v.w, v.h, v.tab * 100, v.tab * 10, value, filters),
        visual_file(f"{v.id}_delta", v.x + 8, v.y + v.h - DELTA_HEIGHT - 4, v.w - 16, DELTA_HEIGHT, v.tab * 100 + 50,
                    v.tab * 10 + 1, delta, filters),
    ]


CHART_TYPES = {"line": "lineChart", "bar_clustered": "clusteredBarChart", "column_stacked": "columnChart",
               "column_clustered": "clusteredColumnChart"}


def chart(v: rs.Visual) -> dict:
    state = {}
    for role in ("Category", "Series", "Y"):
        if role in v.roles:
            state[role] = {"projections": [projection(f, active=True if role == "Category" else None) for f in v.roles[role]]}
    if v.tooltips:
        state["Tooltips"] = {"projections": [projection(f) for f in v.tooltips]}
    category = v.roles["Category"][0]
    query = {"queryState": state,
             "sortDefinition": {"sort": [{"field": field_ref(category), "direction": "Ascending"}], "isDefaultSort": True}}
    axis_type = "Scalar" if v.kind == "line" else "Categorical"
    objects = {
        "categoryAxis": [{"properties": {"showAxisTitle": lit(False),
                                         **({"axisType": lit(axis_type)} if v.kind != "bar_clustered" else {})}}],
        "valueAxis": [{"properties": {"showAxisTitle": lit(False)}}],
        "legend": [{"properties": {"show": lit(True), "position": lit("Top"), "showTitle": lit(False)}}],
        "dataPoint": series_colours(v),
    }
    if v.kind == "line":
        objects["seriesLabels"] = [{"properties": {"show": lit(True)}}]
        objects["lineStyles"] = [{"properties": {"showMarker": lit(False)}}]
    if v.kind == "bar_clustered":
        objects["labels"] = [{"properties": {"show": lit(True)}}]
    visual = {"visualType": CHART_TYPES[v.kind], "query": query, "objects": objects,
              "visualContainerObjects": container_objects(title=v.title, title_measure=v.title_measure, subtitle=v.subtitle,
                                                          subtitle_measure=v.subtitle_measure, alt=v.alt),
              "drillFilterOtherVisuals": True}
    filters = [pbir_filter(f"{v.id}_f{i}", f) for i, f in enumerate(v.filters)]
    return visual_file(v.id, v.x, v.y, v.w, v.h, v.tab * 100, v.tab * 10, visual, filters)


def page_files(page: rs.Page) -> dict[str, dict]:
    files = {}
    targets_ignoring_geography = []
    for v in page.visuals:
        if v.kind in ("title", "footer"):
            made = [textbox(v)]
        elif v.kind.startswith("slicer"):
            made = [slicer(v)]
        elif v.kind == "kpi":
            made = kpi_cards(v)
        else:
            made = [chart(v)]
        for item in made:
            files[f"definition/pages/{page.id}/visuals/{item['name']}/visual.json"] = item
            if v.ignore_geography_slicer:
                targets_ignoring_geography.append(item["name"])
    page_json = {"$schema": SCHEMAS["page"], "name": page.id, "displayName": page.name, "displayOption": "FitToPage",
                 "height": rs.PAGE_HEIGHT, "width": rs.PAGE_WIDTH}
    if page.filters:
        page_json["filterConfig"] = {"filters": [pbir_filter(f"{page.id}_f{i}", f) for i, f in enumerate(page.filters)]}
    geo_slicer = f"{page.id}_slicer_geography"
    if any(v.id == geo_slicer for v in page.visuals) and targets_ignoring_geography:
        page_json["visualInteractions"] = [{"source": geo_slicer, "target": t, "type": "NoFilter"}
                                           for t in targets_ignoring_geography]
    files[f"definition/pages/{page.id}/page.json"] = page_json
    return files


def report_files() -> dict[str, dict]:
    pages = rs.pages()
    files = {
        "definition.pbir": {"$schema": SCHEMAS["pbir"], "version": "4.0",
                            "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}},
        "definition/version.json": {"$schema": SCHEMAS["version"], "version": "2.0.0"},
        "definition/report.json": {
            "$schema": SCHEMAS["report"],
            "themeCollection": {
                "baseTheme": {"name": BASE_THEME, "reportVersionAtImport": VERSION_AT_IMPORT, "type": "SharedResources"},
                "customTheme": {"name": CUSTOM_THEME, "reportVersionAtImport": VERSION_AT_IMPORT, "type": "RegisteredResources"},
            },
            "objects": {"section": [{"properties": {"verticalAlignment": lit("Top")}}]},
            "resourcePackages": [
                {"name": "SharedResources", "type": "SharedResources",
                 "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
                {"name": "RegisteredResources", "type": "RegisteredResources",
                 "items": [{"name": CUSTOM_THEME, "path": CUSTOM_THEME, "type": "CustomTheme"}]},
            ],
            "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                         "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                         "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
        },
        "definition/pages/pages.json": {"$schema": SCHEMAS["pages"], "pageOrder": [p.id for p in pages],
                                        "activePageName": pages[0].id},
    }
    for page in pages:
        files.update(page_files(page))
    return files


def platform(kind: str) -> dict:
    return {"$schema": SCHEMAS["platform"], "metadata": {"type": kind, "displayName": NAME},
            "config": {"version": "2.0", "logicalId": guid("platform", kind)}}


# ------------------------------------------------------------------ write

def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_pbip(project_dir: Path = PROJECT_DIR) -> list[Path]:
    report_dir, model_dir = project_dir / f"{NAME}.Report", project_dir / f"{NAME}.SemanticModel"
    for generated in (report_dir / "definition", model_dir / "definition"):
        if generated.exists() and project_dir in generated.parents:
            shutil.rmtree(generated)  # regenerate this generator's own output folders
    written = []
    _write_json(project_dir / f"{NAME}.pbip", {"$schema": SCHEMAS["pbip"], "version": "1.0",
                                              "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                              "settings": {"enableAutoRecovery": True}})
    written.append(project_dir / f"{NAME}.pbip")
    _write_json(model_dir / ".platform", platform("SemanticModel"))
    _write_json(model_dir / "definition.pbism", {"$schema": SCHEMAS["pbism"], "version": "4.2", "settings": {}})
    for rel, text in semantic_model_files().items():
        _write_text(model_dir / rel, text)
        written.append(model_dir / rel)
    _write_json(report_dir / ".platform", platform("Report"))
    for rel, obj in report_files().items():
        _write_json(report_dir / rel, obj)
        written.append(report_dir / rel)
    theme = report_dir / "StaticResources" / "RegisteredResources" / CUSTOM_THEME
    theme.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(POWERBI_DIR / "theme.json", theme)
    written.append(theme)
    return written
