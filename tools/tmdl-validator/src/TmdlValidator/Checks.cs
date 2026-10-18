using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

namespace TmdlValidator;

/// <summary>Model rules that TOM does not enforce when loading TMDL offline, plus Power BI Desktop conventions.</summary>
public static class ModelChecks
{
    /// <summary>Highest feature level known to TOM 19.118.3 in Power BI mode (DAX user-defined functions).</summary>
    public const int NewestKnownCompatLevel = 1702;
    private static readonly StringComparer Ci = StringComparer.OrdinalIgnoreCase;

    public static void Run(Database db, Report r, SourceIndex src)
    {
        var model = db.Model;
        var dbLoc = src.FindTop("database", null);
        int cl = db.CompatibilityLevel;

        // ---------------- compatibility level
        if (cl < 1200) r.Error("COMPAT", $"compatibilityLevel {cl} is below 1200; TMDL needs a tabular model at 1200 or higher", dbLoc);
        else if (cl < 1500) r.Warn("COMPAT", $"compatibilityLevel {cl} is unusually low for a Power BI model (Power BI Desktop writes 1550 or higher)", dbLoc);
        if (cl > NewestKnownCompatLevel)
            r.Warn("COMPAT", $"compatibilityLevel {cl} is above the newest level this TOM version knows ({NewestKnownCompatLevel}); the TMDL parser accepts any number, but Power BI rejects levels it does not support", dbLoc);

        void Need(int min, MetadataObject o, string feature)
        {
            if (cl < min)
                r.Error("COMPAT-FEATURE", $"{feature} requires compatibilityLevel {min} or higher in Power BI mode, but the model is at {cl}", src.Locate(o), SourceIndex.Describe(o),
                    $"set 'compatibilityLevel: {min}' (or higher) in database.tmdl");
        }
        foreach (var t in model.Tables)
        {
            foreach (var m in t.Measures)
                if (m.FormatStringDefinition is not null) Need(1601, m.FormatStringDefinition, "A dynamic format string (formatStringDefinition)");
            foreach (var cal in t.Calendars) Need(1701, cal, "A calendar (calendar-based time intelligence)");
        }
        foreach (var f in model.Functions) Need(1702, f, "A DAX user-defined function");

        // ---------------- model-level Power BI conventions
        var modelLoc = src.Locate(model);
        if (string.IsNullOrWhiteSpace(model.Culture))
            r.Warn("PBI-MODEL", "model has no 'culture' (Power BI Desktop always writes one, for example 'culture: en-US')", modelLoc);
        if (model.DefaultPowerBIDataSourceVersion != PowerBIDataSourceVersion.PowerBI_V3)
            r.Warn("PBI-MODEL", $"defaultPowerBIDataSourceVersion is '{model.DefaultPowerBIDataSourceVersion}'; Power BI Desktop models use 'powerBI_V3' (enhanced metadata)", modelLoc);
        if (model.Annotations.Find("__PBI_TimeIntelligenceEnabled") is null)
            r.Info("PBI-MODEL", "model has no '__PBI_TimeIntelligenceEnabled' annotation (Desktop writes 0 or 1 for the Auto date/time setting)", modelLoc);
        if (model.Annotations.Find("PBI_QueryOrder") is { } qo)
        {
            try
            {
                var names = System.Text.Json.JsonSerializer.Deserialize<string[]>(qo.Value) ?? Array.Empty<string>();
                var known = new HashSet<string>(model.Tables.Select(t => t.Name).Concat(model.Expressions.Select(e => e.Name)), Ci);
                foreach (var n in names.Where(n => !known.Contains(n)))
                    r.Info("PBI-MODEL", $"PBI_QueryOrder lists '{n}', which is neither a table nor a shared expression", src.Locate(qo) ?? modelLoc);
            }
            catch (JsonException)
            {
                r.Warn("PBI-MODEL", "PBI_QueryOrder annotation is not a JSON array of query names", src.Locate(qo) ?? modelLoc);
            }
        }

        // ---------------- names and lineage tags
        foreach (var g in model.Tables.SelectMany(t => t.Measures).GroupBy(m => m.Name, Ci).Where(g => g.Count() > 1))
            foreach (var m in g.Skip(1))
                r.Error("NAME-DUP", $"measure name '{m.Name}' is used in more than one table ({string.Join(", ", g.Select(x => "'" + x.Table.Name + "'"))}); measure names must be unique in the model", src.Locate(m), SourceIndex.Describe(m));
        foreach (var t in model.Tables)
            foreach (var m in t.Measures.Where(m => t.Columns.Any(c => Ci.Equals(c.Name, m.Name))))
                r.Warn("NAME-CLASH", $"measure '{m.Name}' has the same name as a column of table '{t.Name}'; Analysis Services rejects this", src.Locate(m), SourceIndex.Describe(m));

        var tags = new Dictionary<string, MetadataObject>(StringComparer.Ordinal);
        void Tag(string kind, string? tag, MetadataObject o)
        {
            if (string.IsNullOrEmpty(tag)) return;
            if (!tags.TryAdd(kind + "|" + tag, o))
                r.Warn("LINEAGE-DUP", $"lineageTag '{tag}' is shared by {SourceIndex.Describe(tags[kind + "|" + tag])} and {SourceIndex.Describe(o)}; lineage tags must be unique (use a new GUID)", src.Locate(o), SourceIndex.Describe(o));
        }
        foreach (var t in model.Tables)
        {
            Tag("table", t.LineageTag, t);
            foreach (var c in t.Columns) Tag("column", c.LineageTag, c);
            foreach (var m in t.Measures) Tag("measure", m.LineageTag, m);
            foreach (var h in t.Hierarchies) { Tag("hierarchy", h.LineageTag, h); foreach (var l in h.Levels) Tag("level", l.LineageTag, l); }
        }
        foreach (var e in model.Expressions) Tag("expression", e.LineageTag, e);

        // ---------------- tables, columns, partitions
        foreach (var t in model.Tables)
        {
            var tLoc = src.Locate(t);
            if (t.Partitions.Count == 0)
                r.Warn("TABLE-NOPARTITION", $"table '{t.Name}' has no partition; Power BI needs one (m, calculated, entity or calculationGroup)", tLoc, SourceIndex.Describe(t));
            foreach (var p in t.Partitions)
            {
                switch (p.Source)
                {
                    case MPartitionSource mps when string.IsNullOrWhiteSpace(mps.Expression):
                        r.Error("PARTITION-EMPTY", $"partition '{p.Name}' has an empty M 'source' expression", src.Locate(p), SourceIndex.Describe(p)); break;
                    case CalculatedPartitionSource cps when string.IsNullOrWhiteSpace(cps.Expression):
                        r.Error("PARTITION-EMPTY", $"calculated partition '{p.Name}' has an empty DAX 'source' expression", src.Locate(p), SourceIndex.Describe(p)); break;
                    case null when t.CalculationGroup is null:
                        r.Error("PARTITION-EMPTY", $"partition '{p.Name}' has no source", src.Locate(p), SourceIndex.Describe(p)); break;
                }
            }
            bool hasM = t.Partitions.Any(p => p.Source is MPartitionSource);
            foreach (var c in t.Columns)
            {
                if (c.Type == ColumnType.RowNumber) continue;
                var cLoc = src.Locate(c);
                if (c is DataColumn dc)
                {
                    if (dc.DataType is DataType.Unknown or DataType.Automatic)
                        r.Error("COLUMN-TYPE", $"data column '{c.Name}' has no valid dataType (int64, double, decimal, string, dateTime, boolean, binary)", cLoc, SourceIndex.Describe(c));
                    if (hasM && string.IsNullOrWhiteSpace(dc.SourceColumn))
                        r.Warn("COLUMN-SOURCE", $"data column '{c.Name}' has no sourceColumn; it will not be mapped to any Power Query output column", cLoc, SourceIndex.Describe(c));
                }
                if (c is CalculatedColumn cc && string.IsNullOrWhiteSpace(cc.Expression))
                    r.Error("COLUMN-EXPR", $"calculated column '{c.Name}' has an empty expression", cLoc, SourceIndex.Describe(c));
                if (c.SortByColumn is not null && ReferenceEquals(c.SortByColumn, c))
                    r.Error("COLUMN-SORTBY", $"column '{c.Name}' is sorted by itself", cLoc, SourceIndex.Describe(c));
                if (c.SortByColumn is not null && c.SortByColumn.SortByColumn is not null)
                    r.Warn("COLUMN-SORTBY", $"column '{c.Name}' is sorted by '{c.SortByColumn.Name}', which itself has a sortByColumn (chained sorting is not allowed)", cLoc, SourceIndex.Describe(c));
            }
            var keys = t.Columns.Where(c => c.IsKey).ToList();
            if (keys.Count > 1)
                r.Warn("TABLE-KEY", $"table '{t.Name}' has {keys.Count} columns marked isKey; a table can have only one key column", tLoc, SourceIndex.Describe(t));
            if (Ci.Equals(t.DataCategory, "Time"))
            {
                if (keys.Count == 0)
                    r.Warn("DATE-TABLE", $"table '{t.Name}' has dataCategory: Time (marked as date table) but no column has isKey; mark the date column with isKey", tLoc, SourceIndex.Describe(t));
                else if (keys[0].DataType != DataType.DateTime)
                    r.Warn("DATE-TABLE", $"date table '{t.Name}' key column '{keys[0].Name}' is {keys[0].DataType}; it should be dateTime", src.Locate(keys[0]), SourceIndex.Describe(keys[0]));
            }
        }

        // ---------------- relationships
        foreach (var rel in model.Relationships.OfType<SingleColumnRelationship>())
        {
            if (rel.FromColumn is null || rel.ToColumn is null) continue; // reported by the loader as an unresolved reference
            var loc = src.Locate(rel);
            var desc = $"{Q(rel.FromColumn.Table.Name)}[{rel.FromColumn.Name}] -> {Q(rel.ToColumn.Table.Name)}[{rel.ToColumn.Name}]";
            if (ReferenceEquals(rel.FromColumn.Table, rel.ToColumn.Table))
                r.Warn("REL-SELF", $"relationship '{rel.Name}' ({desc}) connects a table to itself, which tabular models do not support", loc, SourceIndex.Describe(rel));
            // calculated-table columns usually carry no dataType in TMDL (inferred from DAX), so only compare declared types
            static bool Known(DataType t) => t is not (DataType.Unknown or DataType.Automatic);
            if (Known(rel.FromColumn.DataType) && Known(rel.ToColumn.DataType) && rel.FromColumn.DataType != rel.ToColumn.DataType)
                r.Warn("REL-TYPE", $"relationship '{rel.Name}' ({desc}) joins {rel.FromColumn.DataType} to {rel.ToColumn.DataType}; relationship columns should have the same data type", loc, SourceIndex.Describe(rel));
        }
        var activeGroups = model.Relationships.OfType<SingleColumnRelationship>()
            .Where(x => x.IsActive && x.FromColumn is not null && x.ToColumn is not null)
            .GroupBy(x => string.Join("|", new[] { x.FromColumn.Table.Name, x.ToColumn.Table.Name }.OrderBy(n => n, Ci)), Ci);
        foreach (var g in activeGroups.Where(g => g.Count() > 1))
            foreach (var rel in g.Skip(1))
                r.Warn("REL-ACTIVE", $"more than one active relationship between '{rel.FromColumn.Table.Name}' and '{rel.ToColumn.Table.Name}'; Power BI allows only one active relationship per table pair (set isActive: false on the others)", src.Locate(rel), SourceIndex.Describe(rel));

        // ---------------- shared expressions
        foreach (var e in model.Expressions)
        {
            var loc = src.Locate(e);
            if (string.IsNullOrWhiteSpace(e.Expression))
                r.Error("EXPR-EMPTY", $"expression '{e.Name}' is empty", loc, SourceIndex.Describe(e));
            bool isParam = e.Expression?.Contains("IsParameterQuery=true", StringComparison.OrdinalIgnoreCase) == true;
            if (isParam && e.Annotations.Find("PBI_ResultType") is null)
                r.Info("PBI-PARAM", $"parameter '{e.Name}' has no 'PBI_ResultType' annotation (Desktop writes e.g. 'annotation PBI_ResultType = Text')", loc, SourceIndex.Describe(e));
        }

        // ---------------- 'ref' lines that point at nothing (TMDL silently ignores them)
        var rxRef = new Regex(@"^ref[ \t]+(?<k>[A-Za-z]+)[ \t]+(?:'(?<q>(?:[^']|'')*)'|(?<n>[^ \t]+))[ \t]*$", RegexOptions.CultureInvariant);
        foreach (var f in src.Files)
            for (int i = 0; i < f.Lines.Length; i++)
            {
                var m = rxRef.Match(f.Lines[i]);
                if (!m.Success) continue;
                var kind = m.Groups["k"].Value;
                var name = m.Groups["q"].Success ? m.Groups["q"].Value.Replace("''", "'") : m.Groups["n"].Value;
                IEnumerable<string>? existing = kind.ToLowerInvariant() switch
                {
                    "table" => model.Tables.Select(x => x.Name),
                    "role" => model.Roles.Select(x => x.Name),
                    "perspective" => model.Perspectives.Select(x => x.Name),
                    "cultureinfo" or "culture" => model.Cultures.Select(x => x.Name),
                    "expression" => model.Expressions.Select(x => x.Name),
                    "datasource" => model.DataSources.Select(x => x.Name),
                    "function" => model.Functions.Select(x => x.Name),
                    _ => null,
                };
                if (existing is not null && !existing.Contains(name, Ci))
                    r.Warn("REF-MISSING", $"'ref {kind} {name}' points at a {kind} that is not declared in any file; TMDL silently ignores it (missing file or misspelled name?)", new Loc(f, i + 1));
            }
    }

