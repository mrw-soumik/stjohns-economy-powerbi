using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TmdlValidator;

public enum Severity { Error, Warning, Info }

public sealed class Finding
{
    public Severity Severity { get; set; }
    public string Code { get; set; } = "";
    public string Message { get; set; } = "";
    public string? File { get; set; }
    public int? Line { get; set; }
    public int? Column { get; set; }
    public string? LineText { get; set; }
    public string? Object { get; set; }
    public string? Hint { get; set; }
    public List<string>? Context { get; set; }
}

public sealed class Report
{
    public List<Finding> Findings { get; } = new();
    private readonly HashSet<string> _seen = new(StringComparer.Ordinal);

    public void Add(Finding f)
    {
        var key = $"{f.Severity}|{f.Code}|{f.File}|{f.Line}|{f.Message}";
        if (_seen.Add(key)) Findings.Add(f);
    }

    public void Error(string code, string msg, Loc? loc = null, string? obj = null, string? hint = null) =>
        Add(Make(Severity.Error, code, msg, loc, obj, hint));
    public void Warn(string code, string msg, Loc? loc = null, string? obj = null, string? hint = null) =>
        Add(Make(Severity.Warning, code, msg, loc, obj, hint));
    public void Info(string code, string msg, Loc? loc = null, string? obj = null, string? hint = null) =>
        Add(Make(Severity.Info, code, msg, loc, obj, hint));

    public static Finding Make(Severity s, string code, string msg, Loc? loc, string? obj, string? hint) => new()
    {
        Severity = s, Code = code, Message = msg, Object = obj, Hint = hint,
        File = loc?.File.RelPath, Line = loc?.Line, Column = loc?.Column,
        LineText = loc is null ? null : loc.File.LineAt(loc.Line),
    };

    public int Count(Severity s) => Findings.Count(f => f.Severity == s);

    public static string Visible(string? line)
    {
        if (line is null) return "";
        int i = 0;
        var sb = new StringBuilder();
        while (i < line.Length && (line[i] == '\t' || line[i] == ' '))
        {
            sb.Append(line[i] == '\t' ? "→" : "·"); // → for tab, · for space
            i++;
        }
        sb.Append(line[i..]);
        return sb.ToString();
    }

    public void WriteText(TextWriter w, bool includeInfo)
    {
        var ordered = Findings
            .Where(f => includeInfo || f.Severity != Severity.Info)
            .OrderBy(f => f.Severity)
            .ThenBy(f => f.File ?? "￿", StringComparer.Ordinal)
            .ThenBy(f => f.Line ?? 0);
        foreach (var f in ordered)
        {
            var sev = f.Severity switch { Severity.Error => "ERROR", Severity.Warning => "WARNING", _ => "INFO" };
            var where = f.File is null ? "" : f.File + (f.Line is null ? "" : ":" + f.Line + (f.Column is null ? "" : ":" + f.Column)) + ": ";
            w.WriteLine($"{sev} [{f.Code}] {where}{f.Message}");
            if (f.Object is not null) w.WriteLine($"    object: {f.Object}");
            if (f.Context is { Count: > 0 })
                foreach (var c in f.Context) w.WriteLine("    " + c);
            else if (f.LineText is not null && f.Line is not null)
                w.WriteLine($"    {f.Line,5} | {Visible(f.LineText)}");
            if (f.Hint is not null) w.WriteLine($"    hint: {f.Hint}");
        }
    }

    public static readonly JsonSerializerOptions JsonOpts = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        Converters = { new JsonStringEnumConverter(JsonNamingPolicy.CamelCase) },
    };
}
