using System.Text;
using System.Text.RegularExpressions;
using Microsoft.AnalysisServices.Tabular;

namespace TmdlValidator;

public sealed class SourceFile
{
    public required string FullPath { get; init; }
    public required string RelPath { get; init; }
    public required string[] Lines { get; init; }
    public string? LineAt(int line) => line >= 1 && line <= Lines.Length ? Lines[line - 1] : null;
}

/// <summary>1-based line (and optional 1-based column) inside a TMDL file.</summary>
public sealed record Loc(SourceFile File, int Line, int? Column = null)
{
    public int Indent => SourceIndex.IndentWidth(File.LineAt(Line) ?? "");
}

public sealed class SourceIndex
{
    public string Root { get; }
    public List<SourceFile> Files { get; } = new();
    private readonly Dictionary<MetadataObject, Loc?> _cache = new(ReferenceEqualityComparer.Instance);

    private SourceIndex(string root) => Root = root;

    // ------------------------------------------------------------------ loading + file lint
    public static SourceIndex Load(string root, Report report)
    {
        var idx = new SourceIndex(root);
        var strictUtf8 = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true);
        var paths = Directory.EnumerateFiles(root, "*.tmdl", SearchOption.AllDirectories)
            .OrderBy(p => p, StringComparer.Ordinal).ToList();
        foreach (var path in paths)
        {
            var rel = Path.GetRelativePath(root, path).Replace('\\', '/');
            var bytes = File.ReadAllBytes(path);
            int offset = 0;
            bool bom = bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF;
            if (bom) offset = 3;
            bool utf16 = bytes.Length >= 2 && ((bytes[0] == 0xFF && bytes[1] == 0xFE) || (bytes[0] == 0xFE && bytes[1] == 0xFF));
            string text;
            string? encodingError = null;
            try { text = strictUtf8.GetString(bytes, offset, bytes.Length - offset); }
            catch (DecoderFallbackException ex)
            {
                encodingError = $"File is not valid UTF-8 (invalid byte sequence near byte {ex.Index + offset})";
                text = Encoding.UTF8.GetString(bytes, offset, bytes.Length - offset);
            }
            int crlf = 0, lf = 0, cr = 0;
            for (int i = 0; i < text.Length; i++)
            {
                if (text[i] == '\r') { if (i + 1 < text.Length && text[i + 1] == '\n') { crlf++; i++; } else cr++; }
                else if (text[i] == '\n') lf++;
            }
            var lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
            if (lines.Length > 0 && lines[^1].Length == 0) lines = lines[..^1];
            var sf = new SourceFile { FullPath = path, RelPath = rel, Lines = lines };
            idx.Files.Add(sf);
            var first = new Loc(sf, 1);

            if (utf16) report.Error("FILE-ENCODING", "File looks like UTF-16; TMDL files must be UTF-8 (without BOM)", first);
            else if (encodingError is not null) report.Error("FILE-ENCODING", encodingError, first);
            if (bom) report.Warn("FILE-BOM", "File starts with a UTF-8 BOM; Power BI project files should be saved as UTF-8 without BOM", first);
            if (crlf > 0 && lf > 0) report.Warn("FILE-EOL", $"Mixed line endings ({crlf} CRLF, {lf} LF); Power BI Desktop writes CRLF, keep one style per file", first);
            if (cr > 0) report.Warn("FILE-EOL", $"{cr} bare CR line ending(s) found", first);
            if (text.Trim().Length == 0) report.Warn("FILE-EMPTY", "File is empty", first);
            LintIndentation(sf, report);
        }
        return idx;
    }

    private static void LintIndentation(SourceFile f, Report report)
    {
        int tabLines = 0, spaceLines = 0, firstTab = 0, firstSpace = 0, weird = 0;
        bool inFence = false;
        for (int i = 0; i < f.Lines.Length; i++)
        {
            var l = f.Lines[i];
            var t = l.Trim();
            if (inFence) { if (t == "```") inFence = false; continue; }   // verbatim ``` block content is not structural
            if (t.Length > 3 && t.EndsWith("```", StringComparison.Ordinal)) inFence = true; // "... = ```" opens a block
            if (t.Length == 0 || IndentWidth(l) == 0) continue;
            if (l[0] == '\t') { tabLines++; if (firstTab == 0) firstTab = i + 1; }
            else { spaceLines++; if (firstSpace == 0) firstSpace = i + 1; }
            var ws = l[..IndentWidth(l)];
            if (ws.Contains(" \t", StringComparison.Ordinal) && weird++ == 0)
                report.Warn("INDENT-MIXED", "Indentation has a space before a tab; TMDL nesting is decided by leading whitespace, keep it consistent (tabs, like Power BI Desktop)", new Loc(f, i + 1));
        }
        if (tabLines > 0 && spaceLines > 0)
        {
            int minorityLine = tabLines >= spaceLines ? firstSpace : firstTab;
            report.Warn("INDENT-MIXED",
                $"File mixes tab-indented ({tabLines}) and space-indented ({spaceLines}) lines; TMDL nesting is decided by leading whitespace and Power BI Desktop uses tabs",
                new Loc(f, minorityLine));
        }
        else if (spaceLines > 0)
            report.Info("INDENT-SPACES", "File is indented with spaces; the parser accepts it, but Power BI Desktop rewrites it with tabs (noisy diffs)", new Loc(f, firstSpace));
    }

    // ------------------------------------------------------------------ helpers
    public static int IndentWidth(string line)
    {
        int i = 0;
        while (i < line.Length && (line[i] == ' ' || line[i] == '\t')) i++;
        return i;
    }

    public SourceFile? FindByDocument(string? document)
    {
        if (string.IsNullOrWhiteSpace(document)) return null;
        var d = document.Replace('\\', '/');
        if (Path.IsPathRooted(d)) d = Path.GetRelativePath(Root, d).Replace('\\', '/');
        while (d.StartsWith("./", StringComparison.Ordinal)) d = d[2..];
        return Files.FirstOrDefault(f => string.Equals(f.RelPath, d, StringComparison.OrdinalIgnoreCase))
            ?? Files.FirstOrDefault(f => f.RelPath.EndsWith("/" + d, StringComparison.OrdinalIgnoreCase))
            // TOM reports logical document names without the extension, e.g. "./tables/Sales"
            ?? (d.EndsWith(".tmdl", StringComparison.OrdinalIgnoreCase) ? null : FindByDocument(d + ".tmdl"));
    }

    public static bool NeedsQuotes(string name) =>
        name.Length == 0 || name.IndexOfAny(new[] { '.', '=', ':', '\'', ' ', '\t', '"' }) >= 0 || name != name.Trim();

    private static string NamePattern(string name)
    {
        var quoted = "'" + Regex.Escape(name.Replace("'", "''")) + "'";
        return NeedsQuotes(name) ? quoted : "(?:" + quoted + "|" + Regex.Escape(name) + ")";
    }

    private static Regex DeclRx(string keyword, string? name) => new(
        @"^[ \t]*" + Regex.Escape(keyword) +
        (name is null ? @"(?![A-Za-z0-9_])" : @"[ \t]+" + NamePattern(name) + @"(?=[ \t]*(=|$))"),
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>Top-level declaration (indent 0, not a 'ref' line).</summary>
    public Loc? FindTop(string keyword, string? name)
    {
        var rx = DeclRx(keyword, name);
        foreach (var f in Files)
            for (int i = 0; i < f.Lines.Length; i++)
                if (IndentWidth(f.Lines[i]) == 0 && rx.IsMatch(f.Lines[i])) return new Loc(f, i + 1);
        return null;
    }

    /// <summary>Last line (1-based) of the block that starts at <paramref name="parent"/>.</summary>
    public static int BlockEnd(Loc parent)
    {
        var lines = parent.File.Lines;
        int ind = parent.Indent;
        for (int i = parent.Line; i < lines.Length; i++)
        {
            var l = lines[i];
            if (l.Trim().Length == 0) continue;
            if (IndentWidth(l) <= ind) return i; // line i (0-based) is outside => block ends at i (1-based previous)
        }
        return lines.Length;
    }

    public Loc? FindChild(Loc parent, string keyword, string? name)
    {
        var rx = DeclRx(keyword, name);
        int end = BlockEnd(parent);
        var lines = parent.File.Lines;
        for (int i = parent.Line; i < end; i++)
            if (IndentWidth(lines[i]) > parent.Indent && rx.IsMatch(lines[i])) return new Loc(parent.File, i + 1);
        // partial declarations: the same table may be declared in several files
        if (parent.Indent == 0)
        {
            var header = parent.File.Lines[parent.Line - 1];
            foreach (var f in Files)
                for (int i = 0; i < f.Lines.Length; i++)
                {
                    if ((f == parent.File && i + 1 == parent.Line) || f.Lines[i] != header) continue;
                    var other = new Loc(f, i + 1);
                    int e2 = BlockEnd(other);
                    for (int j = i + 1; j < e2; j++)
                        if (IndentWidth(f.Lines[j]) > 0 && rx.IsMatch(f.Lines[j])) return new Loc(f, j + 1);
                }
        }
        return null;
    }

    /// <summary>Finds the line inside a block whose content starts with "property:" (or "property =").</summary>
    public Loc? FindProperty(Loc parent, string property)
    {
        var rx = new Regex(@"^[ \t]+" + Regex.Escape(property) + @"[ \t]*(:|=|$)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        int end = BlockEnd(parent);
        for (int i = parent.Line; i < end; i++)
            if (rx.IsMatch(parent.File.Lines[i])) return new Loc(parent.File, i + 1);
        return null;
    }

    // ------------------------------------------------------------------ TOM object -> location
    public Loc? Locate(MetadataObject? obj)
    {
        if (obj is null) return null;
        if (_cache.TryGetValue(obj, out var cached)) return cached;
        Loc? r = obj switch
        {
            Model => FindTop("model", null),
            Table t => FindTop("table", t.Name),
            Column c => Child(c.Table, "column", c.Name),
            Measure m => Child(m.Table, "measure", m.Name),
            Partition p => Child(p.Table, "partition", p.Name),
            Hierarchy h => Child(h.Table, "hierarchy", h.Name),
            Level l => Child(l.Hierarchy, "level", l.Name),
            CalculationItem ci => Child(ci.CalculationGroup?.Table, "calculationItem", ci.Name),
            CalculationGroup cg => Child(cg.Table, "calculationGroup", null),
            KPI k => Child(k.Measure, "kpi", null),
            FormatStringDefinition f => Child(f.Parent, "formatStringDefinition", null),
            DetailRowsDefinition d => Child(d.Parent, "detailRowsDefinition", null),
            Relationship rel => FindTop("relationship", rel.Name),
            NamedExpression e => FindTop("expression", e.Name),
            ModelRole role => FindTop("role", role.Name),
            TablePermission tp => Child(tp.Role, "tablePermission", tp.Table?.Name ?? tp.Name),
            Perspective p => FindTop("perspective", p.Name),
            Culture cu => FindTop("cultureInfo", cu.Name),
            DataSource ds => FindTop("dataSource", ds.Name),
            Function fn => FindTop("function", fn.Name),
            Calendar cal => Child(cal.Parent, "calendar", cal.Name),
            Annotation a => Child(a.Parent, "annotation", a.Name),
            _ => null,
        };
        r ??= obj.Parent is null ? null : Locate(obj.Parent);
        _cache[obj] = r;
        return r;
    }

    private Loc? Child(MetadataObject? parent, string keyword, string? name)
    {
        var p = Locate(parent);
        return p is null ? null : FindChild(p, keyword, name) ?? p;
    }

    // ------------------------------------------------------------------ "[table 'X'].[measure 'Y'].Prop" paths from TOM messages
    // style 1 (exception messages): [model Model].[table Sales].[measure 'X'].FormatStringDefinition
    private static readonly Regex RxPathSeg = new(@"\[(?<k>[A-Za-z]+) (?:'(?<q>(?:[^']|'')*)'|(?<n>[^\]]*))\](?:\.(?<prop>[A-Za-z]+))?",
        RegexOptions.CultureInvariant);
    // style 2 (SerializationReferenceError): { Table: 'Date', Column: 'Month Name' }
    private static readonly Regex RxBraceSeg = new(@"(?<k>[A-Za-z]+): '(?<q>(?:[^']|'')*)'", RegexOptions.CultureInvariant);

    public Loc? LocatePath(string? text)
    {
        if (string.IsNullOrEmpty(text)) return null;
        var segs = new List<(string kind, string name, string? prop)>();
        var t = text.TrimStart();
        if (t.StartsWith('{'))
            foreach (Match m in RxBraceSeg.Matches(t))
                segs.Add((m.Groups["k"].Value, m.Groups["q"].Value.Replace("''", "'"), null));
        else
            foreach (Match m in RxPathSeg.Matches(text))
                segs.Add((m.Groups["k"].Value, m.Groups["q"].Success ? m.Groups["q"].Value.Replace("''", "'") : m.Groups["n"].Value,
                          m.Groups["prop"].Success ? m.Groups["prop"].Value : null));
        Loc? loc = null;
        string? lastProp = null;
        foreach (var (k, name, prop) in segs)
        {
            var kind = char.ToLowerInvariant(k[0]) + k[1..];
            if (kind is "model" or "database") continue; // tables, roles, ... are top-level in TMDL
            if (kind == "culture") kind = "cultureInfo";
            var next = loc is null ? FindTop(kind, name) : FindChild(loc, kind, name);
            if (next is null) break;
            loc = next;
            lastProp = prop;
        }
        if (loc is not null && lastProp is not null)
            loc = FindChild(loc, char.ToLowerInvariant(lastProp[0]) + lastProp[1..], null) ?? FindProperty(loc, lastProp) ?? loc;
        return loc;
    }

    /// <summary>Maps a line inside an expression to the file line where it appears, starting the search at the owner's declaration.</summary>
    public Loc? LocateExpressionLine(Loc? owner, string expression, int exprLineIndex, string? token)
    {
        if (owner is null) return null;
        var exprLines = expression.Replace("\r\n", "\n").Split('\n');
        if (exprLineIndex < 0 || exprLineIndex >= exprLines.Length) return owner;
        var target = exprLines[exprLineIndex].Trim();
        int end = Math.Max(BlockEnd(owner), owner.Line);
        // collect candidate lines whose trimmed text contains the trimmed expression line
        var lines = owner.File.Lines;
        int occurrence = 0;
        for (int k = 0; k < exprLineIndex; k++) if (exprLines[k].Trim() == target) occurrence++;
        int seen = 0;
        for (int i = owner.Line - 1; i < end; i++)
        {
            var l = lines[i];
            bool match = target.Length == 0 ? false : (i == owner.Line - 1 ? l.Contains(target, StringComparison.Ordinal) : l.Trim() == target || l.Trim().EndsWith(target, StringComparison.Ordinal));
            if (!match) continue;
            if (seen++ < occurrence) continue;
            int? col = null;
            if (token is not null) { var ix = l.IndexOf(token, StringComparison.Ordinal); if (ix >= 0) col = ix + 1; }
            return new Loc(owner.File, i + 1, col);
        }
        return owner;
    }

    public static string Describe(MetadataObject? o)
    {
        var parts = new List<string>();
        for (var x = o; x is not null && x is not Model; x = x.Parent)
        {
            var kind = x.ObjectType.ToString();
            kind = char.ToLowerInvariant(kind[0]) + kind[1..];
            var name = (x as NamedMetadataObject)?.Name;
            parts.Add(string.IsNullOrEmpty(name) ? kind : $"{kind} '{name}'");
        }
        parts.Reverse();
        return parts.Count == 0 ? "model" : string.Join(" / ", parts);
    }
}
