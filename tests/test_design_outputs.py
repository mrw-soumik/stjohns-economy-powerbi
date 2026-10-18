"""Tests for the report specification and the files generated from it."""

from __future__ import annotations

import itertools

import pytest

from stjohns_econ import report_spec as rs
from stjohns_econ.diagrams import DARK, LIGHT, model_svg, wireframe_svg
from stjohns_econ.docgen import REPORT_SPEC, page_block
from stjohns_econ.paths import DOCS_DIR

from .test_powerbi_assets import MEASURES, model_columns

PAGES = rs.pages()


def all_fields(v: rs.Visual) -> list[rs.Field]:
    fields = [f for fs in v.roles.values() for f in fs] + v.tooltips + [f.field for f in v.filters]
    fields += [x for x in (v.value, v.delta, v.delta_colour) if x is not None]
    fields += [rs.m(n) for n in (v.title_measure, v.subtitle_measure) if n]
    return fields


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.id)
def test_visuals_fit_the_page_without_overlap(page):
    for v in page.visuals:
        assert 0 <= v.x and 0 <= v.y and v.x + v.w <= rs.PAGE_WIDTH and v.y + v.h <= rs.PAGE_HEIGHT, v.id
    for a, b in itertools.combinations(page.visuals, 2):
        overlap = a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h
        assert not overlap, f"{a.id} overlaps {b.id}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.id)
def test_ids_and_tab_orders_are_unique(page):
    ids = [v.id for v in page.visuals]
    tabs = [v.tab for v in page.visuals]
    assert len(ids) == len(set(ids)) and len(tabs) == len(set(tabs))
    assert all(len(i) <= 50 and i.replace("_", "").isalnum() for i in ids)


def test_every_visual_has_alt_text():
    missing = [v.id for p in PAGES for v in p.visuals if len(v.alt) < 15]
    assert not missing


def test_spec_fields_exist_in_the_model():
    cols = model_columns()
    problems = []
    for p in PAGES:
        for v in p.visuals:
            for f in all_fields(v):
                if f.kind == "measure" and f.name not in MEASURES:
                    problems.append(f"{v.id}: measure [{f.name}]")
                if f.kind == "column" and f.name not in cols.get(f.table, set()):
                    problems.append(f"{v.id}: column {f.ref}")
    assert not problems, problems


def test_series_colours_come_from_the_validated_tokens():
    allowed = set(rs.GEOGRAPHY_COLOURS.values()) | set(rs.BUILDING_TYPE_COLOURS.values()) | set(rs.BOUND_COLOURS.values())
    used = {c for p in PAGES for v in p.visuals for c in v.colours.values()}
    assert used <= allowed


def test_report_spec_tables_are_current():
    text = REPORT_SPEC.read_text(encoding="utf-8")
    for page in PAGES:
        assert page_block(page) in text, f"rerun: python -m stjohns_econ design ({page.id})"


@pytest.mark.parametrize("index,page", list(enumerate(PAGES, start=1)), ids=lambda x: getattr(x, "id", str(x)))
def test_wireframes_are_current(index, page):
    path = DOCS_DIR / "wireframes" / f"{index}-{page.id}.svg"
    assert path.read_text(encoding="utf-8") == wireframe_svg(page), "rerun: python -m stjohns_econ design"


def test_model_diagrams_are_current_and_opaque():
    for suffix, palette in (("", LIGHT), ("-dark", DARK)):
        svg = (DOCS_DIR / f"model-diagram{suffix}.svg").read_text(encoding="utf-8")
        assert svg == model_svg(palette)
        assert f'fill="{palette["page"]}"' in svg and "<title" in svg
