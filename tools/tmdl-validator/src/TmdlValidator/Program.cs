using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;
using Microsoft.AnalysisServices.Tabular.Serialization;
using Microsoft.AnalysisServices.Tabular.Tmdl;
using TomJson = Microsoft.AnalysisServices.Tabular.JsonSerializer;

namespace TmdlValidator;

public sealed class Options
{
    public string? Path;
    public string? RoundTripDir;
    public string? BimOut;
    public string? SchemaOut;
    public bool Json, LenientRefs, StrictHeuristics, NoHeuristics, WarningsAsErrors, NoSummary, NoInfo;

    public const string Usage = """
        Usage: tmdl-validate <path> [options]
          <path>                 TMDL 'definition' folder, or the *.SemanticModel folder that contains it
        Options:
          --roundtrip <dir>      Re-serialize the loaded model as TMDL into <dir> (new or empty folder),
                                 check the round trip is stable, and list files that differ from the source
          --bim <file>           Also write the loaded model as TMSL JSON (model.bim style)
          --schema <file>        Write the TMDL JSON schema of this TOM version to <file> and exit
          --json                 Print a machine-readable JSON report instead of text
          --lenient-refs         Do not treat unresolved object references as errors
          --strict               Treat heuristic DAX/M reference findings as errors
          --no-heuristics        Skip the heuristic DAX and M checks
          --warnings-as-errors   Exit with code 1 when there are warnings
          --no-summary           Do not print the model summary
          --no-info              Do not print INFO findings
        Exit codes: 0 = valid, 1 = errors found, 2 = bad arguments or path, 3 = validator crashed
        """;

    public static Options Parse(string[] args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            string Next() => i + 1 < args.Length ? args[++i] : throw new ArgumentException($"{args[i]} needs a value");
            switch (args[i])
            {
                case "--roundtrip": o.RoundTripDir = Next(); break;
                case "--bim": o.BimOut = Next(); break;
                case "--schema": o.SchemaOut = Next(); break;
                case "--json": o.Json = true; break;
                case "--lenient-refs": o.LenientRefs = true; break;
                case "--strict": o.StrictHeuristics = true; break;
                case "--no-heuristics": o.NoHeuristics = true; break;
                case "--warnings-as-errors": o.WarningsAsErrors = true; break;
                case "--no-summary": o.NoSummary = true; break;
                case "--no-info": o.NoInfo = true; break;
                case "-h" or "--help": throw new ArgumentException("");
                default:
                    if (args[i].StartsWith('-')) throw new ArgumentException($"Unknown option {args[i]}");
                    if (o.Path is not null) throw new ArgumentException("Only one path can be given");
                    o.Path = args[i]; break;
            }
        }
        if (o.Path is null && o.SchemaOut is null) throw new ArgumentException("Missing <path>");
        return o;
    }
}

public static class Program
{
    private static readonly Regex RxType = new(@"Parsing error type - (?<v>[^\r\n]+)", RegexOptions.CultureInvariant);
    private static readonly Regex RxDetail = new(@"Detailed error - (?<v>[^\r\n]+)", RegexOptions.CultureInvariant);

    public static int Main(string[] args)
    {
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        Options o;
        try { o = Options.Parse(args); }
        catch (ArgumentException ex)
        {
            if (ex.Message.Length > 0) Console.Error.WriteLine(ex.Message);
            Console.Error.WriteLine(Options.Usage);
            return 2;
        }
        try { return Run(o); }
        catch (Exception ex)
        {
            Console.Error.WriteLine("VALIDATOR CRASHED: " + ex);
            Console.WriteLine("RESULT: CRASHED");
            return 3;
        }
    }

    private static string TomVersion =>
        typeof(TmdlSerializer).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
        ?? typeof(TmdlSerializer).Assembly.GetName().Version?.ToString() ?? "?";