    public static string Q(string name) => "'" + name.Replace("'", "''") + "'";
}

/// <summary>
/// Detects TMDL property lines that were absorbed into a DAX/M expression. When a multi-line expression is
/// indented at the same level as its object's properties, TOM keeps reading the following
/// "formatString: ..." / "lineageTag: ..." lines as expression text and loads the model without any error.
/// </summary>
public static class ExpressionChecks
{
    private static HashSet<string>? _props;

    /// <summary>All property names known to this TOM version's TMDL schema (dataType, formatString, lineageTag, ...).</summary>
    public static HashSet<string> TmdlPropertyNames
    {
        get
        {
            if (_props is not null) return _props;
            var set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            using var doc = JsonDocument.Parse(TmdlSerializer.GenerateSchema());
            void Walk(JsonElement e)
            {
                if (e.ValueKind == JsonValueKind.Object)
                    foreach (var p in e.EnumerateObject())
                    {
                        if (p.Name == "properties" && p.Value.ValueKind == JsonValueKind.Object)
                            foreach (var q in p.Value.EnumerateObject()) set.Add(q.Name);
                        Walk(p.Value);
                    }
                else if (e.ValueKind == JsonValueKind.Array)
                    foreach (var x in e.EnumerateArray()) Walk(x);
            }
            Walk(doc.RootElement);
            return _props = set;
        }
    }

