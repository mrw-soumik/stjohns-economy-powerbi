# Data dictionary

This dictionary describes the five CSV files in `data/processed/`, which form the
star schema loaded by Power BI (see [powerbi/model.md](../powerbi/model.md)) and by
the web version of the report. The tables marked "generated" below are rewritten
by `python -m stjohns_econ build` and always match the committed data.

## File conventions

- UTF-8, comma-separated, header row, LF line endings.
- Dates in ISO format (`2026-08-01`); decimals use a full stop.
- Values are stored exactly as Statistics Canada publishes them (same unit and
  scalar factor, rounded to the published number of decimals). Nothing is
  rescaled: employment is in thousands of people, CPI and NHPI are index points.
- An empty cell means "no value" and is only allowed in the columns listed as
  optional below. The tests in `tests/test_processed_data.py` enforce this.

## Sources

All data comes from the Statistics Canada Web Data Service
(`https://www150.statcan.gc.ca/t1/wds/rest`). Six tables are used:

<!-- sources:start -->
| Table | Title | Frequency | Vectors used | Coverage in this repository | Table last released |
|---|---|---|---|---|---|
| [14-10-0459-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410045901) | Labour force characteristics by census metropolitan area, three-month moving average, seasonally adjusted | Monthly | 24 | Jan 2016 to Sep 2026 | 2026-10-09 |
| [17-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710000501) | Population estimates on July 1, by age and gender | Annual | 2 | July 1, 2016 to July 1, 2026 | 2026-09-23 |
| [17-10-0148-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014801) | Population estimates, July 1, by census metropolitan area and census agglomeration, 2021 boundaries | Annual | 1 | July 1, 2016 to July 1, 2025 | 2026-01-14 |
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | Consumer Price Index, monthly, not seasonally adjusted | Monthly | 19 | Jan 2016 to Aug 2026 | 2026-09-14 |
| [18-10-0205-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501) | New housing price index, monthly | Monthly | 6 | Jan 2016 to Aug 2026 | 2026-09-17 |
| [34-10-0292-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410029201) | Building permits, by type of structure and type of work | Monthly | 9 | Jan 2018 to Aug 2026 | 2026-10-14 |
<!-- sources:end -->

## Geographies

| Code | Name in this model | Statistics Canada name(s) | Notes |
|---|---|---|---|
| SJ | St. John's (CMA) | "St. John's, Newfoundland and Labrador" (CPI, LFS, NHPI, building permits); "St. John's (CMA), Newfoundland and Labrador" (population) | All series use census metropolitan area (CMA) code 001. Boundary vintages differ by program (for example 2011 for the CPI and 2021 for population); `DimSeries` records the vintage of each series. |
| CA | Canada | "Canada" | |
| NL | Newfoundland and Labrador | "Newfoundland and Labrador" | Province. |

## Indicators (generated)