    private static int Run(Options o)
    {
        if (o.SchemaOut is not null)
        {
            using (var fs = File.Create(o.SchemaOut)) TmdlSerializer.GenerateSchema(fs);
            Console.WriteLine($"Wrote TMDL JSON schema (TOM {TomVersion}) to {System.IO.Path.GetFullPath(o.SchemaOut)}");
            if (o.Path is null) return 0;
        }

        var report = new Report();
        var defDir = ResolveDefinitionFolder(o.Path!, report);
        if (defDir is null) return Finish(o, report, null, null, null, pathProblem: true);

        var src = SourceIndex.Load(defDir, report);
        if (src.Files.Count == 0)
        {
            report.Error("PATH", $"No .tmdl files found under {defDir}");
            return Finish(o, report, defDir, src, null, pathProblem: true);
        }
        if (src.FindTop("model", null) is null) report.Warn("LAYOUT", "No 'model' declaration found (Power BI writes it to model.tmdl)");
        if (src.FindTop("database", null) is null) report.Info("LAYOUT", "No 'database' declaration found (Power BI writes database.tmdl with compatibilityLevel)");

        // Phase 1: parse every file on its own, so syntax errors in several files are reported in one run.
        var perFile = new List<Finding>();
        var lenientOpts = new MetadataDeserializationOptionsBuilder(MetadataSerializationStyle.Tmdl).WithoutErrorOnUnresolvedLinks().GetOptions();
        foreach (var f in src.Files)
        {
            try
            {
                var ctx = MetadataSerializationContext.Create(MetadataSerializationStyle.Tmdl);
                using var fs = File.OpenRead(f.FullPath);
                ctx.ReadFromDocument(fs);
                ctx.ToDatabase(lenientOpts, null);
            }
            catch (TmdlFormatException ex) { perFile.Add(FormatFinding(ex, f, src)); }
            catch (Exception) { /* isolation artefacts are ignored; the whole-folder load below is authoritative */ }
        }

        // Phase 2: load the whole folder the way Power BI tooling does (strict about unresolved references).
        var db = Load(defDir, strict: !o.LenientRefs, src, report, out bool refErrors);
        bool lenientFallback = false;
        if (db is null && refErrors)
        {
            db = Load(defDir, strict: false, src, null, out _);
            lenientFallback = db is not null;
        }
        if (db is null) foreach (var f in perFile) report.Add(f);

        if (db is not null)
        {
            if (lenientFallback)
                report.Info("LOAD", "Model loaded only with unresolved references ignored; checks below ran on that partial model");
            var vr = db.Model.Validate();
            foreach (var e in vr.Errors)
            {
                if (ResolutionMessages.Contains(e.Message)) continue; // already reported (with a better location) as UNRESOLVED-REF
                var loc = src.Locate(e.Source);
                if (loc is not null && RxValidateProp.Match(e.Message) is { Success: true } pm) loc = src.FindProperty(loc, pm.Groups["p"].Value) ?? loc;
                report.Error("TOM-VALIDATE", e.Message, loc, SourceIndex.Describe(e.Source));
            }
            ModelChecks.Run(db, report, src);
            ExpressionChecks.Run(db, report, src);
            if (!o.NoHeuristics)
            {
                DaxLint.Run(db, report, src, o.StrictHeuristics);
                MLint.Run(db, report, src, o.StrictHeuristics);
            }
        }
        else
        {
            report.Info("LOAD", "Model could not be loaded, so model-level, DAX and M checks were skipped; fix the errors above and re-run");
        }

        RoundTripResult? rt = null;
        if (db is not null && o.RoundTripDir is not null) rt = RoundTrip(db, src, o.RoundTripDir, report);
        if (db is not null && o.BimOut is not null)
        {
            var json = TomJson.SerializeDatabase(db, new SerializeOptions { IgnoreTimestamps = true, IgnoreInferredObjects = true, IgnoreInferredProperties = true, SplitMultilineStrings = true });
            File.WriteAllText(o.BimOut, json);
        }
        return Finish(o, report, defDir, src, db, pathProblem: false, rt);
    }