    private static readonly Regex RxProp = new(@"^[ \t]*(?<kw>[A-Za-z][A-Za-z0-9]*)[ \t]*:", RegexOptions.CultureInvariant);
    private static readonly Regex RxChild = new(@"^[ \t]*(annotation|extendedProperty|changedProperty)[ \t]+\S", RegexOptions.CultureInvariant);

    public static void Run(Database db, Report r, SourceIndex src)
    {
        var model = db.Model;
        var items = DaxLint.Expressions(model)
            .Concat(model.Expressions.Select(e => ((MetadataObject)e, "expression", e.Expression ?? "")))
            .Concat(model.Tables.SelectMany(t => t.Partitions).Where(p => p.Source is MPartitionSource)
                .Select(p => ((MetadataObject)p, "partition source", ((MPartitionSource)p.Source).Expression ?? "")));
        foreach (var (owner, what, expr) in items)
        {
            var lines = expr.Replace("\r\n", "\n").Split('\n');
            for (int i = 0; i < lines.Length; i++)
            {
                var m = RxProp.Match(lines[i]);
                if (!(m.Success && TmdlPropertyNames.Contains(m.Groups["kw"].Value)) && !RxChild.IsMatch(lines[i])) continue;
                r.Error("EXPR-SWALLOWED",
                    $"{what} contains the TMDL line \"{lines[i].Trim()}\": the multi-line expression is indented at the same level as the object's properties, so the following property lines became part of the expression (TOM loads this without error)",
                    src.LocateExpressionLine(src.Locate(owner), expr, i, null), SourceIndex.Describe(owner),
                    "indent every line of a multi-line expression one level deeper than the object's properties (e.g. measure at 1 tab, its properties at 2 tabs, its expression lines at 3 tabs)");
                break;
            }
        }
    }
}

