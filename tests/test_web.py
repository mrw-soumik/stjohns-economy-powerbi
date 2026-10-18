"""Tests for the web version of the report (docs/index.html)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from stjohns_econ import report_spec as rs
from stjohns_econ.paths import DOCS_DIR, ROOT
from stjohns_econ.web import dashboard_payload

INDEX = (DOCS_DIR / "index.html").read_text(encoding="utf-8")


def read_global(path, name):
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"window\.{name} = (.*);\n$", text, re.S)
    assert match, f"{path.name} does not assign window.{name}"
    return json.loads(match.group(1))


def test_dashboard_bundle_matches_processed_data():
    bundled = read_global(DOCS_DIR / "data" / "dashboard.js", "DASHBOARD")
    assert bundled == json.loads(json.dumps(dashboard_payload())), "rerun: python -m stjohns_econ design"


def test_report_spec_bundle_matches_spec():
    bundled = read_global(DOCS_DIR / "data" / "report-spec.js", "REPORT_SPEC")
    assert bundled == json.loads(json.dumps(rs.to_json())), "rerun: python -m stjohns_econ design"


def test_page_is_labelled_as_the_web_version():
    assert "Web version of the Power BI report" in INDEX
    assert '<html lang="en-CA">' in INDEX


def test_scripts_and_styles_are_local_and_pinned():
    refs = re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', INDEX)
    external = [r for r in refs if re.match(r"https?://", r)]
    assert not external, f"no CDN dependencies expected: {external}"
    assert "assets/vendor/d3-7.9.0.min.js" in refs
    vendored = (DOCS_DIR / "assets" / "vendor" / "d3-7.9.0.min.js").read_text(encoding="utf-8")
    assert vendored.startswith("// https://d3js.org v7.9.0 ")
    assert (DOCS_DIR / "assets" / "vendor" / "d3-LICENSE.txt").exists()


def test_text_is_inserted_safely():
    js = "".join((DOCS_DIR / "assets" / "js" / f).read_text(encoding="utf-8") for f in ("app.js", "charts.js"))
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_web_measures_match_the_dax_reference():
    result = subprocess.run(["node", str(ROOT / "tests" / "web" / "check_measures.cjs")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