<!-- indicators:start -->
| Code | Indicator | Topic | Unit | Frequency | Adjustment | Statistic | Aggregation | Change type | Direction |
|---|---|---|---|---|---|---|---|---|---|
| `CPI_ALL` | CPI, all-items | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_SHELTER` | CPI, shelter | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_RENTED` | CPI, rented accommodation | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_OWNED` | CPI, owned accommodation | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_WFE` | CPI, water, fuel and electricity | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_FOOD` | CPI, food | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `CPI_ENERGY` | CPI, energy | Prices | Index (2002=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Lower is better |
| `LFS_UR` | Unemployment rate | Labour | Percent | Monthly | Seasonally adjusted, three-month moving average | Estimate | Average | Points | Lower is better |
| `LFS_ER` | Employment rate | Labour | Percent | Monthly | Seasonally adjusted, three-month moving average | Estimate | Average | Points | Higher is better |
| `LFS_PR` | Participation rate | Labour | Percent | Monthly | Seasonally adjusted, three-month moving average | Estimate | Average | Points | Higher is better |
| `LFS_EMP` | Employment | Labour | Persons (thousands) | Monthly | Seasonally adjusted, three-month moving average | Estimate | Average | Percent | Higher is better |
| `LFS_UR_SE` | Unemployment rate, standard error of estimate | Labour | Percentage points | Monthly | Seasonally adjusted, three-month moving average | Standard error of estimate | Average | Points | Neutral |
| `LFS_UR_SE_YOY` | Unemployment rate, standard error of year-over-year change | Labour | Percentage points | Monthly | Seasonally adjusted, three-month moving average | Standard error of year-over-year change | Average | Points | Neutral |
| `LFS_EMP_SE` | Employment, standard error of estimate | Labour | Persons (thousands) | Monthly | Seasonally adjusted, three-month moving average | Standard error of estimate | Average | Percent | Neutral |
| `LFS_EMP_SE_YOY` | Employment, standard error of year-over-year change | Labour | Persons (thousands) | Monthly | Seasonally adjusted, three-month moving average | Standard error of year-over-year change | Average | Percent | Neutral |
| `POP` | Population, July 1 | Population | Persons | Annual | Not applicable | Estimate | Average | Percent | Neutral |
| `NHPI_TOTAL` | New Housing Price Index, total (house and land) | Housing | Index (December 2016=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Neutral |
| `NHPI_HOUSE` | New Housing Price Index, house only | Housing | Index (December 2016=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Neutral |
| `NHPI_LAND` | New Housing Price Index, land only | Housing | Index (December 2016=100) | Monthly | Not seasonally adjusted | Estimate | Average | Percent | Neutral |
| `BP_UNITS` | Dwelling units created, building permits | Housing | Dwelling units | Monthly | Not seasonally adjusted | Estimate | Sum | Percent | Higher is better |
| `BP_UNITS_SINGLE` | Dwelling units created, single-dwelling buildings | Housing | Dwelling units | Monthly | Not seasonally adjusted | Estimate | Sum | Percent | Higher is better |
| `BP_UNITS_MULTI` | Dwelling units created, multiple-dwelling buildings | Housing | Dwelling units | Monthly | Not seasonally adjusted | Estimate | Sum | Percent | Higher is better |
<!-- indicators:end -->

## Table: FactObservation

Grain: one row per date, geography and indicator. 

| Column | Type | Required | Description | Example |
|---|---|---|---|---|
| Date | date | yes | Reference period. Monthly data is keyed to the first day of the month; annual population estimates to July 1 (see Transformation rules). Foreign key to `DimDate[Date]`. | 2026-08-01 |
| GeographyKey | integer | yes | Foreign key to `DimGeography`. | 1 |
| IndicatorKey | integer | yes | Foreign key to `DimIndicator`. | 1 |
| SeriesKey | integer | yes | Statistics Canada vector ID without the "v". Foreign key to `DimSeries`. | 41692846 |
| Value | decimal | yes | Published value, in the indicator's unit. | 171.8 |
| Status | text | optional | Statistics Canada status flag. Empty means normal; `E` means "use with caution". Other codes (`..`, `F`) are not present because points without a value are dropped. | E |
| Symbol | text | optional | Statistics Canada symbol: `p` preliminary, `r` revised, empty for none. | |
| ReleaseDate | date | yes | Date Statistics Canada last released this data point. | 2026-09-14 |

## Table: DimDate

Daily calendar covering full years from the first to the last fact date. Mark it
as the date table on `Date`.

| Column | Type | Description | Example |
|---|---|---|---|
| Date | date | Calendar day (primary key). | 2026-08-01 |
| Year | integer | Calendar year. | 2026 |
| Quarter | integer | Quarter number 1 to 4. | 3 |
| QuarterLabel | text | "Q" plus quarter number. | Q3 |
| YearQuarter | text | Year and quarter. | 2026 Q3 |
| Month | integer | Month number 1 to 12. | 8 |
| MonthName | text | Full month name (sort by `Month`). | August |
| MonthShort | text | Three-letter month name (sort by `Month`). | Aug |
| MonthStart | date | First day of the month; use it on chart axes. | 2026-08-01 |
| MonthLabel | text | Short month and year (sort by `MonthSort`). | Aug 2026 |
| YearMonth | text | Sortable year-month text. | 2026-08 |
| MonthSort | integer | Year × 100 + month. | 202608 |
| MonthIndex | integer | Months since January of the first year (0-based). | 127 |
| IsMonthStart | boolean | True on the first day of each month. | True |

## Table: DimGeography

| Column | Type | Description | Example |
|---|---|---|---|
| GeographyKey | integer | Primary key. | 1 |
| GeographyCode | text | Stable code used in measures and filters: SJ, CA, NL. | SJ |
| GeographyName | text | Full name. | St. John's (CMA) |
| ShortName | text | Name for legends and labels (sort by `SortOrder`). | St. John's |
| GeographyLevel | text | Census metropolitan area, Province or Country. | Census metropolitan area |
| SortOrder | integer | Display order; also the order of the colour slots. | 1 |
| ColourHex | text | Fixed series colour on the light theme. | #2a78d6 |
| ColourHexDark | text | Same hue stepped for dark surfaces (web version). | #3987e5 |
| MarkerShape | text | Marker shape when markers are shown (secondary encoding). | Circle |

## Table: DimIndicator

| Column | Type | Description | Example |
|---|---|---|---|
| IndicatorKey | integer | Primary key. | 8 |
| IndicatorCode | text | Stable code used in measures and filters. | LFS_UR |
| IndicatorName | text | Full name (sort by `SortOrder`). | Unemployment rate |
| ShortName | text | Name for chart labels (sort by `SortOrder`). | Unemployment rate |
| Topic | text | Prices, Labour, Population or Housing. | Labour |
| Subtopic | text | Finer grouping, for example Shelter costs or Sampling error. | Labour market |
| Unit | text | Unit of `Value`. | Percent |
| Frequency | text | Monthly or Annual. | Monthly |
| Adjustment | text | Seasonal adjustment and smoothing as published. | Seasonally adjusted, three-month moving average |
| Statistic | text | Estimate, Standard error of estimate, or Standard error of year-over-year change. | Estimate |
| AggregationMethod | text | How `[Value]` combines several periods: Average (stocks, rates, indexes) or Sum (flows). | Average |
| ChangeType | text | Headline change unit: Points for rates, Percent otherwise. | Points |
| Direction | text | Higher is better, Lower is better or Neutral; drives the favourable/unfavourable wording. | Lower is better |
| Decimals | integer | Published number of decimals. | 1 |
| FormatString | text | Power BI format string used by dynamic format strings. | 0.0"%" |
| StdErrCode | text | Optional. Indicator code of the standard error of this estimate. | LFS_UR_SE |
| StdErrYoYCode | text | Optional. Indicator code of the standard error of its year-over-year change. | LFS_UR_SE_YOY |
| ReferenceDay | text | Optional. Month and day an annual estimate refers to. | 07-01 |
| SortOrder | integer | Display order. | 8 |
| Description | text | Plain-language definition. | Unemployed people as a percentage of the labour force, population aged 15 and over. |

## Table: DimSeries

Lineage: one row per Statistics Canada vector, so every number can be traced to
its source.

| Column | Type | Description | Example |
|---|---|---|---|
| SeriesKey | integer | Vector ID (primary key). | 41692846 |
| VectorLabel | text | Vector ID as Statistics Canada writes it. | v41692846 |
| TableId | text | Statistics Canada table number. | 18-10-0004-01 |
| TableTitle | text | Table title. | Consumer Price Index, monthly, not seasonally adjusted |
| TableUrl | text | Table page on statcan.gc.ca (data category Web URL). | https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401 |
| TableDoi | text | Persistent DOI link. | https://doi.org/10.25318/1810000401-eng |
| Coordinate | text | Member coordinate of the series in the table. | 4.2.0.0.0.0.0.0.0.0 |
| SourceSeriesTitle | text | Series title as published. | St. John's, Newfoundland and Labrador;All-items |
| SourceGeography | text | Geography name as published. | St. John's, Newfoundland and Labrador |
| SourceGeographyCode | text | Standard Geographical Classification code (text, keeps leading zeros). | 001 |
| SourceGeographyVintage | integer | Vintage of that classification. | 2011 |
| GeographyCode | text | Model geography code. | SJ |
| GeographyName | text | Model geography name. | St. John's (CMA) |
| IndicatorCode | text | Model indicator code. | CPI_ALL |
| UnitOfMeasure | text | Unit as published. | 2002=100 |
| ScalarFactor | text | Scalar factor as published. | units |
| Frequency | text | Frequency as published. | Monthly |
| FirstDate | date | First date loaded. | 2016-01-01 |
| LastDate | date | Last date loaded. | 2026-08-01 |
| ObservationCount | integer | Rows in the fact table for this vector. | 128 |
| LatestReleaseDate | date | Most recent release date among its data points. | 2026-09-14 |
| TableReleaseDate | date | Latest release of the whole table at fetch time. | 2026-09-14 |

## Helper tables created in Power BI

| Table | Built from | Columns | Purpose |
|---|---|---|---|
| BasePeriod | DimDate (month starts up to the last fact date) | BaseDate, BaseLabel, BaseSort | Disconnected slicer for `[Index (Base = 100)]`. |
| _Measures | empty | Placeholder (hidden) | Home table for all measures. |

## Transformation rules

1. Only the 61 catalogued vectors (`config/series.csv`) are loaded. The build
   checks each one against the metadata Statistics Canada returns: table,
   coordinate, frequency, unit of measure and scalar factor must match the
   catalogue, and the series must not be terminated.
2. Reference periods from January 2016 are requested, two years before the 2018
   focus period, so that year-over-year and 12-month measures are complete from
   January 2018.
3. Data points without a value (suppressed or not available) are dropped and
   reported by the build. None were present in the snapshot of 2026-10-18.
4. Annual population estimates refer to July 1 but are published with a
   January 1 reference period; they are keyed to July 1 of the same year.
5. Values are rounded to the number of decimals Statistics Canada publishes.
6. Status and symbol codes are translated to their published symbols (`E`,
   `p`, `r`); status `E` rows are kept and flagged, not dropped.

## Known gaps and caveats

- **City-level CPI is limited.** Statistics Canada publishes the St. John's CPI
  for all-items and the shelter components only. Food and energy are loaded for
  Canada and the province as context and are blank for St. John's by design.
- **N.L. New Housing Price Index not loaded.** The provincial index (vectors
  v111955448, v111955449 and v111955450) equalled the St. John's index in all 128
  months from January 2016 to August 2026 when checked on 2026-10-18, so loading
  it would only draw a duplicate line.
- **NHPI land only is flagged "use with caution".** Every land-only value carries
  status `E`. The report shows it only in secondary views with a caution note.
- **The CPI and NHPI are not seasonally adjusted.** Compare the same month across
  years (year-over-year), not consecutive months.
- **Labour Force Survey estimates for a CMA are survey estimates.** They are
  three-month moving averages, seasonally adjusted, with published standard
  errors. Small month-to-month or year-over-year moves can be sampling noise; the
  measures test significance at the 95% level (1.96 standard errors).
- **Building permits measure intentions, not completions.** "Dwelling units
  created" counts units authorized by permits (new construction and conversions),
  not seasonally adjusted. Use 12-month totals or calendar years. Values are
  revised after first release.
- **Population estimates are revised** as new census and administrative data
  arrive; the latest St. John's CMA estimate is for July 1, 2025, one year behind
  the provincial and national estimates.
- **The CPI is not a cost-of-living index** (Statistics Canada's own note on
  table 18-10-0004-01).

## Series catalogue (generated)

Every vector used, with its table, coordinate, unit as published and coverage.

<!-- catalogue:start -->
| Indicator | Geography | Vector | Table | Coordinate | Unit (as published) | Frequency | First period | Last period | Observations |
|---|---|---|---|---|---|---|---|---|---|
| `CPI_ALL` | St. John's (CMA) | v41692846 | 18-10-0004-01 | `4.2.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_ALL` | Canada | v41690973 | 18-10-0004-01 | `2.2.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_ALL` | Newfoundland and Labrador | v41691244 | 18-10-0004-01 | `3.2.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_SHELTER` | St. John's (CMA) | v41692847 | 18-10-0004-01 | `4.79.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_SHELTER` | Canada | v41691050 | 18-10-0004-01 | `2.79.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_SHELTER` | Newfoundland and Labrador | v41691277 | 18-10-0004-01 | `3.79.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_RENTED` | St. John's (CMA) | v41692848 | 18-10-0004-01 | `4.80.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_RENTED` | Canada | v41691051 | 18-10-0004-01 | `2.80.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_RENTED` | Newfoundland and Labrador | v41691278 | 18-10-0004-01 | `3.80.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_OWNED` | St. John's (CMA) | v41692849 | 18-10-0004-01 | `4.84.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_OWNED` | Canada | v41691055 | 18-10-0004-01 | `2.84.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_OWNED` | Newfoundland and Labrador | v41691280 | 18-10-0004-01 | `3.84.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_WFE` | St. John's (CMA) | v41692850 | 18-10-0004-01 | `4.91.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_WFE` | Canada | v41691062 | 18-10-0004-01 | `2.91.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_WFE` | Newfoundland and Labrador | v41691285 | 18-10-0004-01 | `3.91.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_FOOD` | Canada | v41690974 | 18-10-0004-01 | `2.3.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_FOOD` | Newfoundland and Labrador | v41691245 | 18-10-0004-01 | `3.3.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_ENERGY` | Canada | v41691239 | 18-10-0004-01 | `2.288.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `CPI_ENERGY` | Newfoundland and Labrador | v41691375 | 18-10-0004-01 | `3.288.0.0.0.0.0.0.0.0` | 2002=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `LFS_UR` | St. John's (CMA) | v1643278046 | 14-10-0459-01 | `3.5.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR` | Canada | v1643277934 | 14-10-0459-01 | `1.5.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR` | Newfoundland and Labrador | v1643277990 | 14-10-0459-01 | `2.5.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_ER` | St. John's (CMA) | v1643278062 | 14-10-0459-01 | `3.7.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_ER` | Canada | v1643277950 | 14-10-0459-01 | `1.7.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_ER` | Newfoundland and Labrador | v1643278006 | 14-10-0459-01 | `2.7.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_PR` | St. John's (CMA) | v1643278054 | 14-10-0459-01 | `3.6.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_PR` | Canada | v1643277942 | 14-10-0459-01 | `1.6.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_PR` | Newfoundland and Labrador | v1643277998 | 14-10-0459-01 | `2.6.1.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP` | St. John's (CMA) | v1643278030 | 14-10-0459-01 | `3.3.1.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP` | Canada | v1643277918 | 14-10-0459-01 | `1.3.1.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP` | Newfoundland and Labrador | v1643277974 | 14-10-0459-01 | `2.3.1.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE` | St. John's (CMA) | v1643278048 | 14-10-0459-01 | `3.5.2.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE` | Canada | v1643277936 | 14-10-0459-01 | `1.5.2.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE` | Newfoundland and Labrador | v1643277992 | 14-10-0459-01 | `2.5.2.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE_YOY` | St. John's (CMA) | v1643278052 | 14-10-0459-01 | `3.5.4.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE_YOY` | Canada | v1643277940 | 14-10-0459-01 | `1.5.4.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_UR_SE_YOY` | Newfoundland and Labrador | v1643277996 | 14-10-0459-01 | `2.5.4.1.0.0.0.0.0.0` | Percent | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE` | St. John's (CMA) | v1643278032 | 14-10-0459-01 | `3.3.2.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE` | Canada | v1643277920 | 14-10-0459-01 | `1.3.2.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE` | Newfoundland and Labrador | v1643277976 | 14-10-0459-01 | `2.3.2.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE_YOY` | St. John's (CMA) | v1643278036 | 14-10-0459-01 | `3.3.4.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE_YOY` | Canada | v1643277924 | 14-10-0459-01 | `1.3.4.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `LFS_EMP_SE_YOY` | Newfoundland and Labrador | v1643277980 | 14-10-0459-01 | `2.3.4.1.0.0.0.0.0.0` | Persons in thousands | Monthly | Jan 2016 | Sep 2026 | 129 |
| `POP` | St. John's (CMA) | v1589858712 | 17-10-0148-01 | `4.1.1.0.0.0.0.0.0.0` | Persons | Annual | July 1, 2016 | July 1, 2025 | 10 |
| `POP` | Canada | v466668 | 17-10-0005-01 | `1.1.1.0.0.0.0.0.0.0` | Persons | Annual | July 1, 2016 | July 1, 2026 | 11 |
| `POP` | Newfoundland and Labrador | v466983 | 17-10-0005-01 | `2.1.1.0.0.0.0.0.0.0` | Persons | Annual | July 1, 2016 | July 1, 2026 | 11 |
| `NHPI_TOTAL` | St. John's (CMA) | v111955451 | 18-10-0205-01 | `4.1.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `NHPI_TOTAL` | Canada | v111955442 | 18-10-0205-01 | `1.1.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `NHPI_HOUSE` | St. John's (CMA) | v111955452 | 18-10-0205-01 | `4.2.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `NHPI_HOUSE` | Canada | v111955443 | 18-10-0205-01 | `1.2.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `NHPI_LAND` | St. John's (CMA) | v111955453 | 18-10-0205-01 | `4.3.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `NHPI_LAND` | Canada | v111955444 | 18-10-0205-01 | `1.3.0.0.0.0.0.0.0.0` | Index, 201612=100 | Monthly | Jan 2016 | Aug 2026 | 128 |
| `BP_UNITS` | St. John's (CMA) | v1675210090 | 34-10-0292-01 | `17.4.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS` | Canada | v1675207275 | 34-10-0292-01 | `1.4.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS` | Newfoundland and Labrador | v1675207472 | 34-10-0292-01 | `2.4.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_SINGLE` | St. John's (CMA) | v1675210110 | 34-10-0292-01 | `17.7.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_SINGLE` | Canada | v1675207295 | 34-10-0292-01 | `1.7.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_SINGLE` | Newfoundland and Labrador | v1675207492 | 34-10-0292-01 | `2.7.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_MULTI` | St. John's (CMA) | v1675210160 | 34-10-0292-01 | `17.15.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_MULTI` | Canada | v1675207345 | 34-10-0292-01 | `1.15.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
| `BP_UNITS_MULTI` | Newfoundland and Labrador | v1675207542 | 34-10-0292-01 | `2.15.1.2.1.0.0.0.0.0` | Number | Monthly | Jan 2018 | Aug 2026 | 104 |
<!-- catalogue:end -->

## Licence and attribution

The data is used under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence).
The licence requires these notices, which this repository and the report carry:

- On the data reproduced in `data/raw/` and `data/processed/`:
  "Source: Statistics Canada, name of product, reference date. Reproduced and
  distributed on an "as is" basis with the permission of Statistics Canada."
- On the dashboard and other value-added products: "Adapted from Statistics
  Canada, name of product, reference date. This does not constitute an
  endorsement by Statistics Canada of this product."

The product names and reference dates are the tables and coverage listed under
Sources above.