    // ---------------------------------------------------------------- path handling
    private static string? ResolveDefinitionFolder(string input, Report r)
    {
        var p = System.IO.Path.GetFullPath(input);
        if (File.Exists(p))
        {
            if (System.IO.Path.GetFileName(p).Equals("definition.pbism", StringComparison.OrdinalIgnoreCase)) p = System.IO.Path.GetDirectoryName(p)!;
            else { r.Error("PATH", $"'{p}' is a file; pass the TMDL 'definition' folder (or the .SemanticModel folder)"); return null; }
        }
        if (!Directory.Exists(p)) { r.Error("PATH", $"Folder not found: {p}"); return null; }
        string? smDir = null;
        bool tmdlHere = Directory.EnumerateFiles(p, "*.tmdl", SearchOption.TopDirectoryOnly).Any();
        var sub = System.IO.Path.Combine(p, "definition");
        if (!tmdlHere && Directory.Exists(sub)) { smDir = p; p = sub; }
        else if (System.IO.Path.GetFileName(p.TrimEnd('/')).Equals("definition", StringComparison.OrdinalIgnoreCase)) smDir = System.IO.Path.GetDirectoryName(p.TrimEnd('/'));

        if (smDir is not null)
        {
            var pbism = System.IO.Path.Combine(smDir, "definition.pbism");
            if (File.Exists(pbism))
            {
                try
                {
                    using var doc = JsonDocument.Parse(File.ReadAllText(pbism));
                    if (doc.RootElement.TryGetProperty("version", out var v))
                    {
                        var s = v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : v.ToString();
                        if (Version.TryParse(s.Contains('.') ? s : s + ".0", out var ver) && ver.Major < 4)
                            r.Error("PBISM", $"definition.pbism has version {s}; a TMDL 'definition' folder needs version 4.0 or higher ({pbism})");
                    }
                    else r.Warn("PBISM", $"definition.pbism has no 'version' property ({pbism})");
                }
                catch (JsonException ex) { r.Error("PBISM", $"definition.pbism is not valid JSON: {ex.Message} ({pbism})"); }
            }
            else if (smDir.EndsWith(".SemanticModel", StringComparison.OrdinalIgnoreCase))
                r.Warn("PBISM", $"No definition.pbism next to the definition folder; Power BI Desktop requires it (version 4.0+ for TMDL) ({smDir})");
            if (File.Exists(System.IO.Path.Combine(smDir, "model.bim")))
                r.Warn("PBISM", $"Both model.bim and a definition folder exist in {smDir}; keep only one model format");
        }
        return p;
    }

    // ---------------------------------------------------------------- loading
    private static Database? Load(string dir, bool strict, SourceIndex src, Report? report, out bool refErrors)
    {
        refErrors = false;
        var b = new MetadataDeserializationOptionsBuilder(MetadataSerializationStyle.Tmdl);
        if (strict) b.WithErrorOnUnresolvedLinks(); else b.WithoutErrorOnUnresolvedLinks();
        try { return TmdlSerializer.DeserializeDatabaseFromFolder(dir, b.GetOptions()); }
        catch (TmdlDeserializationWithReferenceErrorsException ex)
        {
            refErrors = true;
            foreach (var e in ex.ResolutionErrors)
            {
                var loc = src.LocatePath(e.SourceObject);
                if (loc is not null && !string.IsNullOrEmpty(e.PropertyName)) loc = src.FindProperty(loc, e.PropertyName) ?? loc;
                ResolutionMessages.Add(e.Error);
                var target = (e.TargetObject ?? "").Trim().TrimStart('{').TrimEnd('}').Trim();
                var prop = string.IsNullOrEmpty(e.PropertyName) ? "?" : char.ToLowerInvariant(e.PropertyName[0]) + e.PropertyName[1..];
                report?.Error("UNRESOLVED-REF", $"'{prop}' points at an object that does not exist: {target}", loc,
                    (e.SourceObject ?? "").Trim().TrimStart('{').TrimEnd('}').Trim(),
                    "check the spelling and quoting of the referenced name (TMDL references look like Table.'Column Name' or 'Table Name'.Column)");
            }
            if (ex.ResolutionErrors.Count == 0) report?.Error("UNRESOLVED-REF", Clean(ex.Message));
        }
        catch (TmdlFormatException ex) { report?.Add(FormatFinding(ex, null, src)); }
        catch (TmdlSerializationException ex)
        {
            var file = src.FindByDocument(ex.Document);
            var loc = src.LocatePath(ex.Message);
            if (loc is null && file is not null && ex.HasDocumentSourceInfo && ex.Line > 0) loc = new Loc(file, ex.Line);
            var msg = Clean(ex.Message);
            var hint = CompatHint(msg) ?? (msg.Contains("cannot be merged", StringComparison.Ordinal)
                ? "objects declared twice with the same name are merged into one (TMDL partial declarations), so a repeated property is an error: rename or remove the duplicate object"
                : null);
            report?.Error("TMDL-SEMANTIC", msg, loc, null, hint);
        }
        catch (CompatibilityViolationException ex)
        {
            var msg = Clean(ex.Message);
            report?.Error("COMPAT-FEATURE", msg, src.LocatePath(ex.Message), null, CompatHint(msg));
        }
        catch (Exception ex)
        {
            var msg = ex.GetType().Name + ": " + Clean(ex.Message);
            for (var inner = ex.InnerException; inner is not null; inner = inner.InnerException) msg += " -> " + inner.GetType().Name + ": " + Clean(inner.Message);
            report?.Error("TMDL-LOAD", msg, src.LocatePath(ex.Message));
        }
        return null;
    }

