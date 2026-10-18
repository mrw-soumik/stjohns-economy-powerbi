"""Generate the SVG wireframes (from report_spec) and the star-schema diagram.

Every SVG has an opaque background so it stays legible on GitHub's light and
dark themes; the model diagram also has a dark variant for <picture> switching.
Colours are the validated tokens documented in powerbi/model.md.
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from . import report_spec as rs
from .paths import DOCS_DIR

FONT = "Segoe UI, system-ui, -apple-system, Helvetica, Arial, sans-serif"
LIGHT = {"page": "#f9f9f7", "surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
         "grid": "#e1e0d9", "axis": "#c3c2b7", "accent": "#2a78d6", "accent_soft": "#cde2fb"}
DARK = {"page": "#0d0d0d", "surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
        "grid": "#2c2c2a", "axis": "#383835", "accent": "#3987e5", "accent_soft": "#184f95"}


def t(x, y, text, size=12, fill="#0b0b0b", weight="normal", anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(text)}</text>')


def wrap(text: str, width_px: int, size: int) -> list[str]:
    max_chars = max(10, int(width_px / (size * 0.52)))
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > max_chars:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    return lines + [line] if line else lines


# ---------------------------------------------------------------- wireframes

def _card(v: rs.Visual, c=LIGHT) -> list[str]:
    return [f'<rect x="{v.x}" y="{v.y}" width="{v.w}" height="{v.h}" rx="6" fill="{c["surface"]}" stroke="{c["grid"]}"/>']


def _badge(v: rs.Visual, c=LIGHT) -> list[str]:
    cx, cy = v.x + v.w - 14, v.y + 14
    return [f'<circle cx="{cx}" cy="{cy}" r="9" fill="{c["accent_soft"]}"/>',
            t(cx, cy + 4, str(v.tab), 10, c["ink"], "600", "middle")]


def _titles(v: rs.Visual, c=LIGHT) -> tuple[list[str], int]:
    out, y = [], v.y + 22
    title = v.title or v.title_measure
    if v.title_measure:
        title = f"{v.title} (dynamic title)"
    for line in wrap(title, v.w - 44, 12)[:2]:
        out.append(t(v.x + 14, y, line, 12, c["ink"], "600"))
        y += 16
    sub = v.subtitle or (f"[{v.subtitle_measure}]" if v.subtitle_measure else "")
    for line in (wrap(sub, v.w - 44, 10)[:2] if sub else []):
        out.append(t(v.x + 14, y, line, 10, c["ink2"]))
        y += 14
    return out, y


def _legend(v: rs.Visual, y: int, c=LIGHT) -> tuple[list[str], int]:
    out, x = [], v.x + 14
    for name, colour in v.colours.items():
        label = {"Latest Value": "Estimate", "Upper 95% Bound": "Upper 95% bound", "Lower 95% Bound": "Lower 95% bound"}.get(name, name)
        out.append(f'<rect x="{x}" y="{y - 7}" width="14" height="3" rx="1.5" fill="{colour}"/>')
        out.append(t(x + 18, y, label, 9, c["ink2"]))
        x += 26 + int(len(label) * 5.2)
    return out, y + 12


def _line_glyph(v: rs.Visual, top: int, c=LIGHT) -> list[str]:
    import math
    left, right, bottom = v.x + 40, v.x + v.w - 64, v.y + v.h - 28
    out = []
    for i in range(4):
        gy = top + (bottom - top) * i / 3
        out.append(f'<line x1="{left}" y1="{gy:.1f}" x2="{right}" y2="{gy:.1f}" stroke="{c["grid"]}" stroke-width="1"/>')
    out.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{c["axis"]}" stroke-width="1"/>')
    profiles = [(0.45, 0.10, 0.0), (0.62, 0.08, 1.1), (0.80, 0.06, 2.3)]  # level, amplitude, phase; distinct end levels
    for i, (name, colour) in enumerate(list(v.colours.items())[:3]):
        level, amp, phase = profiles[i]
        if name == "Upper 95% Bound":
            level, amp, phase = profiles[0][0] - 0.16, profiles[0][1], profiles[0][2]
        elif name == "Lower 95% Bound":
            level, amp, phase = profiles[0][0] + 0.16, profiles[0][1], profiles[0][2]
        elif name == "Latest Value":
            level, amp, phase = profiles[0]
        pts = []
        for k in range(41):
            frac = k / 40
            py = level + amp * math.sin(frac * 5.0 + phase) - 0.12 * frac
            pts.append((left + (right - left) * frac, top + (bottom - top) * min(0.95, max(0.05, py))))
        path = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        out.append(f'<polyline points="{path}" fill="none" stroke="{colour}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        label = {"Latest Value": "Estimate", "Upper 95% Bound": "Upper", "Lower 95% Bound": "Lower"}.get(name, name)
        out.append(t(pts[-1][0] + 6, pts[-1][1] + 3, label, 9, c["ink"]))
    return out


def _categories(v: rs.Visual) -> list[str]:
    cat = v.roles.get("Category", [None])[0]
    if cat is not None and cat.table == "DimDate" and cat.name == "Year":
        return [str(y) for y in range(2018, 2027)]
    codes = next((f.values for f in v.filters if f.field.name == "IndicatorCode"), [])
    names = {"CPI_ALL": "All-items", "CPI_SHELTER": "Shelter", "CPI_RENTED": "Rented acc.",
             "CPI_OWNED": "Owned acc.", "CPI_WFE": "Water, fuel, elec."}
    return [names.get(code, code) for code in codes] or [f"Item {i}" for i in range(1, 6)]


def _bar_glyph(v: rs.Visual, top: int, horizontal: bool, stacked: bool, c=LIGHT) -> list[str]:
    out = []
    colours = list(v.colours.values())[: (2 if stacked else 3)]
    categories = _categories(v)
    left, right, bottom = v.x + (96 if horizontal else 40), v.x + v.w - 24, v.y + v.h - 40
    groups = len(categories)
    if horizontal:
        band = (bottom - top) / groups
        for g in range(groups):
            out.append(t(v.x + 14, top + band * g + band / 2 + 3, categories[g], 9, c["ink2"]))
            for s, colour in enumerate(colours):
                bh = min(8, band / (len(colours) + 1))
                by = top + band * g + 4 + s * (bh + 2)
                bw = (right - left - 30) * (0.35 + 0.12 * ((g + s * 2) % 5))
                out.append(f'<rect x="{left}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{colour}"/>')
    else:
        band = (right - left) / groups
        out.append(f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="{c["axis"]}" stroke-width="1"/>')
        for g in range(groups):
            out.append(t(left + band * g + band / 2, bottom + 14, categories[g], 8, c["ink2"], anchor="middle"))
            if stacked:
                y0 = bottom
                for s, colour in enumerate(colours):
                    hgt = (bottom - top) * (0.18 + 0.1 * ((g + s * 3) % 4)) * (0.6 if s == 0 else 0.9)
                    bw = min(24, band * 0.6)
                    out.append(f'<rect x="{left + band * g + (band - bw) / 2:.1f}" y="{y0 - hgt:.1f}" width="{bw:.1f}" height="{hgt - 2:.1f}" rx="2" fill="{colour}"/>')
                    y0 -= hgt
            else:
                bw = min(8, band / (len(colours) + 1))
                for s, colour in enumerate(colours):
                    hgt = (bottom - top) * (0.2 + 0.12 * ((g * 2 + s) % 5))
                    bx = left + band * g + 2 + s * (bw + 2)
                    out.append(f'<rect x="{bx:.1f}" y="{bottom - hgt:.1f}" width="{bw:.1f}" height="{hgt:.1f}" rx="2" fill="{colour}"/>')
    return out


def _slicer(v: rs.Visual, c=LIGHT) -> list[str]:
    out = [t(v.x + 12, v.y + 17, v.title, 10, c["ink2"], "600")]
    y = v.y + 34
    if v.kind == "slicer_date":
        out += [f'<rect x="{v.x + 12}" y="{y - 5}" width="{v.w - 24}" height="4" rx="2" fill="{c["grid"]}"/>',
                f'<rect x="{v.x + 12}" y="{y - 5}" width="{v.w - 24}" height="4" rx="2" fill="{c["accent"]}" opacity="0.5"/>',
                f'<circle cx="{v.x + 14}" cy="{y - 3}" r="6" fill="{c["surface"]}" stroke="{c["accent"]}" stroke-width="2"/>',
                f'<circle cx="{v.x + v.w - 14}" cy="{y - 3}" r="6" fill="{c["surface"]}" stroke="{c["accent"]}" stroke-width="2"/>',
                t(v.x + v.w - 30, v.y + 17, "Jan 2018 to latest month", 9, c["ink2"], anchor="end")]
    elif v.kind == "slicer_list":
        x = v.x + 12
        for name, colour in rs.GEOGRAPHY_COLOURS.items():
            wdt = 22 + len(name) * 6
            out += [f'<rect x="{x}" y="{y - 12}" width="{wdt}" height="18" rx="9" fill="{c["surface"]}" stroke="{c["axis"]}"/>',
                    f'<circle cx="{x + 10}" cy="{y - 3}" r="4" fill="{colour}"/>', t(x + 18, y + 1, name, 9, c["ink"])]
            x += wdt + 8
    else:
        out += [f'<rect x="{v.x + 12}" y="{y - 12}" width="{v.w - 24}" height="20" rx="4" fill="{c["surface"]}" stroke="{c["axis"]}"/>',
                t(v.x + 20, y + 2, "Jan 2018", 9, c["ink"]), t(v.x + v.w - 22, y + 2, "▾", 10, c["ink2"], anchor="end")]
    return out


def _kpi(v: rs.Visual, c=LIGHT) -> list[str]:
    out = [t(v.x + 14, v.y + 22, v.title, 11, c["ink"], "600")]
    sub = v.subtitle or (f"[{v.subtitle_measure}]" if v.subtitle_measure else "")
    if sub:
        out.append(t(v.x + 14, v.y + 37, sub, 9, c["ink2"]))
    placeholder = {"YoY %": "+0.0%", "Latest Value": "00.0", "12-Month Rolling Total": "0,000",
                   "Units Permitted per 1,000 Residents": "0.0"}.get(v.value.name, "0.0")
    out.append(t(v.x + 14, v.y + v.h - 30, placeholder, 20, c["ink"], "600"))
    out.append(t(v.x + 20 + len(placeholder) * 12, v.y + v.h - 30, f"[{v.value.name}]", 9, c["muted"]))
    out.append(t(v.x + 14, v.y + v.h - 12, f"▲ [{v.delta.name}]", 9, c["ink2"]))
    return out


def wireframe_svg(page: rs.Page) -> str:
    c = LIGHT
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {rs.PAGE_WIDTH} {rs.PAGE_HEIGHT}" '
             f'width="{rs.PAGE_WIDTH}" height="{rs.PAGE_HEIGHT}" role="img" aria-labelledby="wf-title wf-desc">',
             f'<title id="wf-title">Wireframe: {escape(page.name)} page</title>',
             f'<desc id="wf-desc">{escape(page.question)} Numbered circles give the keyboard tab order.</desc>',
             f'<rect width="{rs.PAGE_WIDTH}" height="{rs.PAGE_HEIGHT}" fill="{c["page"]}"/>']
    for v in page.visuals:
        if v.kind == "title":
            parts.append(t(v.x, v.y + 24, v.text[0], 20, c["ink"], "600"))
            parts.append(t(v.x, v.y + 44, v.text[1], 11, c["ink2"]))
            parts += _badge(rs.Visual(v.id, v.kind, v.x + v.w - 40, v.y, 40, 30, v.tab))
            continue
        if v.kind == "footer":
            for i, line in enumerate(wrap(v.text[0], v.w, 9)[:2]):
                parts.append(t(v.x, v.y + 14 + i * 13, line, 9, c["ink2"]))
            continue
        parts += _card(v)
        if v.kind.startswith("slicer"):
            parts += _slicer(v)
        elif v.kind == "kpi":
            parts += _kpi(v)
        else:
            titles, y = _titles(v)
            parts += titles
            legend, y = _legend(v, y + 10)
            parts += legend
            if v.kind == "line":
                parts += _line_glyph(v, y + 8)
            else:
                parts += _bar_glyph(v, y + 8, v.kind == "bar_clustered", v.kind == "column_stacked")
        parts += _badge(v)
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- model diagram

MODEL_TABLES = {
    "FactObservation": (["Date (FK)", "GeographyKey (FK)", "IndicatorKey (FK)", "SeriesKey (FK)", "Value", "Status", "Symbol", "ReleaseDate"], "fact"),
    "DimDate": (["Date (PK)", "Year, Quarter, Month", "MonthStart, MonthLabel", "MonthSort, MonthIndex", "IsMonthStart"], "dim"),
    "DimGeography": (["GeographyKey (PK)", "GeographyCode", "GeographyName, ShortName", "SortOrder, ColourHex"], "dim"),
    "DimIndicator": (["IndicatorKey (PK)", "IndicatorCode, Name", "Topic, Unit, Frequency", "AggregationMethod", "Direction, FormatString", "StdErrCode, StdErrYoYCode"], "dim"),
    "DimSeries": (["SeriesKey (PK) = vector", "TableId, TableTitle", "TableUrl, TableDoi", "SourceSeriesTitle", "FirstDate, LastDate"], "dim"),
    "BasePeriod": (["BaseDate", "BaseLabel, BaseSort"], "helper"),
    "_Measures": (["50+ measures in 8 folders"], "helper"),
}
MODEL_POS = {"FactObservation": (370, 200), "DimDate": (40, 200), "DimGeography": (370, 40), "DimIndicator": (700, 200),
             "DimSeries": (370, 430), "BasePeriod": (40, 450), "_Measures": (700, 450)}
BOX_W, ROW_H = 220, 18


def _box_height(name: str) -> int:
    return 30 + ROW_H * len(MODEL_TABLES[name][0]) + 8


def model_svg(c: dict) -> str:
    w, h = 960, 620
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-labelledby="m-title m-desc">',
             '<title id="m-title">Star schema of the semantic model</title>',
             '<desc id="m-desc">FactObservation in the centre with many-to-one relationships to DimDate, DimGeography, '
             'DimIndicator and DimSeries; filters flow from each dimension to the fact table. BasePeriod and _Measures are disconnected.</desc>',
             f'<rect width="{w}" height="{h}" rx="10" fill="{c["page"]}"/>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             f'<path d="M0,0 L10,5 L0,10 z" fill="{c["ink2"]}"/></marker></defs>']

    def anchor(name, side):
        x, y = MODEL_POS[name]
        hgt = _box_height(name)
        return {"left": (x, y + hgt / 2), "right": (x + BOX_W, y + hgt / 2), "top": (x + BOX_W / 2, y),
                "bottom": (x + BOX_W / 2, y + hgt)}[side]

    links = [("DimDate", "right", "left"), ("DimGeography", "bottom", "top"), ("DimIndicator", "left", "right"), ("DimSeries", "top", "bottom")]
    for dim, dside, fside in links:
        (x1, y1), (x2, y2) = anchor(dim, dside), anchor("FactObservation", fside)
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c["ink2"]}" stroke-width="1.5" marker-end="url(#arrow)"/>')
        parts.append(t(x1 + (6 if dside == "right" else -6 if dside == "left" else 8), y1 + (-6 if dside in ("right", "left") else 14 if dside == "bottom" else -6),
                       "1", 11, c["ink"], "600", "start" if dside != "left" else "end"))
        parts.append(t(x2 + (-8 if fside == "left" else 8 if fside == "right" else 10), y2 + (-6 if fside in ("left", "right") else -6 if fside == "top" else 16),
                       "*", 13, c["ink"], "600", "end" if fside == "left" else "start"))
    for name, (cols, role) in MODEL_TABLES.items():
        x, y = MODEL_POS[name]
        hgt = _box_height(name)
        header = {"fact": c["accent"], "dim": c["accent_soft"], "helper": c["grid"]}[role]
        header_ink = "#ffffff" if role == "fact" else c["ink"]
        parts.append(f'<rect x="{x}" y="{y}" width="{BOX_W}" height="{hgt}" rx="6" fill="{c["surface"]}" stroke="{c["axis"]}"/>')
        parts.append(f'<path d="M{x},{y + 6} a6,6 0 0 1 6,-6 h{BOX_W - 12} a6,6 0 0 1 6,6 v20 h-{BOX_W} z" fill="{header}"/>')
        parts.append(t(x + 12, y + 18, name, 12, header_ink, "600"))
        for i, col in enumerate(cols):
            parts.append(t(x + 12, y + 44 + i * ROW_H, col, 10.5, c["ink"] if "(PK" in col or "(FK" in col else c["ink2"],
                           "600" if "(PK" in col or "(FK" in col else "normal"))
    parts.append(t(40, 600, "Arrows show the filter direction (one side to many side). Grey headers mark disconnected helper tables.", 10, c["ink2"]))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def run_diagrams(docs_dir: Path = DOCS_DIR) -> list[Path]:
    written = []
    wf_dir = docs_dir / "wireframes"
    wf_dir.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(rs.pages(), start=1):
        path = wf_dir / f"{i}-{page.id}.svg"
        path.write_text(wireframe_svg(page), encoding="utf-8")
        written.append(path)
    for suffix, palette in (("", LIGHT), ("-dark", DARK)):
        path = docs_dir / f"model-diagram{suffix}.svg"
        path.write_text(model_svg(palette), encoding="utf-8")
        written.append(path)
    return written