/// <summary>Heuristic DAX lint: lexical errors, bracket balance, references to unknown tables/columns/measures.</summary>
public static class DaxLint
{
    private enum K { Ident, Quoted, Bracket, Str, Num, LParen, RParen, LBrace, RBrace, Comma, Op }
    private readonly record struct Tok(K Kind, string Value, int Start, int End);

    private static (List<Tok> toks, List<(int pos, string msg)> errs) Lex(string s)
    {
        var toks = new List<Tok>();
        var errs = new List<(int, string)>();
        int i = 0, n = s.Length;
        while (i < n)
        {
            char c = s[i];
            if (char.IsWhiteSpace(c)) { i++; continue; }
            if ((c == '/' && i + 1 < n && s[i + 1] == '/') || (c == '-' && i + 1 < n && s[i + 1] == '-'))
            { while (i < n && s[i] != '\n') i++; continue; }
            if (c == '/' && i + 1 < n && s[i + 1] == '*')
            {
                int e = s.IndexOf("*/", i + 2, StringComparison.Ordinal);
                if (e < 0) { errs.Add((i, "unterminated /* comment */")); break; }
                i = e + 2; continue;
            }
            if (c is '"' or '\'' or '[')
            {
                char close = c == '[' ? ']' : c;
                int st = i++;
                var sb = new StringBuilder();
                bool closed = false;
                while (i < n)
                {
                    if (s[i] == close)
                    {
                        if (i + 1 < n && s[i + 1] == close) { sb.Append(close); i += 2; continue; }
                        i++; closed = true; break;
                    }
                    sb.Append(s[i++]);
                }
                var kind = c == '"' ? K.Str : c == '\'' ? K.Quoted : K.Bracket;
                if (!closed) errs.Add((st, kind switch { K.Str => "unterminated string literal (\")", K.Quoted => "unterminated quoted table name (')", _ => "unterminated [column/measure] reference" }));
                toks.Add(new Tok(kind, sb.ToString(), st, i));
                continue;
            }
            if (char.IsLetter(c) || c == '_')
            {
                int st = i;
                while (i < n && (char.IsLetterOrDigit(s[i]) || s[i] == '_' || s[i] == '.')) i++;
                toks.Add(new Tok(K.Ident, s[st..i], st, i));
                continue;
            }
            if (char.IsDigit(c) || (c == '.' && i + 1 < n && char.IsDigit(s[i + 1])))
            {
                int st = i;
                while (i < n && (char.IsLetterOrDigit(s[i]) || s[i] == '.')) i++;
                toks.Add(new Tok(K.Num, s[st..i], st, i));
                continue;
            }
            var k = c switch { '(' => K.LParen, ')' => K.RParen, '{' => K.LBrace, '}' => K.RBrace, ',' => K.Comma, _ => K.Op };
            toks.Add(new Tok(k, c.ToString(), i, i + 1));
            i++;
        }
        return (toks, errs);
    }