    private static readonly HashSet<string> ResolutionMessages = new(StringComparer.Ordinal);
    private static readonly Regex RxMinCompat = new(@"minimal compatab?ility level of (?<n>\d+)", RegexOptions.CultureInvariant);
    private static readonly Regex RxValidateProp = new(@"^Property (?<p>[A-Za-z]+) of object", RegexOptions.CultureInvariant);
    private static readonly Regex RxUnquotedDecl = new(
        @"^[ \t]*(?:ref[ \t]+)?(?<k>table|column|measure|partition|hierarchy|level|expression|role|perspective|relationship|calculationItem|function|cultureInfo|dataSource|tablePermission|calendar)[ \t]+(?<name>[^'=\r\n]*?)[ \t]*(=.*)?$",
        RegexOptions.CultureInvariant);

    private static string? CompatHint(string msg) =>
        RxMinCompat.Match(msg) is { Success: true } m ? $"raise 'compatibilityLevel' in database.tmdl to {m.Groups["n"].Value} or higher" : null;

    private static string Clean(string msg) => string.Join(" ", msg.Split('\n')
        .Select(l => l.Trim())
        .Where(l => l.Length > 0 && !l.StartsWith("Document -", StringComparison.Ordinal) && !l.StartsWith("Line Number -", StringComparison.Ordinal) && !l.StartsWith("Line -", StringComparison.Ordinal)));

    private static Finding FormatFinding(TmdlFormatException ex, SourceFile? file, SourceIndex src)
    {
        var type = RxType.Match(ex.Message) is { Success: true } mt ? mt.Groups["v"].Value.Trim() : "Format";
        var detail = RxDetail.Match(ex.Message) is { Success: true } md ? md.Groups["v"].Value.Trim() : Clean(ex.Message);
        file ??= src.FindByDocument(ex.Document);
        int? line = ex.HasDocumentSourceInfo && ex.Line > 0 ? ex.Line : null;
        var text = file?.LineAt(line ?? 0) ?? ex.LineText;
        int? col = text is null ? null : SourceIndex.IndentWidth(text) + 1;
        var ctx = new List<string>();
        if (file is not null && line is not null)
        {
            int prev = line.Value - 1;
            while (prev >= 1 && (file.LineAt(prev) ?? "").Trim().Length == 0) prev--;
            if (prev >= 1) ctx.Add($"  {prev,5} | {Report.Visible(file.LineAt(prev))}");
            ctx.Add($"> {line,5} | {Report.Visible(text)}");
            ctx.Add("          (→ = tab, · = space)");
        }
        string? hint = type switch
        {
            "Indentation" => "TMDL nests by leading whitespace: properties and child objects one level deeper than their object, multi-line expressions one level deeper than the properties. The real mistake is often on the previous non-blank line.",
            "UnknownKeyword" => "unknown property/object keyword in this context: check spelling (camelCase TOM names such as dataType, sourceColumn, formatString, summarizeBy) and that it sits under the right object; run with --schema to list valid properties",
            _ => null,
        };
        if (type == "InvalidName")
            hint = "names with spaces or . = : ' go in single quotes (a ' inside a name is written ''); column references use TMDL dot notation, e.g. fromColumn: Sales.'Order Date' (not DAX 'Sales'[Order Date])";
        if (type == "InvalidValueFormat" && Regex.Match(detail, @"expected type (?<t>[A-Za-z]+)") is { Success: true } et)
        {
            var enumType = typeof(TmdlSerializer).Assembly.GetType("Microsoft.AnalysisServices.Tabular." + et.Groups["t"].Value)
                ?? typeof(Microsoft.AnalysisServices.CompatibilityMode).Assembly.GetType("Microsoft.AnalysisServices." + et.Groups["t"].Value);
            if (enumType is { IsEnum: true })
                hint = "allowed values: " + string.Join(", ", Enum.GetNames(enumType).Select(n => char.ToLowerInvariant(n[0]) + n[1..]));
        }
        var trimmed = text?.TrimStart() ?? "";
        if (trimmed.StartsWith("//", StringComparison.Ordinal) && !trimmed.StartsWith("///", StringComparison.Ordinal))
            hint = "TMDL has no comment syntax: '//' lines are not allowed outside expressions. Use a '///' description line directly above an object, or put the comment inside the DAX/M expression";
        if (type == "InvalidLineType" && file is not null && line is not null)
        {
            int prev = line.Value - 1;
            while (prev >= 1 && (file.LineAt(prev) ?? "").Trim().Length == 0) prev--;
            if ((file.LineAt(prev) ?? "").TrimStart().StartsWith("///", StringComparison.Ordinal))
                hint = "a '///' description must be immediately followed by the object it describes: remove the blank line";
        }
        // TOM reports an unquoted name containing a space as an indentation error; say what is really wrong
        if (text is not null && RxUnquotedDecl.Match(text) is { Success: true } um && um.Groups["name"].Value.Trim().IndexOfAny(new[] { ' ', '\t' }) > 0)
            hint = $"the {um.Groups["k"].Value} name \"{um.Groups["name"].Value.Trim()}\" contains a space: names with spaces or . = : ' must be in single quotes, e.g. {um.Groups["k"].Value} '{um.Groups["name"].Value.Trim()}'";
        return new Finding
        {
            Severity = Severity.Error, Code = "TMDL-SYNTAX", Message = $"{detail} [{type}]",
            File = file?.RelPath ?? ex.Document, Line = line, Column = col, LineText = text, Context = ctx, Hint = hint,
        };
    }

