"""Project paths and run-wide constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
RAW_DIR = ROOT / "data" / "raw" / "statcan"
PROCESSED_DIR = ROOT / "data" / "processed"
DOCS_DIR = ROOT / "docs"
README = ROOT / "README.md"

# First reference period requested from Statistics Canada. Two years before the
# 2018 focus period so that year-over-year and 12-month rolling measures are
# complete from January 2018 onwards.
START_DATE = "2016-01-01"

# Public location of the processed CSVs once the repository is published.
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/mrw-soumik/stjohns-economy-powerbi/main/data/processed/"
)
