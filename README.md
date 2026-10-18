# St. John's Economy and Housing Dashboard (Power BI)

A Power BI dashboard on Statistics Canada open data for the St. John's census
metropolitan area (CMA): prices and shelter costs, jobs, housing supply and
population, compared with Newfoundland and Labrador and Canada. Every number
traces back to a Statistics Canada table and vector, and the pipeline that
prepares the data is tested.

> **View the live report:** link to be added after publishing.
>
> **Screenshots:** to be added.

Built by Mostafa Rafiur Wasib to put the "Power BI Essential Training"
certification into practice: Power Query, a star-schema semantic model, DAX
measures, an accessible report design, and the data engineering and testing
around them.

## Why this dashboard

**Who it is for:** City of St. John's staff and councillors preparing briefings,
residents and journalists who want a sourced picture of the local economy, and
analysts who want to check a number against Statistics Canada.

**Business questions**

1. **Overview:** How is the St. John's economy doing right now, compared with
   Canada?
2. **Prices:** How fast are prices rising in St. John's compared with Canada,
   and which shelter costs are driving it?
3. **Jobs:** Is the St. John's labour market strengthening or weakening, and how
   does it compare with the province and Canada?
4. **Housing and population:** Is new housing supply keeping pace with
   population growth, and what is happening to new-home prices?

## Headline findings

<!-- findings:start -->
_Computed by `python -m stjohns_econ insights` from the data snapshot of 2026-10-18. Full sources, including vector IDs, are in [docs/findings.md](docs/findings.md)._