    // ---------------------------------------------------------------- round trip
    public sealed class RoundTripResult
    {
        public string Folder { get; set; } = "";
        public bool StableTmdl { get; set; }
        public bool StableTmsl { get; set; }
        public List<string> TmslDifferences { get; } = new();
        public List<string> Same { get; } = new();
        public List<string> Differ { get; } = new();
        public List<string> OnlyInSource { get; } = new();
        public List<string> OnlyInOutput { get; } = new();
    }

    private static RoundTripResult? RoundTrip(Database db, SourceIndex src, string outDir, Report r)
    {
        outDir = System.IO.Path.GetFullPath(outDir);
        var root = System.IO.Path.GetFullPath(src.Root).TrimEnd('/') + "/";
        if ((outDir.TrimEnd('/') + "/").StartsWith(root, StringComparison.Ordinal) || root.StartsWith(outDir.TrimEnd('/') + "/", StringComparison.Ordinal))
        { r.Error("ROUNDTRIP", $"--roundtrip folder must be outside the source folder ({outDir})"); return null; }
        if (Directory.Exists(outDir) && Directory.EnumerateFileSystemEntries(outDir).Any())
        { r.Error("ROUNDTRIP", $"--roundtrip folder already exists and is not empty: {outDir}"); return null; }
        Directory.CreateDirectory(outDir);
        TmdlSerializer.SerializeDatabaseToFolder(db, outDir);

        var res = new RoundTripResult { Folder = outDir };
        var lenient = new MetadataDeserializationOptionsBuilder(MetadataSerializationStyle.Tmdl).WithoutErrorOnUnresolvedLinks().GetOptions();
        var db2 = TmdlSerializer.DeserializeDatabaseFromFolder(outDir, lenient);
        res.StableTmdl = TmdlSerializer.SerializeDatabase(db) == TmdlSerializer.SerializeDatabase(db2);
        var jo = new SerializeOptions { IgnoreTimestamps = true, IgnoreInferredObjects = true, IgnoreInferredProperties = true };
        var diffProps = new SortedSet<string>(StringComparer.Ordinal);
        using (var j1 = JsonDocument.Parse(TomJson.SerializeDatabase(db, jo)))
        using (var j2 = JsonDocument.Parse(TomJson.SerializeDatabase(db2, jo)))
            JsonDiff(j1.RootElement, j2.RootElement, "", diffProps);
        res.StableTmsl = diffProps.Count == 0;
        res.TmslDifferences.AddRange(diffProps);
        if (!res.StableTmdl)
            r.Warn("ROUNDTRIP", "Round trip is not stable: TOM serializes the re-loaded model differently from the original load");
        if (!res.StableTmsl)
        {
            var benign = new HashSet<string> { "dataType", "isDataTypeInferred" };
            var msg = $"TMSL of the re-loaded model differs in: {string.Join(", ", diffProps)}";
            if (diffProps.All(benign.Contains))
                r.Info("ROUNDTRIP", msg + " (the TMDL serializer omits inferred data types of calculated/calculated-table columns; harmless)");
            else
                r.Warn("ROUNDTRIP", msg + "; some information does not survive a TOM round trip");
        }

        static string[] Norm(IEnumerable<string> lines)
        {
            var l = lines.Select(x => x.TrimEnd()).ToList();
            while (l.Count > 0 && l[^1].Length == 0) l.RemoveAt(l.Count - 1);
            return l.ToArray();
        }
        var outFiles = Directory.EnumerateFiles(outDir, "*.tmdl", SearchOption.AllDirectories)
            .ToDictionary(p => System.IO.Path.GetRelativePath(outDir, p).Replace('\\', '/'), p => p, StringComparer.OrdinalIgnoreCase);
        foreach (var f in src.Files)
        {
            if (!outFiles.Remove(f.RelPath, out var op)) { res.OnlyInSource.Add(f.RelPath); continue; }
            var a = Norm(f.Lines);
            var b = Norm(File.ReadAllLines(op));
            int i = 0;
            while (i < a.Length && i < b.Length && a[i] == b[i]) i++;
            if (i == a.Length && i == b.Length) res.Same.Add(f.RelPath);
            else res.Differ.Add($"{f.RelPath} (first difference at line {i + 1}: source \"{Trunc(i < a.Length ? a[i] : "<end of file>")}\" vs output \"{Trunc(i < b.Length ? b[i] : "<end of file>")}\")");
        }
        res.OnlyInOutput.AddRange(outFiles.Keys.OrderBy(k => k, StringComparer.Ordinal));
        return res;
    }

