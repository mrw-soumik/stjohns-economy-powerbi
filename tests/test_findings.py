"""The published findings must equal what the data produces today."""

from __future__ import annotations

import math

from stjohns_econ.insights import compute_findings, render_findings_md, render_readme_block
from stjohns_econ.paths import DOCS_DIR, README

FINDINGS = compute_findings()


def test_there_are_four_to_six_findings_with_sources():
    assert 4 <= len(FINDINGS) <= 6
    for f in FINDINGS:
        assert f.tables and f.vectors and f.text


def test_finding_values_are_finite_numbers():
    for f in FINDINGS:
        for key, value in f.values.items():
            if isinstance(value, float):
                assert math.isfinite(value), f"{f.key}.{key}"


def test_readme_block_matches_the_data():
    assert render_readme_block(FINDINGS) in README.read_text(encoding="utf-8"), "rerun: python -m stjohns_econ insights"


def test_findings_page_matches_the_data():
    assert (DOCS_DIR / "findings.md").read_text(encoding="utf-8") == render_findings_md(FINDINGS)


def test_house_style():
    text = README.read_text(encoding="utf-8") + (DOCS_DIR / "findings.md").read_text(encoding="utf-8")
    assert "—" not in text, "no em dashes"
    for word in ("revolutionary", "cutting-edge", "seamless", "leverage"):
        assert word not in text.lower()
