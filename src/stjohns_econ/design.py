"""The "design" command: regenerate every output derived from report_spec.py."""

from __future__ import annotations

from pathlib import Path

from .diagrams import run_diagrams
from .docgen import REPORT_SPEC, update_report_spec
from .web import run_web_data


def run_design() -> list[Path]:
    written = run_diagrams()
    written += run_web_data()
    if update_report_spec():
        written.append(REPORT_SPEC)
    return written