    /// <summary>Collects the names of JSON properties whose values differ (or exist on one side only).</summary>
    private static void JsonDiff(JsonElement a, JsonElement b, string name, SortedSet<string> diffs)
    {
        if (diffs.Count > 50) return;
        if (a.ValueKind != b.ValueKind) { diffs.Add(name); return; }
        switch (a.ValueKind)
        {
            case JsonValueKind.Object:
                var bp = b.EnumerateObject().ToDictionary(p => p.Name, p => p.Value, StringComparer.Ordinal);
                foreach (var p in a.EnumerateObject())
                {
                    if (bp.Remove(p.Name, out var bv)) JsonDiff(p.Value, bv, p.Name, diffs);
                    else diffs.Add(p.Name);
                }
                foreach (var k in bp.Keys) diffs.Add(k);
                break;
            case JsonValueKind.Array:
                var aa = a.EnumerateArray().ToList();
                var ba = b.EnumerateArray().ToList();
                if (aa.Count != ba.Count) { diffs.Add(name); break; }
                for (int i = 0; i < aa.Count; i++) JsonDiff(aa[i], ba[i], name, diffs);
                break;
            default:
                if (a.GetRawText() != b.GetRawText()) diffs.Add(name);
                break;
        }
    }

    private static string Trunc(string s)
    {
        s = Report.Visible(s);
        return s.Length > 70 ? s[..70] + "..." : s;
    }