1. **Prices in St. John's are rising faster than in Canada over the past year, but have risen less since 2018.** St. John's all-items CPI rose 4.4% in the 12 months to August 2026, compared with 3.0% for Canada. Over the longer run the picture is reversed: from August 2018 to August 2026, prices rose 24.2% in St. John's and 26.5% nationally. _(Table 18-10-0004-01)_
2. **Shelter costs are rising much faster in St. John's than nationally.** In August 2026, St. John's shelter prices were 4.9% higher than a year earlier, against 1.5% for Canada. Within shelter, rented accommodation rose 11.9% (Canada 2.8%) and water, fuel and electricity 8.4% (Canada 4.9%), while owned accommodation rose 1.4% (Canada 0.5%). _(Table 18-10-0004-01)_
3. **A single year of rent increases moved St. John's ahead of Canada.** From August 2018 to August 2025, the rented accommodation index rose 30.2% in St. John's, less than Canada's 34.2%. One year of 11.9% growth (Canada 2.8%) reversed that: over the full period to August 2026, St. John's is up 45.6% against 37.9% for Canada. _(Table 18-10-0004-01)_
4. **The St. John's job market is stable, with unemployment close to the national rate.** The St. John's CMA unemployment rate was 6.6% in September 2026 (three-month moving average, seasonally adjusted), close to Canada's 6.5% and below the provincial 9.0%. The change from 7.0% a year earlier (−0.4 points) is within the 95% margin of error of 1.6 points (1.96 standard errors), so it is not statistically significant. Employment, at 128.6 thousand, is 12.5% above its 2019 average (Canada 11.1%). _(Table 14-10-0459-01)_
5. **Permitted housing supply is rising, led by multi-unit buildings.** Building permits in the St. John's CMA created 1,578 dwelling units in the 12 months to August 2026, 22.2% more than in the previous 12 months (Canada −2.0%). That is 6.5 units per 1,000 residents, below Canada's 7.2 (using the latest July 1 population estimates: 2025 for St. John's, 2026 for Canada). In 2025, 1,483 units were permitted, against 516 in 2019, and multiple-unit buildings (doubles, row houses and apartments) accounted for 67.5% of them, up from 41.1% in 2019. _(Tables 17-10-0005-01, 17-10-0148-01, 34-10-0292-01)_
6. **St. John's added 23,426 residents in four years, about 6.9 for every dwelling unit permitted.** The St. John's CMA population grew 10.6% from July 1, 2021 to July 1, 2025 (to 243,478, an increase of 23,426), faster than Canada (8.8%) and the province (4.4%). Over the same four years (July 2021 to June 2025), building permits created 3,392 dwelling units: one unit for every 6.9 new residents. Permits are not completions, and this ratio does not adjust for household size. _(Tables 17-10-0005-01, 17-10-0148-01, 34-10-0292-01)_
<!-- findings:end -->

## Data sources and licence

Six Statistics Canada tables, 61 vectors, loaded through the Statistics Canada
Web Data Service. Monthly data from January 2016 (two years before the 2018
focus period, so year-over-year measures are complete from 2018).

| Table | Content | Frequency | Used for |
|---|---|---|---|
| [18-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810000401) | Consumer Price Index, monthly, not seasonally adjusted | Monthly | All-items and shelter components (St. John's, N.L., Canada); food and energy (N.L., Canada) |
| [14-10-0459-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410045901) | Labour force characteristics by CMA, three-month moving average, seasonally adjusted | Monthly | Unemployment, employment and participation rates, employment, standard errors |
| [34-10-0292-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3410029201) | Building permits, by type of structure and type of work | Monthly | Dwelling units created (total, single, multiple) |
| [18-10-0205-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1810020501) | New housing price index, monthly | Monthly | New-home prices (total, house only, land only) |
| [17-10-0148-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710014801) | Population estimates, July 1, by CMA and census agglomeration, 2021 boundaries | Annual | St. John's CMA population |
| [17-10-0005-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710000501) | Population estimates on July 1, by age and gender | Annual | N.L. and Canada population |

Every vector, coordinate, unit and reference period is listed in the
[data dictionary](docs/data-dictionary.md).

**Licence.** The data is used under the
[Statistics Canada Open Licence](https://www.statcan.gc.ca/en/terms-conditions/open-licence),
which requires these notices:

- For the data reproduced in `data/raw/` and `data/processed/`: "Source:
  Statistics Canada, name of product, reference date. Reproduced and distributed
  on an "as is" basis with the permission of Statistics Canada." (Products and
  reference dates: the tables above, January 2016 to the latest period in each
  table.)
- For the dashboard: "Adapted from Statistics Canada, name of product,
  reference date. This does not constitute an endorsement by Statistics Canada of
  this product."

The code is under the MIT licence ([LICENSE](LICENSE)). This is an independent
portfolio project, not affiliated with or endorsed by Statistics Canada or the
City of St. John's.

## Data model

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/model-diagram-dark.svg">
  <img alt="Star schema: FactObservation in the centre with many-to-one relationships to DimDate, DimGeography, DimIndicator and DimSeries; BasePeriod and _Measures are disconnected helper tables." src="docs/model-diagram.svg">
</picture>

One fact table holds every observation (date, geography, indicator, value);
`DimSeries` keeps the lineage to each Statistics Canada vector. Measures avoid
adding values with different units: they return blank unless one indicator and
one geography are in context, average stocks and rates, and sum flows. Details:
[powerbi/model.md](powerbi/model.md).

Measures cover the latest value, change from the previous period,
year-over-year change, 12-month rolling averages and totals, an index to any base
month, gaps to Canada, 95% confidence bounds and significance tests for Labour
Force Survey estimates, and units permitted per 1,000 residents.

## Repository layout

```
config/                 series catalogue: 61 vectors, indicators, geographies
src/stjohns_econ/       Python ETL (fetch, build), findings, report spec and generators
data/raw/statcan/       raw Web Data Service responses (snapshot) and fetch manifest
data/processed/         star schema as CSV (FactObservation, DimDate, DimGeography, DimIndicator, DimSeries)
powerbi/                Power Query (queries.pq), DAX (measures.dax), theme.json, model.md
docs/                   data dictionary, report specification, wireframes, findings, model diagram
tests/                  data-quality, unit and consistency tests (pytest)
```

## How to build the report

The Power BI assets are plain text, so the report can be rebuilt in about an
hour in Power BI Desktop:

1. **Theme:** View > Themes > Browse for themes > `powerbi/theme.json`.
2. **Queries:** for each section of `powerbi/queries.pq`, add a blank query, paste
   the code and name it as shown (they load the CSVs from this repository's raw
   GitHub URLs; privacy level Public, anonymous access).
3. **Model:** create the four relationships and settings in
   [powerbi/model.md](powerbi/model.md) and mark `DimDate` as the date table.
4. **Measures:** paste `powerbi/measures.dax` into DAX query view, run it, and add
   the measures to the model; set formats and folders as listed.
5. **Pages:** build the four pages from [docs/report-spec.md](docs/report-spec.md)
   and its wireframes; the check query at the end of `measures.dax` should match
   [powerbi/check-query-expected.csv](powerbi/check-query-expected.csv).

## How to refresh the data

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m stjohns_econ fetch      # about 6 polite requests to the Statistics Canada WDS
python -m stjohns_econ build      # validate and rebuild data/processed/*.csv
python -m pytest                  # data-quality and consistency tests
python -m stjohns_econ insights   # recompute the findings above
```

(`make refresh` runs the same steps.) Commit the updated CSVs and Power BI picks
them up on its next refresh, because the queries read from the GitHub raw URLs.
Statistics Canada releases the CPI, the Labour Force Survey and building permits
monthly, so a monthly refresh after the CPI release keeps everything current.

## Data quality checks

`python -m pytest` runs about 80 tests, including:

- unique keys at every grain and referential integrity between fact and dimensions;
- no unexpected empty values, and only known Statistics Canada flags;
- expected date coverage for every series, no gaps, and data that is current at
  the snapshot date;
- one unit per indicator, matching the unit Statistics Canada reports, and
  plausible value ranges;
- single plus multiple dwelling units add up to the total in every month;
- Power Query column types match the CSVs; every DAX column, measure and code
  reference exists; the theme uses the validated palette;
- the README findings, data dictionary tables and wireframes match the data and
  the specification.

## Limitations

- St. John's CPI covers all-items and shelter components only; Statistics Canada
  does not publish food or energy indexes for the city.
- Labour Force Survey estimates for a CMA have sampling error; the report flags
  changes that are within 1.96 standard errors.
- Building permits show permitted supply, not completions, and are revised after
  first release.
- The latest St. John's population estimate is for July 1, 2025, one year behind
  the provincial and national estimates.
- The New Housing Price Index land component is flagged "use with caution" by
  Statistics Canada for every month.
- Figures are as published on the snapshot date (October 18, 2026, UTC) and will
  change with Statistics Canada revisions.