    private static readonly Regex Generated = new(@"^(Value\d*|Date)$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    public static IEnumerable<(MetadataObject owner, string what, string expr)> Expressions(Model model)
    {
        foreach (var t in model.Tables)
        {
            foreach (var m in t.Measures)
            {
                yield return (m, "measure", m.Expression ?? "");
                if (m.FormatStringDefinition?.Expression is { Length: > 0 } fs) yield return (m.FormatStringDefinition, "formatStringDefinition", fs);
                if (m.DetailRowsDefinition?.Expression is { Length: > 0 } dr) yield return (m.DetailRowsDefinition, "detailRowsDefinition", dr);
                if (m.KPI is { } k)
                {
                    if (!string.IsNullOrWhiteSpace(k.TargetExpression)) yield return (k, "KPI target", k.TargetExpression);
                    if (!string.IsNullOrWhiteSpace(k.StatusExpression)) yield return (k, "KPI status", k.StatusExpression);
                    if (!string.IsNullOrWhiteSpace(k.TrendExpression)) yield return (k, "KPI trend", k.TrendExpression);
                }
            }
            foreach (var c in t.Columns.OfType<CalculatedColumn>()) yield return (c, "calculated column", c.Expression ?? "");
            foreach (var p in t.Partitions)
                if (p.Source is CalculatedPartitionSource cps) yield return (p, "calculated table", cps.Expression ?? "");
            if (t.CalculationGroup is { } cg)
                foreach (var ci in cg.CalculationItems)
                {
                    yield return (ci, "calculation item", ci.Expression ?? "");
                    if (ci.FormatStringDefinition?.Expression is { Length: > 0 } cfs) yield return (ci.FormatStringDefinition, "calculation item format string", cfs);
                }
        }
        foreach (var role in model.Roles)
            foreach (var tp in role.TablePermissions)
                if (!string.IsNullOrWhiteSpace(tp.FilterExpression)) yield return (tp, "RLS filter", tp.FilterExpression);
    }

    public static void Run(Database db, Report r, SourceIndex src, bool strict)
    {
        var model = db.Model;
        var tables = new Dictionary<string, Table>(StringComparer.OrdinalIgnoreCase);
        foreach (var t in model.Tables) tables[t.Name] = t;
        var measures = new HashSet<string>(model.Tables.SelectMany(t => t.Measures).Select(m => m.Name), StringComparer.OrdinalIgnoreCase);
        var columns = new HashSet<string>(model.Tables.SelectMany(t => t.Columns).Select(c => c.Name), StringComparer.OrdinalIgnoreCase);

        foreach (var (owner, what, expr) in Expressions(model))
        {
            var (toks, lexErrs) = Lex(expr);
            var ownerLoc = src.Locate(owner);
            var objDesc = SourceIndex.Describe(owner);
            Loc? At(int pos, string? token) => src.LocateExpressionLine(ownerLoc, expr, LineOf(expr, pos), token);

            foreach (var (pos, msg) in lexErrs)
                r.Error("DAX-SYNTAX", $"{what}: {msg}", At(pos, null), objDesc);

            var stack = new Stack<Tok>();
            foreach (var t in toks)
            {
                if (t.Kind is K.LParen or K.LBrace) stack.Push(t);
                else if (t.Kind is K.RParen or K.RBrace)
                {
                    var want = t.Kind == K.RParen ? K.LParen : K.LBrace;
                    if (stack.Count == 0 || stack.Peek().Kind != want)
                    { r.Error("DAX-SYNTAX", $"{what}: unexpected '{t.Value}' (unbalanced brackets)", At(t.Start, null), objDesc); stack.Clear(); break; }
                    stack.Pop();
                }
            }
            if (stack.Count > 0)
                r.Error("DAX-SYNTAX", $"{what}: '{stack.Peek().Value}' is never closed (unbalanced brackets)", At(stack.Peek().Start, null), objDesc);

            var vars = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i + 1 < toks.Count; i++)
                if (toks[i].Kind == K.Ident && toks[i].Value.Equals("VAR", StringComparison.OrdinalIgnoreCase) && toks[i + 1].Kind == K.Ident)
                    vars.Add(toks[i + 1].Value);
            var literals = new HashSet<string>(toks.Where(t => t.Kind == K.Str).Select(t => t.Value), StringComparer.OrdinalIgnoreCase);

            void Ref(string msg, int pos, string token)
            {
                var f = Report.Make(strict ? Severity.Error : Severity.Warning, "DAX-REF", $"{what}: {msg}", At(pos, token), objDesc, null);
                r.Add(f);
            }

            for (int i = 0; i < toks.Count; i++)
            {
                var t = toks[i];
                bool qualified = (t.Kind is K.Ident or K.Quoted) && i + 1 < toks.Count && toks[i + 1].Kind == K.Bracket && toks[i + 1].Start == t.End;
                if (qualified)
                {
                    var col = toks[i + 1].Value;
                    var token = expr[t.Start..toks[i + 1].End];
                    i++;
                    if (vars.Contains(t.Value)) continue;
                    if (!tables.TryGetValue(t.Value, out var tbl))
                        Ref($"unknown table '{t.Value}' in {token}", t.Start, token);
                    else if (!tbl.Columns.Any(c => c.Name.Equals(col, StringComparison.OrdinalIgnoreCase)) &&
                             !tbl.Measures.Any(m => m.Name.Equals(col, StringComparison.OrdinalIgnoreCase)))
                        Ref($"table '{tbl.Name}' has no column or measure named [{col}] ({token})", t.Start, token);
                }
                else if (t.Kind == K.Bracket)
                {
                    if (!measures.Contains(t.Value) && !columns.Contains(t.Value) && !literals.Contains(t.Value) && !Generated.IsMatch(t.Value))
                        Ref($"[{t.Value}] matches no measure or column in the model", t.Start, "[" + t.Value);
                }
                else if (t.Kind == K.Quoted && !tables.ContainsKey(t.Value) && !vars.Contains(t.Value))
                    Ref($"unknown table '{t.Value}'", t.Start, "'" + t.Value);
            }
        }
    }

