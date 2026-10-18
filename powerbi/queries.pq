// =============================================================================
// St. John's Economy and Housing Dashboard: Power Query (M) queries
// =============================================================================
// Each section below is one query. To add a query in Power BI:
//   Home > Transform data > New source > Blank query > Advanced editor,
//   paste the code between the section rules, then rename the query to the
//   name shown after "Query:". Create them in the order listed.
//
// Data source: the CSV files in data/processed/ of
//   https://github.com/mrw-soumik/stjohns-economy-powerbi
// loaded from GitHub raw URLs, for example
//   https://raw.githubusercontent.com/mrw-soumik/stjohns-economy-powerbi/main/data/processed/FactObservation.csv
//
// Privacy level: Public. Authentication: Anonymous.
//
// Why Web.Contents with RelativePath: the first argument stays a fixed root URL,
// so the Power BI service can validate the data source for scheduled refresh.
// Types are set with the "en-CA" culture so that ISO dates and "." decimals
// parse the same way on any regional setting.
//
// Source: Statistics Canada (see README.md for the full attribution).
// =============================================================================


// -----------------------------------------------------------------------------
// Query: RepoPath   (parameter, type Text, required)
// Path of the processed folder inside raw.githubusercontent.com. Change "main"
// to a tag or commit SHA to pin the report to a specific data snapshot.
// -----------------------------------------------------------------------------
"mrw-soumik/stjohns-economy-powerbi/main/data/processed/" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]


// -----------------------------------------------------------------------------
// Query: fnLoadCsv   (function)
// Downloads one processed CSV and promotes the header row. All columns arrive
// as text; each table query below sets the types.
// -----------------------------------------------------------------------------
(fileName as text) as table =>
let
    Source = Web.Contents(
        "https://raw.githubusercontent.com",
        [RelativePath = RepoPath & fileName]
    ),
    Parsed = Csv.Document(
        Source,
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Parsed, [PromoteAllScalars = true])
in
    Promoted

// Offline alternative (Power BI Desktop only; needs a gateway if published):
// replace the Source step with
//     Source = File.Contents("C:\path\to\stjohns-economy-powerbi\data\processed\" & fileName),


// -----------------------------------------------------------------------------
// Query: FactObservation   (fact table, one row per Date x Geography x Indicator)
// -----------------------------------------------------------------------------
let
    Source = fnLoadCsv("FactObservation.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"Date", type date},
            {"GeographyKey", Int64.Type},
            {"IndicatorKey", Int64.Type},
            {"SeriesKey", Int64.Type},
            {"Value", type number},
            {"Status", type text},
            {"Symbol", type text},
            {"ReleaseDate", type date}
        },
        "en-CA"
    ),
    // Empty flags mean "no flag": store them as null rather than "".
    Flags = Table.ReplaceValue(Typed, "", null, Replacer.ReplaceValue, {"Status", "Symbol"})
in
    Flags


// -----------------------------------------------------------------------------
// Query: DimDate   (daily calendar, full years; mark as date table on [Date])
// -----------------------------------------------------------------------------
let
    Source = fnLoadCsv("DimDate.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"Date", type date},
            {"Year", Int64.Type},
            {"Quarter", Int64.Type},
            {"QuarterLabel", type text},
            {"YearQuarter", type text},
            {"Month", Int64.Type},
            {"MonthName", type text},
            {"MonthShort", type text},
            {"MonthStart", type date},
            {"MonthLabel", type text},
            {"YearMonth", type text},
            {"MonthSort", Int64.Type},
            {"MonthIndex", Int64.Type},
            {"IsMonthStart", type logical}
        },
        "en-CA"
    )
in
    Typed


// -----------------------------------------------------------------------------
// Query: DimGeography
// -----------------------------------------------------------------------------
let
    Source = fnLoadCsv("DimGeography.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"GeographyKey", Int64.Type},
            {"GeographyCode", type text},
            {"GeographyName", type text},
            {"ShortName", type text},
            {"GeographyLevel", type text},
            {"SortOrder", Int64.Type},
            {"ColourHex", type text},
            {"ColourHexDark", type text},
            {"MarkerShape", type text}
        },
        "en-CA"
    )
in
    Typed


// -----------------------------------------------------------------------------
// Query: DimIndicator
// -----------------------------------------------------------------------------
let
    Source = fnLoadCsv("DimIndicator.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"IndicatorKey", Int64.Type},
            {"IndicatorCode", type text},
            {"IndicatorName", type text},
            {"ShortName", type text},
            {"Topic", type text},
            {"Subtopic", type text},
            {"Unit", type text},
            {"Frequency", type text},
            {"Adjustment", type text},
            {"Statistic", type text},
            {"AggregationMethod", type text},
            {"ChangeType", type text},
            {"Direction", type text},
            {"Decimals", Int64.Type},
            {"FormatString", type text},
            {"StdErrCode", type text},
            {"StdErrYoYCode", type text},
            {"ReferenceDay", type text},
            {"SortOrder", Int64.Type},
            {"Description", type text}
        },
        "en-CA"
    ),
    Blanks = Table.ReplaceValue(Typed, "", null, Replacer.ReplaceValue, {"StdErrCode", "StdErrYoYCode", "ReferenceDay"})
in
    Blanks


// -----------------------------------------------------------------------------
// Query: DimSeries   (lineage: one row per Statistics Canada vector)
// -----------------------------------------------------------------------------
let
    Source = fnLoadCsv("DimSeries.csv"),
    Typed = Table.TransformColumnTypes(
        Source,
        {
            {"SeriesKey", Int64.Type},
            {"VectorLabel", type text},
            {"TableId", type text},
            {"TableTitle", type text},
            {"TableUrl", type text},
            {"TableDoi", type text},
            {"Coordinate", type text},
            {"SourceSeriesTitle", type text},
            {"SourceGeography", type text},
            {"SourceGeographyCode", type text},
            {"SourceGeographyVintage", Int64.Type},
            {"GeographyCode", type text},
            {"GeographyName", type text},
            {"IndicatorCode", type text},
            {"UnitOfMeasure", type text},
            {"ScalarFactor", type text},
            {"Frequency", type text},
            {"FirstDate", type date},
            {"LastDate", type date},
            {"ObservationCount", Int64.Type},
            {"LatestReleaseDate", type date},
            {"TableReleaseDate", type date}
        },
        "en-CA"
    )
in
    Typed


// -----------------------------------------------------------------------------
// Query: BasePeriod   (disconnected; drives the "Index (Base = 100)" measure)
// One row per month that has data. Use BaseLabel in a single-select slicer,
// sorted by BaseSort; the measures fall back to January 2018 if nothing is
// selected.
// -----------------------------------------------------------------------------
let
    LastFactDate = List.Max(FactObservation[Date]),
    MonthStarts = Table.SelectRows(DimDate, each [IsMonthStart] = true and [Date] <= LastFactDate),
    Kept = Table.SelectColumns(MonthStarts, {"Date", "MonthLabel", "MonthSort"}),
    Renamed = Table.RenameColumns(
        Kept,
        {{"Date", "BaseDate"}, {"MonthLabel", "BaseLabel"}, {"MonthSort", "BaseSort"}}
    )
in
    Renamed


// -----------------------------------------------------------------------------
// Query: _Measures   (empty home table for the measures in measures.dax)
// After the measures are added, hide the Placeholder column; Power BI then
// lists _Measures at the top of the Data pane.
// -----------------------------------------------------------------------------
let
    Source = #table(type table [Placeholder = text], {})
in
    Source