    // ---------------------------------------------------------------- summary
    public static object Summary(Database db)
    {
        var m = db.Model;
        string Col(Column? c) => c is null ? "(unresolved)" : $"{ModelChecks.Q(c.Table.Name)}[{c.Name}]";
        return new
        {
            database = new { name = db.Name, compatibilityLevel = db.CompatibilityLevel, compatibilityMode = db.CompatibilityMode.ToString() },
            model = new
            {
                culture = m.Culture, sourceQueryCulture = m.SourceQueryCulture,
                defaultPowerBIDataSourceVersion = m.DefaultPowerBIDataSourceVersion.ToString(),
                defaultMode = m.DefaultMode.ToString(),
                annotations = m.Annotations.Select(a => a.Name).ToArray(),
            },
            tables = m.Tables.Select(t => new
            {
                name = t.Name, isHidden = t.IsHidden, dataCategory = t.DataCategory,
                columns = t.Columns.Count(c => c.Type != ColumnType.RowNumber),
                calculatedColumns = t.Columns.OfType<CalculatedColumn>().Count(),
                measures = t.Measures.Count,
                hierarchies = t.Hierarchies.Count,
                keyColumn = t.Columns.FirstOrDefault(c => c.IsKey)?.Name,
                calculationGroup = t.CalculationGroup is not null,
                partitions = t.Partitions.Select(p => new { name = p.Name, sourceType = p.SourceType.ToString(), mode = p.Mode.ToString() }).ToArray(),
            }).ToArray(),
            relationships = m.Relationships.OfType<SingleColumnRelationship>().Select(r => new
            {
                name = r.Name, from = Col(r.FromColumn), to = Col(r.ToColumn),
                fromCardinality = r.FromCardinality.ToString(), toCardinality = r.ToCardinality.ToString(),
                crossFilteringBehavior = r.CrossFilteringBehavior.ToString(), isActive = r.IsActive,
            }).ToArray(),
            expressions = m.Expressions.Select(e => new
            {
                name = e.Name, kind = e.Kind.ToString(),
                isParameter = e.Expression?.Contains("IsParameterQuery=true", StringComparison.OrdinalIgnoreCase) == true,
                resultType = e.Annotations.Find("PBI_ResultType")?.Value,
            }).ToArray(),
            roles = m.Roles.Select(r => new { name = r.Name, modelPermission = r.ModelPermission.ToString(), tablePermissions = r.TablePermissions.Count }).ToArray(),
            perspectives = m.Perspectives.Select(p => p.Name).ToArray(),
            cultures = m.Cultures.Select(c => c.Name).ToArray(),
            functions = m.Functions.Select(f => f.Name).ToArray(),
            dataSources = m.DataSources.Select(d => d.Name).ToArray(),
        };
    }

    private static void WriteSummaryText(TextWriter w, Database db)
    {
        var m = db.Model;
        w.WriteLine("Model summary:");
        w.WriteLine($"  database: compatibilityLevel {db.CompatibilityLevel}, compatibilityMode {db.CompatibilityMode}, name '{db.Name}'");
        w.WriteLine($"  model: culture {m.Culture ?? "(none)"}, sourceQueryCulture {m.SourceQueryCulture ?? "(none)"}, defaultPowerBIDataSourceVersion {m.DefaultPowerBIDataSourceVersion}, defaultMode {m.DefaultMode}");
        if (m.Annotations.Count > 0) w.WriteLine($"  model annotations: {string.Join(", ", m.Annotations.Select(a => a.Name + "=" + Trunc(a.Value ?? "")))}");
        w.WriteLine($"  tables ({m.Tables.Count}):");
        foreach (var t in m.Tables)
        {
            var extras = new List<string>();
            if (!string.IsNullOrEmpty(t.DataCategory)) extras.Add($"dataCategory {t.DataCategory}");
            if (t.Columns.FirstOrDefault(c => c.IsKey) is { } key) extras.Add($"key '{key.Name}'");
            if (t.IsHidden) extras.Add("hidden");
            if (t.CalculationGroup is not null) extras.Add("calculation group");
            int cols = t.Columns.Count(c => c.Type != ColumnType.RowNumber);
            int calc = t.Columns.OfType<CalculatedColumn>().Count();
            var parts = string.Join("; ", t.Partitions.Select(p => $"{p.Name} [{p.SourceType}, {p.Mode}]"));
            w.WriteLine($"    {ModelChecks.Q(t.Name)}{(extras.Count > 0 ? " (" + string.Join(", ", extras) + ")" : "")}: {cols} columns ({calc} calculated), {t.Measures.Count} measures, {t.Hierarchies.Count} hierarchies, {t.Partitions.Count} partition(s): {parts}");
        }
        var rels = m.Relationships.OfType<SingleColumnRelationship>().ToList();
        w.WriteLine($"  relationships ({rels.Count}):");
        foreach (var r in rels)
        {
            string C(Column? c) => c is null ? "(unresolved)" : $"{ModelChecks.Q(c.Table.Name)}[{c.Name}]";
            w.WriteLine($"    {C(r.FromColumn)} ({r.FromCardinality}) -> {C(r.ToColumn)} ({r.ToCardinality}), {r.CrossFilteringBehavior}, {(r.IsActive ? "active" : "inactive")}  [{r.Name}]");
        }
        w.WriteLine($"  expressions ({m.Expressions.Count}):");
        foreach (var e in m.Expressions)
        {
            bool p = e.Expression?.Contains("IsParameterQuery=true", StringComparison.OrdinalIgnoreCase) == true;
            w.WriteLine($"    {ModelChecks.Q(e.Name)}: {e.Kind}{(p ? ", parameter" : "")}{(e.Annotations.Find("PBI_ResultType") is { } a ? ", PBI_ResultType=" + a.Value : "")}");
        }
        if (m.Roles.Count > 0) w.WriteLine($"  roles ({m.Roles.Count}): {string.Join(", ", m.Roles.Select(r => $"{ModelChecks.Q(r.Name)} ({r.ModelPermission}, {r.TablePermissions.Count} table permission(s))"))}");
        if (m.Perspectives.Count > 0) w.WriteLine($"  perspectives: {string.Join(", ", m.Perspectives.Select(p => p.Name))}");
        if (m.Cultures.Count > 0) w.WriteLine($"  cultures: {string.Join(", ", m.Cultures.Select(c => c.Name))}");
        if (m.Functions.Count > 0) w.WriteLine($"  functions: {string.Join(", ", m.Functions.Select(f => f.Name))}");
        if (m.DataSources.Count > 0) w.WriteLine($"  dataSources: {string.Join(", ", m.DataSources.Select(d => d.Name))}");
    }