    public static int LineOf(string s, int pos)
    {
        int line = 0;
        for (int i = 0; i < pos && i < s.Length; i++) if (s[i] == '\n') line++;
        return line;
    }
}

/// <summary>Heuristic Power Query (M) lint: lexical errors, bracket balance, let/in balance, unresolved #"..." references.</summary>
public static class MLint
{
    private enum K { Ident, QIdent, Str, Num, Open, Close, Punct }
    private readonly record struct Tok(K Kind, string Value, int Start, int End);

    private static (List<Tok>, List<(int, string)>) Lex(string s)
    {
        var toks = new List<Tok>();
        var errs = new List<(int, string)>();
        int i = 0, n = s.Length;
        while (i < n)
        {
            char c = s[i];
            if (char.IsWhiteSpace(c)) { i++; continue; }
            if (c == '/' && i + 1 < n && s[i + 1] == '/') { while (i < n && s[i] != '\n') i++; continue; }
            if (c == '/' && i + 1 < n && s[i + 1] == '*')
            {
                int e = s.IndexOf("*/", i + 2, StringComparison.Ordinal);
                if (e < 0) { errs.Add((i, "unterminated /* comment */")); break; }
                i = e + 2; continue;
            }
            if (c == '"' || (c == '#' && i + 1 < n && s[i + 1] == '"'))
            {
                int st = i;
                bool q = c == '#';
                i += q ? 2 : 1;
                var sb = new StringBuilder();
                bool closed = false;
                while (i < n)
                {
                    if (s[i] == '"') { if (i + 1 < n && s[i + 1] == '"') { sb.Append('"'); i += 2; continue; } i++; closed = true; break; }
                    sb.Append(s[i++]);
                }
                if (!closed) errs.Add((st, q ? "unterminated quoted identifier #\"...\"" : "unterminated text literal \"...\""));
                toks.Add(new Tok(q ? K.QIdent : K.Str, sb.ToString(), st, i));
                continue;
            }
            if (char.IsLetter(c) || c == '_' || (c == '#' && i + 1 < n && char.IsLetter(s[i + 1])))
            {
                int st = i++;
                while (i < n && (char.IsLetterOrDigit(s[i]) || s[i] == '_' || s[i] == '.')) i++;
                toks.Add(new Tok(K.Ident, s[st..i], st, i));
                continue;
            }
            if (char.IsDigit(c))
            {
                int st = i;
                while (i < n && (char.IsLetterOrDigit(s[i]) || s[i] == '.')) i++;
                toks.Add(new Tok(K.Num, s[st..i], st, i));
                continue;
            }
            if (c is '(' or '[' or '{') { toks.Add(new Tok(K.Open, c.ToString(), i, i + 1)); i++; continue; }
            if (c is ')' or ']' or '}') { toks.Add(new Tok(K.Close, c.ToString(), i, i + 1)); i++; continue; }
            if (c == '=' && i + 1 < n && s[i + 1] == '>') { toks.Add(new Tok(K.Punct, "=>", i, i + 2)); i += 2; continue; }
            if ((c is '<' or '>') && i + 1 < n && (s[i + 1] == '=' || s[i + 1] == '>')) { toks.Add(new Tok(K.Punct, s.Substring(i, 2), i, i + 2)); i += 2; continue; }
            toks.Add(new Tok(K.Punct, c.ToString(), i, i + 1));
            i++;
        }
        return (toks, errs);
    }

