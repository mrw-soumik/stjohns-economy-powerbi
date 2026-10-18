"""Command-line entry point: python -m stjohns_econ <command>.

Commands
  fetch      download the catalogued series from Statistics Canada into data/raw/statcan/
  build      validate the raw snapshot and write the star schema to data/processed/
  insights   compute the headline findings (docs/findings.md and the README block)
  diagrams   regenerate the SVG model diagram and report wireframes in docs/
  all        fetch, build, insights and diagrams in order
"""

from __future__ import annotations

import argparse
import sys

from .paths import START_DATE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stjohns_econ", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["fetch", "build", "insights", "diagrams", "all"])
    parser.add_argument("--start", default=START_DATE, help="first reference period to request (fetch)")
    parser.add_argument("--end", default=None, help="last reference period to request (fetch); default today")
    args = parser.parse_args(argv)

    if args.command in ("fetch", "all"):
        from .fetch import run_fetch
        manifest = run_fetch(start=args.start, end=args.end)
        print(f"fetch: {manifest['vector_count']} vectors, {manifest['data_point_count']} data points "
              f"({manifest['start_reference_period']} to {manifest['end_reference_period']})")
    if args.command in ("build", "all"):
        from .build import run_build
        summary = run_build()
        for name, rows in summary["rows"].items():
            print(f"build: {name}.csv {rows} rows")
        for note in summary["notes"]:
            print(f"build: note: {note}")
    if args.command in ("insights", "all"):
        from .insights import run_insights
        findings = run_insights()
        print(f"insights: {len(findings)} findings written to docs/findings.md and README.md")
    if args.command in ("diagrams", "all"):
        from .diagrams import run_diagrams
        for path in run_diagrams():
            print(f"diagrams: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
