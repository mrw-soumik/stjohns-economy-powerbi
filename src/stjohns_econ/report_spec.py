"""The report specification as data.

One definition drives four outputs, so they cannot drift apart:
  * docs/report-spec.md (the per-page visual tables),
  * docs/wireframes/*.svg,
  * the Power BI report in PBIR format (powerbi/StJohnsEconomy.Report),
  * the web version in docs/ (it reads docs/data/report-spec.json).

Coordinates are pixels on a 1280 x 720 Power BI page.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

PAGE_WIDTH, PAGE_HEIGHT = 1280, 720
MARGIN, GAP = 24, 16

# Series colours. Geography colours are the first three slots of the theme
# palette; building types use two shades of the St. John's blue because that
# chart shows St. John's only (validated as an ordinal pair).
GEOGRAPHY_COLOURS = {"St. John's": "#2a78d6", "Canada": "#eb6834", "N.L.": "#1baf7a"}
BUILDING_TYPE_COLOURS = {"Single dwellings": "#6da7ec", "Multiple dwellings": "#184f95"}
BOUND_COLOURS = {"Latest Value": "#2a78d6", "Upper 95% Bound": "#898781", "Lower 95% Bound": "#898781"}

SOURCE_TEXT = {
    "overview": "Adapted from Statistics Canada, tables 18-10-0004-01, 14-10-0459-01, 34-10-0292-01, 17-10-0005-01 and 17-10-0148-01.",
    "prices": "Adapted from Statistics Canada, table 18-10-0004-01 (Consumer Price Index, monthly, not seasonally adjusted).",
    "jobs": "Adapted from Statistics Canada, table 14-10-0459-01 (Labour force characteristics by census metropolitan area, three-month moving average, seasonally adjusted).",
    "housing": "Adapted from Statistics Canada, tables 34-10-0292-01, 18-10-0205-01, 17-10-0005-01 and 17-10-0148-01.",
}
ENDORSEMENT = "This does not constitute an endorsement by Statistics Canada of this product."


@dataclass(frozen=True)
class Field:
    table: str
    name: str
    kind: str = "column"  # "column" or "measure"

    @property
    def ref(self) -> str:
        return f"[{self.name}]" if self.kind == "measure" else f"{self.table}[{self.name}]"


def col(table: str, name: str) -> Field:
    return Field(table, name, "column")


def m(name: str) -> Field:
    return Field("_Measures", name, "measure")


@dataclass
class Filter:
    field: Field
    values: list = field(default_factory=list)  # categorical "is one of"
    on_or_after: str | None = None  # dates as ISO text, numbers as text

    def describe(self) -> str:
        if self.values:
            vals = ", ".join(str(v) for v in self.values)
            return f"{self.field.ref} is {vals}" if len(self.values) == 1 else f"{self.field.ref} in ({vals})"
        return f"{self.field.ref} >= {self.on_or_after}"


@dataclass
class Visual:
    id: str
    kind: str  # title, footer, slicer_date, slicer_list, slicer_dropdown, kpi, line, bar_clustered, column_clustered, column_stacked
    x: int
    y: int
    w: int
    h: int
    tab: int
    title: str = ""
    title_measure: str = ""
    subtitle: str = ""
    subtitle_measure: str = ""
    roles: dict = field(default_factory=dict)  # role -> list[Field]
    filters: list = field(default_factory=list)
    tooltips: list = field(default_factory=list)
    alt: str = ""
    ignore_geography_slicer: bool = False
    colours: dict = field(default_factory=dict)  # series value -> hex
    text: list = field(default_factory=list)  # paragraphs for title/footer
    notes: str = ""
    # KPI tiles
    value: Field | None = None
    delta: Field | None = None
    delta_colour: Field | None = None


@dataclass
class Page:
    id: str
    name: str
    question: str
    visuals: list
    filters: list = field(default_factory=list)
    interactions: str = ""


# ---------------------------------------------------------------- helpers

def title_box(page_id: str, title: str, question: str) -> Visual:
    return Visual(f"{page_id}_title", "title", MARGIN, 12, PAGE_WIDTH - 2 * MARGIN, 52, tab=1,
                  text=[title, question], alt=f"Page title: {title}. {question}")


def footer_box(page_id: str) -> Visual:
    return Visual(f"{page_id}_footer", "footer", MARGIN, 676, PAGE_WIDTH - 2 * MARGIN, 36, tab=99,
                  text=[f"{SOURCE_TEXT[page_id]} {ENDORSEMENT} Independent portfolio project; data as published, "
                        "not seasonally adjusted unless stated."],
                  alt="Source and licence notice.")


def slicers(page_id: str) -> list[Visual]:
    y, h = 72, 48
    return [
        Visual(f"{page_id}_slicer_date", "slicer_date", MARGIN, y, 320, h, tab=2, title="Date range",
               roles={"Values": [col("DimDate", "Date")]},
               alt="Date range slicer. Sets the period shown in every chart on this page; cards show the latest month in the range."),
        Visual(f"{page_id}_slicer_geography", "slicer_list", MARGIN + 336, y, 300, h, tab=3, title="Geography",
               roles={"Values": [col("DimGeography", "ShortName")]},
               alt="Geography slicer. Chooses which of St. John's, the province and Canada appear in the comparison charts."),
        Visual(f"{page_id}_slicer_base", "slicer_dropdown", MARGIN + 652, y, 220, h, tab=4, title="Index base month",
               roles={"Values": [col("BasePeriod", "BaseLabel")]},
               alt="Base month for indexed charts. Indexed lines equal 100 in this month."),
    ]


def kpi(vid: str, x: int, y: int, w: int, h: int, tab: int, title: str, value: Field, delta: Field,
        delta_colour: Field, filters: list, alt: str, subtitle_measure: str = "Latest Period Label",
        subtitle: str = "") -> Visual:
    return Visual(vid, "kpi", x, y, w, h, tab=tab, title=title, subtitle=subtitle, subtitle_measure=subtitle_measure,
                  value=value, delta=delta, delta_colour=delta_colour, filters=filters, alt=alt,
                  ignore_geography_slicer=True)


GEO_NAMES = {"SJ": "St. John's", "CA": "Canada", "NL": "N.L."}


def geo_colours(*codes: str) -> dict:
    return {GEO_NAMES[c]: GEOGRAPHY_COLOURS[GEO_NAMES[c]] for c in codes}


def ind(*codes: str) -> Filter:
    return Filter(col("DimIndicator", "IndicatorCode"), list(codes))


def geo(*codes: str) -> Filter:
    return Filter(col("DimGeography", "GeographyCode"), list(codes))


SINCE_2018 = Filter(col("DimDate", "Date"), on_or_after="2018-01-01")
GEO_SERIES = {"Series": [col("DimGeography", "ShortName")]}
MONTH_AXIS = {"Category": [col("DimDate", "MonthStart")]}


def row_positions(count: int, y: int, h: int) -> list[tuple[int, int, int, int]]:
    w = (PAGE_WIDTH - 2 * MARGIN - (count - 1) * GAP) // count
    return [(MARGIN + i * (w + GAP), y, w, h) for i in range(count)]


# ---------------------------------------------------------------- pages

def overview() -> Page:
    tiles = row_positions(3, 72, 116) + row_positions(3, 204, 116)
    gap_label, gap_colour = m("Gap vs Canada Label"), m("Gap Colour")
    yoy_label, yoy_colour = m("YoY Delta Label"), m("YoY Delta Colour")
    k = [
        ("ov_kpi_inflation", "Inflation (CPI all-items)", m("YoY %"), gap_label, gap_colour, "CPI_ALL",
         "St. John's 12-month change in the all-items Consumer Price Index, with the gap to Canada in percentage points."),
        ("ov_kpi_rent", "Rent (CPI rented accommodation)", m("YoY %"), gap_label, gap_colour, "CPI_RENTED",
         "St. John's 12-month change in the rented accommodation index, with the gap to Canada."),
        ("ov_kpi_unemployment", "Unemployment rate", m("Latest Value"), yoy_label, yoy_colour, "LFS_UR",
         "St. John's unemployment rate, three-month moving average, with the change from a year earlier and whether it is statistically significant."),
        ("ov_kpi_employment", "Employment (thousands)", m("Latest Value"), yoy_label, yoy_colour, "LFS_EMP",
         "Employed people in the St. John's CMA, in thousands, with the 12-month change and its significance."),
        ("ov_kpi_permits", "Dwelling units permitted, last 12 months", m("12-Month Rolling Total"),
         m("Rolling 12-Month Delta Label"), m("Rolling 12-Month Delta Colour"), "BP_UNITS",
         "Dwelling units created by building permits in the St. John's CMA over the last 12 months, compared with the 12 months before."),
        ("ov_kpi_population", "Population, July 1", m("Latest Value"), yoy_label, yoy_colour, "POP",
         "St. John's CMA population on July 1 of the latest year, with growth from the year before."),
    ]
    visuals = [title_box("overview", "St. John's economy and housing at a glance",
                         "How is the St. John's economy doing right now, compared with Canada? Latest Statistics Canada "
                         "data for the St. John's census metropolitan area (CMA).")]
    for i, ((vid, title, value, delta, colour, code, alt), (x, y, w, h)) in enumerate(zip(k, tiles)):
        subtitle = "YoY Period Label" if value.name == "YoY %" else "Latest Period Label"
        visuals.append(kpi(vid, x, y, w, h, 2 + i, title, value, delta, colour, [ind(code), geo("SJ")], alt,
                           subtitle_measure=subtitle))
    (x1, y1, w1, h1), (x2, y2, w2, h2) = row_positions(2, 336, 332)
    visuals += [
        Visual("ov_chart_inflation", "line", x1, y1, w1, h1, tab=10, title="Inflation: 12-month change in the CPI",
               subtitle="All-items, not seasonally adjusted", roles={**MONTH_AXIS, "Y": [m("YoY %")], **GEO_SERIES},
               filters=[ind("CPI_ALL"), geo("SJ", "CA"), SINCE_2018], tooltips=[m("YoY Gap vs Canada (pts)")],
               colours=geo_colours("SJ", "CA"),
               alt="Line chart of 12-month CPI inflation since January 2018 for St. John's and Canada. Use Show as a table (Alt+Shift+F11) to read the values."),
        Visual("ov_chart_unemployment", "line", x2, y2, w2, h2, tab=11, title="Unemployment rate",
               subtitle="Three-month moving average, seasonally adjusted", roles={**MONTH_AXIS, "Y": [m("Latest Value")], **GEO_SERIES},
               filters=[ind("LFS_UR"), geo("SJ", "CA"), SINCE_2018], tooltips=[m("Gap vs Canada")],
               colours=geo_colours("SJ", "CA"),
               alt="Line chart of the unemployment rate since January 2018 for St. John's and Canada. Use Show as a table (Alt+Shift+F11) to read the values."),
        footer_box("overview"),
    ]
    return Page("overview", "Overview", "How is the St. John's economy doing right now, compared with Canada?", visuals,
                interactions="No slicers. Cards are fixed to St. John's by visual-level filters; the two charts compare St. John's with Canada from January 2018.")


def prices() -> Page:
    tiles = row_positions(4, 132, 112)
    gap_label, gap_colour = m("Gap vs Canada Label"), m("Gap Colour")
    k = [("pr_kpi_all", "All-items CPI", "CPI_ALL"),
         ("pr_kpi_shelter", "Shelter", "CPI_SHELTER"),
         ("pr_kpi_rent", "Rented accommodation", "CPI_RENTED"),
         ("pr_kpi_wfe", "Water, fuel and electricity", "CPI_WFE")]
    visuals = [title_box("prices", "Prices and shelter costs",
                         "How fast are prices rising in St. John's compared with Canada, and which shelter costs are driving it?"),
               *slicers("prices")]
    for i, ((vid, title, code), (x, y, w, h)) in enumerate(zip(k, tiles)):
        visuals.append(kpi(vid, x, y, w, h, 5 + i, title, m("YoY %"), gap_label, gap_colour, [ind(code), geo("SJ")],
                           f"St. John's 12-month change in the {title} index, with the gap to Canada in percentage points.",
                           subtitle_measure="YoY Period Label"))
    (x1, y1, w1, h1), (x2, y2, w2, h2), (x3, y3, w3, h3) = row_positions(3, 256, 412)
    visuals += [
        Visual("pr_chart_inflation", "line", x1, y1, w1, h1, tab=10, title="12-month inflation, all-items CPI",
               subtitle="Per cent change from the same month a year earlier", roles={**MONTH_AXIS, "Y": [m("YoY %")], **GEO_SERIES},
               filters=[ind("CPI_ALL")], tooltips=[m("YoY Gap vs Canada (pts)")], colours=GEOGRAPHY_COLOURS,
               alt="Line chart of 12-month all-items CPI inflation for the selected geographies and dates. Use Show as a table (Alt+Shift+F11) to read the values."),
        Visual("pr_chart_components", "bar_clustered", x2, y2, w2, h2, tab=11, title="12-month change by shelter component",
               subtitle_measure="Latest Period Label",
               roles={"Category": [col("DimIndicator", "ShortName")], "Y": [m("YoY %")], **GEO_SERIES},
               filters=[ind("CPI_ALL", "CPI_SHELTER", "CPI_RENTED", "CPI_OWNED", "CPI_WFE")], colours=GEOGRAPHY_COLOURS,
               alt="Bar chart comparing the latest 12-month change in all-items CPI and each shelter component across the selected geographies."),
        Visual("pr_chart_rent_index", "line", x3, y3, w3, h3, tab=12, title_measure="Index Chart Title",
               title="Rented accommodation, indexed", subtitle="Each line equals 100 in the selected base month",
               roles={**MONTH_AXIS, "Y": [m("Index (Base = 100)")], **GEO_SERIES},
               filters=[ind("CPI_RENTED")], tooltips=[m("Change Since Base %"), m("Index Gap vs Canada")], colours=GEOGRAPHY_COLOURS,
               alt="Line chart of the rented accommodation price index rebased to 100 in the selected base month, by geography."),
        footer_box("prices"),
    ]
    return Page("prices", "Prices", "How fast are prices rising in St. John's compared with Canada, and which shelter costs are driving it?",
                visuals, filters=[SINCE_2018],
                interactions="Date and geography slicers filter the three charts; the four cards show St. John's only and ignore the geography slicer. The base-month slicer only changes the indexed chart.")


def jobs() -> Page:
    tiles = row_positions(4, 132, 112)
    yoy_label, yoy_colour = m("YoY Delta Label"), m("YoY Delta Colour")
    k = [("jb_kpi_unemployment", "Unemployment rate", "LFS_UR"),
         ("jb_kpi_employment", "Employment (thousands)", "LFS_EMP"),
         ("jb_kpi_employment_rate", "Employment rate", "LFS_ER"),
         ("jb_kpi_participation", "Participation rate", "LFS_PR")]
    visuals = [title_box("jobs", "Jobs and the labour market",
                         "Is the St. John's labour market strengthening or weakening, and how does it compare with the province and Canada?"),
               *slicers("jobs")]
    for i, ((vid, title, code), (x, y, w, h)) in enumerate(zip(k, tiles)):
        visuals.append(kpi(vid, x, y, w, h, 5 + i, title, m("Latest Value"), yoy_label, yoy_colour, [ind(code), geo("SJ")],
                           f"St. John's {title.lower()}, three-month moving average, with the 12-month change and whether it is statistically significant."))
    (x1, y1, w1, h1), (x2, y2, w2, h2), (x3, y3, w3, h3) = row_positions(3, 256, 412)
    visuals += [
        Visual("jb_chart_unemployment", "line", x1, y1, w1, h1, tab=10, title="Unemployment rate",
               subtitle="Three-month moving average, seasonally adjusted", roles={**MONTH_AXIS, "Y": [m("Latest Value")], **GEO_SERIES},
               filters=[ind("LFS_UR")], tooltips=[m("YoY Change"), m("YoY Significance Label")], colours=GEOGRAPHY_COLOURS,
               alt="Line chart of the unemployment rate for the selected geographies and dates. Use Show as a table (Alt+Shift+F11) to read the values."),
        Visual("jb_chart_uncertainty", "line", x2, y2, w2, h2, tab=11, title="St. John's unemployment rate and its 95% confidence bounds",
               subtitle="Survey estimate plus and minus 1.96 standard errors",
               roles={**MONTH_AXIS, "Y": [m("Latest Value"), m("Upper 95% Bound"), m("Lower 95% Bound")]},
               filters=[ind("LFS_UR"), geo("SJ")], colours=BOUND_COLOURS, ignore_geography_slicer=True,
               alt="Line chart of the St. John's unemployment rate with upper and lower 95% confidence bounds, showing the survey's sampling uncertainty."),
        Visual("jb_chart_employment_index", "line", x3, y3, w3, h3, tab=12, title_measure="Index Chart Title",
               title="Employment, indexed", subtitle="Each line equals 100 in the selected base month",
               roles={**MONTH_AXIS, "Y": [m("Index (Base = 100)")], **GEO_SERIES},
               filters=[ind("LFS_EMP")], tooltips=[m("Change Since Base %")], colours=GEOGRAPHY_COLOURS,
               alt="Line chart of employment rebased to 100 in the selected base month, comparing growth across geographies."),
        footer_box("jobs"),
    ]
    return Page("jobs", "Jobs", "Is the St. John's labour market strengthening or weakening, and how does it compare with the province and Canada?",
                visuals, filters=[SINCE_2018],
                interactions="Date and geography slicers filter the comparison charts; the cards and the confidence-bounds chart show St. John's only and ignore the geography slicer.")


def housing() -> Page:
    tiles = row_positions(4, 132, 112)
    visuals = [title_box("housing", "Housing and population",
                         "Is new housing supply keeping pace with population growth, and what is happening to new-home prices?"),
               *slicers("housing")]
    visuals += [
        kpi("hs_kpi_permits", *tiles[0], 5, "Dwelling units permitted, last 12 months", m("12-Month Rolling Total"),
            m("Rolling 12-Month Delta Label"), m("Rolling 12-Month Delta Colour"), [ind("BP_UNITS"), geo("SJ")],
            "Dwelling units created by building permits in the St. John's CMA over the last 12 months, compared with the 12 months before."),
        kpi("hs_kpi_per_capita", *tiles[1], 6, "Units permitted per 1,000 residents", m("Units Permitted per 1,000 Residents"),
            m("Units per 1,000 vs Canada Label"), m("Units per 1,000 vs Canada Colour"), [geo("SJ")],
            "Dwelling units permitted in the last 12 months per 1,000 St. John's residents, compared with Canada.",
            subtitle_measure="", subtitle="Last 12 months of building permits"),
        kpi("hs_kpi_population", *tiles[2], 7, "Population, July 1", m("Latest Value"), m("YoY Delta Label"),
            m("YoY Delta Colour"), [ind("POP"), geo("SJ")],
            "St. John's CMA population on July 1 of the latest year, with growth from the year before."),
        kpi("hs_kpi_new_home_prices", *tiles[3], 8, "New housing prices", m("YoY %"), m("Gap vs Canada Label"),
            m("Gap Colour"), [ind("NHPI_TOTAL"), geo("SJ")],
            "St. John's 12-month change in the New Housing Price Index, with the gap to Canada.",
            subtitle_measure="YoY Period Label"),
    ]
    (x1, y1, w1, h1), (x2, y2, w2, h2), (x3, y3, w3, h3), (x4, y4, w4, h4) = row_positions(4, 256, 412)
    visuals += [
        Visual("hs_chart_permits_by_type", "column_stacked", x1, y1, w1, h1, tab=10,
               title="Dwelling units permitted per year, St. John's", subtitle="Calendar years; the latest year is partial",
               roles={"Category": [col("DimDate", "Year")], "Y": [m("Value")], "Series": [col("DimIndicator", "ShortName")]},
               filters=[ind("BP_UNITS_SINGLE", "BP_UNITS_MULTI"), geo("SJ")], colours=BUILDING_TYPE_COLOURS,
               tooltips=[m("Multi-unit Share %")], ignore_geography_slicer=True,
               alt="Stacked column chart of dwelling units created by building permits in St. John's each year, split into single and multiple dwellings."),
        Visual("hs_chart_per_capita", "line", x2, y2, w2, h2, tab=11, title="Units permitted per 1,000 residents",
               subtitle="Rolling 12-month total of permitted units", roles={**MONTH_AXIS, "Y": [m("Units Permitted per 1,000 Residents")], **GEO_SERIES},
               colours=GEOGRAPHY_COLOURS,
               alt="Line chart of dwelling units permitted over 12 months per 1,000 residents, by geography."),
        Visual("hs_chart_new_home_prices", "line", x3, y3, w3, h3, tab=12, title_measure="Index Chart Title",
               title="New housing prices, indexed", subtitle="House and land; 100 in the base month",
               roles={**MONTH_AXIS, "Y": [m("Index (Base = 100)")], **GEO_SERIES},
               filters=[ind("NHPI_TOTAL")], tooltips=[m("Change Since Base %")], colours=geo_colours("SJ", "CA"),
               notes="Newfoundland and Labrador is not shown: its index equals the St. John's index.",
               alt="Line chart of the New Housing Price Index rebased to 100 in the selected base month, St. John's and Canada."),
        Visual("hs_chart_population_growth", "column_clustered", x4, y4, w4, h4, tab=13, title="Population growth, year over year",
               subtitle="July 1 estimates", roles={"Category": [col("DimDate", "Year")], "Y": [m("YoY %")], **GEO_SERIES},
               filters=[ind("POP")], colours=GEOGRAPHY_COLOURS,
               alt="Column chart of annual population growth to July 1 for each geography."),
        footer_box("housing"),
    ]
    return Page("housing", "Housing and population",
                "Is new housing supply keeping pace with population growth, and what is happening to new-home prices?",
                visuals, filters=[SINCE_2018],
                interactions="Date and geography slicers filter the comparison charts; the cards and the stacked column chart show St. John's only and ignore the geography slicer.")


def pages() -> list[Page]:
    return [overview(), prices(), jobs(), housing()]


def to_json() -> dict:
    """Plain-data export (dataclasses become dictionaries) for the web version."""
    return {"width": PAGE_WIDTH, "height": PAGE_HEIGHT, "pages": [asdict(p) for p in pages()],
            "colours": {"geography": GEOGRAPHY_COLOURS, "buildingType": BUILDING_TYPE_COLOURS, "bounds": BOUND_COLOURS}}