    public static void Run(Database db, Report r, SourceIndex src, bool strict)
    {
        var model = db.Model;
        var queryNames = new HashSet<string>(model.Expressions.Select(e => e.Name).Concat(model.Tables.Select(t => t.Name)), StringComparer.Ordinal);
        var items = model.Expressions.Where(e => e.Kind == ExpressionKind.M).Select(e => ((MetadataObject)e, "expression", e.Expression ?? ""))
            .Concat(model.Tables.SelectMany(t => t.Partitions).Where(p => p.Source is MPartitionSource)
                .Select(p => ((MetadataObject)p, "partition source", ((MPartitionSource)p.Source).Expression ?? "")));
        foreach (var (owner, what, expr) in items)
        {
            var (toks, errs) = Lex(expr);
            var ownerLoc = src.Locate(owner);
            var objDesc = SourceIndex.Describe(owner);
            Loc? At(int pos, string? token) => src.LocateExpressionLine(ownerLoc, expr, DaxLint.LineOf(expr, pos), token);
            foreach (var (pos, msg) in errs) r.Error("M-SYNTAX", $"{what}: {msg}", At(pos, null), objDesc);

            var stack = new Stack<Tok>();
            bool bad = false;
            var inBrackets = new bool[toks.Count];
            for (int i = 0; i < toks.Count; i++)
            {
                var t = toks[i];
                inBrackets[i] = stack.Any(x => x.Value == "[");
                if (t.Kind == K.Open) stack.Push(t);
                else if (t.Kind == K.Close)
                {
                    var want = t.Value switch { ")" => "(", "]" => "[", _ => "{" };
                    if (stack.Count == 0 || stack.Peek().Value != want)
                    { r.Error("M-SYNTAX", $"{what}: unexpected '{t.Value}' (unbalanced brackets)", At(t.Start, null), objDesc); bad = true; break; }
                    stack.Pop();
                }
            }
            if (!bad && stack.Count > 0)
                r.Error("M-SYNTAX", $"{what}: '{stack.Peek().Value}' is never closed (unbalanced brackets)", At(stack.Peek().Start, null), objDesc);

            int lets = toks.Count(t => t.Kind == K.Ident && t.Value == "let");
            int ins = toks.Count(t => t.Kind == K.Ident && t.Value == "in");
            if (lets != ins)
                r.Add(Report.Make(strict ? Severity.Error : Severity.Warning, "M-LETIN", $"{what}: {lets} 'let' but {ins} 'in' keyword(s)", ownerLoc, objDesc, null));

            var defined = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i + 1 < toks.Count; i++)
            {
                bool startsBinding = i == 0 || (toks[i - 1].Kind == K.Ident && toks[i - 1].Value == "let") || (toks[i - 1].Kind == K.Punct && toks[i - 1].Value == ",");
                if (startsBinding && toks[i].Kind is K.QIdent or K.Ident && toks[i + 1].Kind == K.Punct && toks[i + 1].Value == "=")
                    defined.Add(toks[i].Value);
            }
            var reported = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < toks.Count; i++)
            {
                var t = toks[i];
                if (t.Kind != K.QIdent || inBrackets[i]) continue;
                if (i + 1 < toks.Count && toks[i + 1].Kind == K.Punct && toks[i + 1].Value == "=") continue;
                if (defined.Contains(t.Value) || queryNames.Contains(t.Value) || !reported.Add(t.Value)) continue;
                r.Add(Report.Make(strict ? Severity.Error : Severity.Warning, "M-REF",
                    $"{what}: #\"{t.Value}\" is not a step of this query, a shared expression/parameter or a table query", At(t.Start, "#\"" + t.Value), objDesc, null));
            }
        }
    }
}
