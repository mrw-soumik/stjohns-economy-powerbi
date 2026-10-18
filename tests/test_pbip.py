"""Tests for the Power BI Project (powerbi/project): generated, valid, consistent."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys

import pytest

from stjohns_econ import pbip
from stjohns_econ import report_spec as rs
from stjohns_econ.paths import POWERBI_DIR, ROOT

from .test_powerbi_assets import MEASURES

PROJECT = pbip.PROJECT_DIR
MODEL_MD = (POWERBI_DIR / "model.md").read_text(encoding="utf-8")
DAX = (POWERBI_DIR / "measures.dax").read_text(encoding="utf-8")
PARSED = pbip.parse_measures(DAX)


def md_rows(heading_regex: str) -> list[list[str]]:
    """Rows of the first Markdown table after a heading matching the regex."""
    text = MODEL_MD[re.search(heading_regex, MODEL_MD, re.M).end():]
    rows = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("|"):
            rows.append([c.strip() for c in line.strip("|").split("|")])
        elif rows:
            break
    return rows[2:]  # skip header and separator


def test_committed_project_is_current(tmp_path):
    out = tmp_path / "project"
    shared = PROJECT / f"{pbip.NAME}.Report" / "StaticResources" / "SharedResources"
    shutil.copytree(shared, out / f"{pbip.NAME}.Report" / "StaticResources" / "SharedResources")
    written = pbip.run_pbip(out)
    for path in written:
        committed = PROJECT / path.relative_to(out)
        assert committed.exists(), f"missing {committed}; rerun: python -m stjohns_econ design"
        assert committed.read_bytes() == path.read_bytes(), f"{committed} is stale; rerun: python -m stjohns_econ design"
    generated = {p.relative_to(out) for p in out.rglob("*") if p.is_file()}
    committed = {p.relative_to(PROJECT) for p in PROJECT.rglob("*") if p.is_file() and ".pbi" not in p.parts}
    assert committed == generated, f"unexpected files: {sorted(map(str, committed ^ generated))}"


def test_project_passes_the_pbir_validator():
    result = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "pbip-validate" / "validate_pbip.py"), "--strict",
                             str(PROJECT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]
    assert "errors: 0  warnings: 0" in result.stdout


TMDL_VALIDATOR = ROOT / "tools" / "tmdl-validator"


@pytest.mark.skipif(not (TMDL_VALIDATOR / "bin" / "TmdlValidator.dll").exists() or not (TMDL_VALIDATOR / "dotnet").exists(),
                    reason="TMDL validator not built (see powerbi/VALIDATION.md)")
def test_model_passes_the_tmdl_validator():
    result = subprocess.run([str(TMDL_VALIDATOR / "tmdl-validate.sh"), str(PROJECT / f"{pbip.NAME}.SemanticModel"), "--strict"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:]


def test_every_measure_reaches_the_model_with_its_folder_and_format():
    assert [m.name for m in PARSED] == MEASURES
    documented = {row[1]: (row[0], row[2]) for row in md_rows(r"^## Measures")}
    for m in PARSED:
        folder, fmt = documented[m.name]
        assert folder == m.folder, f"{m.name}: folder {m.folder!r} vs model.md {folder!r}"
        expected = m.dynamic or m.format or "Text"
        assert fmt == expected, f"{m.name}: format {expected!r} vs model.md {fmt!r}"
    tmdl = (PROJECT / f"{pbip.NAME}.SemanticModel" / "definition" / "tables" / "_Measures.tmdl").read_text(encoding="utf-8")
    assert len(re.findall(r"^\tmeasure ", tmdl, re.M)) == len(PARSED)


def test_dynamic_format_expressions_are_documented_in_measures_dax():
    header = DAX[:DAX.index("\nDEFINE\n")]
    flat = re.sub(r"\s+", " ", re.sub(r"^//", "", header, flags=re.M))
    for key, expr in pbip.DYNAMIC_FORMATS.items():
        assert re.sub(r"\s+", " ", expr) in flat, f"{key} differs from the measures.dax header"


def test_model_settings_match_model_md():
    sort_rows = md_rows(r"^4\. \*\*Sort by column\*\*")
    documented = {tuple(re.match(r"(\w+)\[(\w+)\]", r[0]).groups()): re.match(r"\w+\[(\w+)\]", r[1]).group(1) for r in sort_rows}
    assert documented == pbip.SORT_BY
    hidden_text = MODEL_MD[MODEL_MD.index("3. **Hide**"):MODEL_MD.index("4. **Sort by column**")]
    for table, column in pbip.HIDDEN:
        assert f"{table}[{column}]" in hidden_text or f"[{column}]" in hidden_text


def test_every_spec_visual_becomes_a_pbir_visual():
    for page in rs.pages():
        folder = PROJECT / f"{pbip.NAME}.Report" / "definition" / "pages" / page.id / "visuals"
        names = {p.name for p in folder.iterdir()}
        for v in page.visuals:
            assert v.id in names
            if v.kind == "kpi":
                assert f"{v.id}_delta" in names


def test_pbir_tab_order_follows_the_spec():
    for page in rs.pages():
        folder = PROJECT / f"{pbip.NAME}.Report" / "definition" / "pages" / page.id / "visuals"
        visuals = [json.loads((d / "visual.json").read_text(encoding="utf-8")) for d in folder.iterdir()]
        orders = [v["position"]["tabOrder"] for v in visuals]
        assert len(orders) == len(set(orders))
        by_name = {v["name"]: v["position"]["tabOrder"] for v in visuals}
        spec_order = [v.id for v in sorted(page.visuals, key=lambda x: x.tab)]
        assert [by_name[n] for n in spec_order] == sorted(by_name[n] for n in spec_order)


def test_every_visual_has_alt_text():
    for path in PROJECT.rglob("visual.json"):
        v = json.loads(path.read_text(encoding="utf-8"))
        alt = v["visual"]["visualContainerObjects"]["general"][0]["properties"]["altText"]["expr"]["Literal"]["Value"]
        assert len(alt) > 15, path