    // ---------------------------------------------------------------- output
    private static int Finish(Options o, Report report, string? defDir, SourceIndex? src, Database? db, bool pathProblem, RoundTripResult? rt = null)
    {
        int errors = report.Count(Severity.Error), warnings = report.Count(Severity.Warning), infos = report.Count(Severity.Info);
        bool failed = errors > 0 || (o.WarningsAsErrors && warnings > 0);
        string result = failed ? "FAILED" : "OK";
        if (o.Json)
        {
            var doc = new
            {
                result, errors, warnings, infos,
                validator = new { tom = TomVersion, runtime = RuntimeInformation.FrameworkDescription, os = RuntimeInformation.OSDescription, arch = RuntimeInformation.ProcessArchitecture.ToString() },
                folder = defDir, files = src?.Files.Select(f => f.RelPath).ToArray(),
                modelLoaded = db is not null,
                findings = report.Findings.Where(f => !o.NoInfo || f.Severity != Severity.Info)
                    .OrderBy(f => f.Severity).ThenBy(f => f.File ?? "￿", StringComparer.Ordinal).ThenBy(f => f.Line ?? 0),
                summary = db is null ? null : Summary(db),
                roundTrip = rt,
            };
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(doc, Report.JsonOpts));
        }
        else
        {
            var w = Console.Out;
            w.WriteLine($"TMDL validator | TOM {TomVersion} | {RuntimeInformation.FrameworkDescription} | {RuntimeInformation.OSDescription} {RuntimeInformation.ProcessArchitecture}");
            if (defDir is not null) w.WriteLine($"Folder: {defDir} ({src?.Files.Count ?? 0} .tmdl files)");
            w.WriteLine();
            if (report.Findings.Count > 0)
            {
                report.WriteText(w, includeInfo: !o.NoInfo);
                w.WriteLine();
            }
            if (db is not null && !o.NoSummary) { WriteSummaryText(w, db); w.WriteLine(); }
            if (rt is not null)
            {
                w.WriteLine($"Round trip -> {rt.Folder}");
                w.WriteLine($"  stable (TOM re-reads its own output identically): TMDL {rt.StableTmdl}, TMSL {rt.StableTmsl}");
                w.WriteLine($"  identical files: {rt.Same.Count}, differing: {rt.Differ.Count}, only in source: {rt.OnlyInSource.Count}, only in output: {rt.OnlyInOutput.Count}");
                foreach (var d in rt.Differ) w.WriteLine("  differs: " + d);
                foreach (var d in rt.OnlyInSource) w.WriteLine("  only in source: " + d);
                foreach (var d in rt.OnlyInOutput) w.WriteLine("  only in output: " + d);
                w.WriteLine($"  inspect with: diff -ru '{defDir}' '{rt.Folder}'");
                w.WriteLine();
            }
            w.WriteLine($"RESULT: {result} ({errors} error(s), {warnings} warning(s), {infos} info)");
        }
        if (pathProblem) return 2;
        return failed ? 1 : 0;
    }
}
