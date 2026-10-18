"""Consistency tests between the Power BI assets and the processed data.

Power BI cannot run in CI, so these tests catch the mistakes that would break a
refresh or a measure: a column renamed in the CSVs but not in Power Query, a
DAX reference to a column or measure that does not exist, an indicator code
typed wrongly inside a measure, or a theme palette that drifted from the
validated colours.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd
import pytest

from stjohns_econ.insights import CHECK_QUERY_FILE, check_query_expected
from stjohns_econ.paths import GITHUB_RAW_BASE, POWERBI_DIR, PROCESSED_DIR

QUERIES = (POWERBI_DIR / "queries.pq").read_text(encoding="utf-8")
DAX = (POWERBI_DIR / "measures.dax").read_text(encoding="utf-8")
MODEL_MD = (POWERBI_DIR / "model.md").read_text(encoding="utf-8")
THEME = json.loads((POWERBI_DIR / "theme.json").read_text(encoding="utf-8"))

CSV_TABLES = sorted(p.stem for p in PROCESSED_DIR.glob("*.csv"))
DERIVED_COLUMNS = {"BasePeriod": ["BaseDate", "BaseLabel", "BaseSort"], "_Measures": ["Placeholder"]}

# Validated with the dataviz palette validator (adjacent pairs, light mode) and
# the first three slots for all pairs; see powerbi/model.md.
VALIDATED_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]


def csv_header(table: str) -> list[str]:
    return list(pd.read_csv(PROCESSED_DIR / f"{table}.csv", nrows=0).columns)


def query_sections() -> dict[str, str]:
    parts = re.split(r"^// Query: (\w+).*$", QUERIES, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def typed_columns(section: str) -> list[tuple[str, str]]:
    return re.findall(r'\{"([^"]+)",\s*(type \w+|Int64\.Type)\}', section)


def strip_dax_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        in_string = False
        for i, ch in enumerate(line):
            if ch == '"':
                in_string = not in_string
            elif ch == "/" and not in_string and line[i:i + 2] == "//":
                line = line[:i]
                break
        out.append(line)
    return "\n".join(out)


DAX_CODE = strip_dax_comments(DAX)
DAX_STRINGS = re.findall(r'"((?:[^"]|"")*)"', DAX_CODE)
DAX_NO_STRINGS = re.sub(r'"(?:[^"]|"")*"', '""', DAX_CODE)
MEASURES = re.findall(r"MEASURE\s+'_Measures'\[([^\]]+)\]\s*=", DAX_CODE)


def model_columns() -> dict[str, set[str]]:
    cols = {t: set(csv_header(t)) for t in CSV_TABLES}
    cols.update({t: set(c) for t, c in DERIVED_COLUMNS.items()})
    return cols


# ---------------------------------------------------------------- Power Query

def test_every_processed_table_has_a_query():
    sections = query_sections()
    missing = [t for t in CSV_TABLES + list(DERIVED_COLUMNS) if t not in sections]
    assert not missing, f"queries.pq has no section for {missing}"


@pytest.mark.parametrize("table", CSV_TABLES)
def test_query_columns_match_csv_header_in_order(table):
    cols = [c for c, _ in typed_columns(query_sections()[table])]
    assert cols == csv_header(table)


@pytest.mark.parametrize("table", CSV_TABLES)
def test_query_types_fit_the_csv_values(table):
    df = pd.read_csv(PROCESSED_DIR / f"{table}.csv", dtype=str, keep_default_na=False)
    for col, mtype in typed_columns(query_sections()[table]):
        values = df[col][df[col] != ""]
        if mtype == "Int64.Type":
            assert values.str.fullmatch(r"-?\d+").all(), f"{table}.{col} is not whole numbers"
        elif mtype == "type date":
            values.map(dt.date.fromisoformat)  # raises on a bad date
        elif mtype == "type number":
            pd.to_numeric(values)  # raises on a non-number
        elif mtype == "type logical":
            assert set(values) <= {"True", "False"}, f"{table}.{col} is not boolean"


def test_query_reads_from_the_published_repository():
    match = re.search(r'^"([^"]+)" meta \[IsParameterQuery = true', QUERIES, flags=re.M)
    assert match, "RepoPath parameter not found"
    assert "https://raw.githubusercontent.com/" + match.group(1) == GITHUB_RAW_BASE
    assert 'Web.Contents(\n        "https://raw.githubusercontent.com"' in QUERIES


# ---------------------------------------------------------------- DAX

def test_measure_names_are_unique():
    assert len(MEASURES) == len(set(MEASURES))
    assert len(MEASURES) >= 40


def test_dax_column_references_exist():
    cols = model_columns()
    refs = re.findall(r"(?:'([^']+)'|\b([A-Za-z_]\w*))\[([^\]]+)\]", DAX_NO_STRINGS)
    problems = []
    for quoted, bare, column in refs:
        table = quoted or bare
        if table == "_Measures":
            continue  # measure definitions
        if table not in cols:
            problems.append(f"unknown table {table}")
        elif column not in cols[table]:
            problems.append(f"unknown column {table}[{column}]")
    assert not problems, sorted(set(problems))


def test_dax_measure_references_are_defined():
    refs = re.findall(r"(?<![\w'\]])\[([^\]]+)\]", DAX_NO_STRINGS)
    undefined = sorted({r for r in refs if r not in MEASURES})
    assert not undefined, f"references to undefined measures: {undefined}"


def test_dax_codes_and_categories_exist_in_the_data():
    ind = pd.read_csv(PROCESSED_DIR / "DimIndicator.csv", dtype=str, keep_default_na=False)
    geo = pd.read_csv(PROCESSED_DIR / "DimGeography.csv", dtype=str, keep_default_na=False)
    known = set(ind["IndicatorCode"]) | set(geo["GeographyCode"])
    for col in ("Frequency", "AggregationMethod", "ChangeType", "Direction", "Statistic"):
        known |= set(ind[col])
    known |= {"Quarterly"}  # handled for completeness; no quarterly series today
    codes = {s for s in DAX_STRINGS if re.fullmatch(r"[A-Z]{2}(_[A-Z]+)*", s) or s in
             {"Monthly", "Annual", "Sum", "Average", "Points", "Percent", "Neutral", "Estimate",
              "Higher is better", "Lower is better"}}
    assert codes, "expected code literals in measures.dax"
    unknown = sorted(codes - known)
    assert not unknown, f"string literals in measures.dax not found in the data: {unknown}"


def test_dax_colours_are_text_tokens():
    colours = {s.lower() for s in DAX_STRINGS if re.fullmatch(r"#[0-9a-fA-F]{6}", s)}
    assert colours <= {"#006300", "#d03b3b", "#52514e"}, colours


def test_model_md_documents_every_measure():
    missing = [m for m in MEASURES if f"| {m} |" not in MODEL_MD]
    assert not missing, f"model.md does not list: {missing}"


def test_check_query_expected_is_current():
    committed = pd.read_csv(POWERBI_DIR / CHECK_QUERY_FILE)
    fresh = check_query_expected()
    pd.testing.assert_frame_equal(committed, fresh, check_dtype=False, atol=1e-9)


# ---------------------------------------------------------------- theme

def test_theme_palette_is_the_validated_palette():
    assert THEME["dataColors"] == VALIDATED_PALETTE


def test_geography_colours_are_the_first_theme_slots():
    geo = pd.read_csv(PROCESSED_DIR / "DimGeography.csv").sort_values("SortOrder")
    assert geo["ColourHex"].tolist() == VALIDATED_PALETTE[:3]


def test_theme_text_colours_are_ink_tokens():
    assert THEME["foreground"] == "#0b0b0b"
    assert THEME["good"] == "#006300" and THEME["bad"] == "#d03b3b"
    for cls in THEME["textClasses"].values():
        assert cls["color"] in {"#0b0b0b", "#52514e"}
