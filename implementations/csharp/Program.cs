using System.Globalization;
using System.Text;

internal sealed class ServiceStats
{
    public long Count;
    public long Errors;
    public long LatencySum;
}

internal sealed class ParseResult
{
    public long Lines;
    public long Valid;
    public long Invalid;
    public long LatencySum;
    public long Errors;
    public readonly Dictionary<string, ServiceStats> Services = new(StringComparer.Ordinal);
}

/// <summary>A cursor over either split-created tokens or scanned source spans.</summary>
internal ref struct TokenCursor
{
    private readonly string[]? _splitTokens;
    private readonly ReadOnlySpan<char> _line;
    private int _index;

    public TokenCursor(string[] splitTokens)
    {
        _splitTokens = splitTokens;
        _line = default;
        _index = 0;
    }

    public TokenCursor(ReadOnlySpan<char> line)
    {
        _splitTokens = null;
        _line = line;
        _index = 0;
    }

    public bool TryNext(out ReadOnlySpan<char> token)
    {
        if (_splitTokens is not null)
        {
            while (_index < _splitTokens.Length)
            {
                string part = _splitTokens[_index++];
                if (part.Length == 0) continue;
                token = part.AsSpan();
                return true;
            }
            token = default;
            return false;
        }

        while (_index < _line.Length && IsDelimiter(_line[_index])) _index++;
        if (_index == _line.Length)
        {
            token = default;
            return false;
        }
        int start = _index;
        while (_index < _line.Length && !IsDelimiter(_line[_index])) _index++;
        token = _line[start.._index];
        return true;
    }

    private static bool IsDelimiter(char c) => c is ' ' or '\t';
}

internal static class Program
{
    private static bool IsDigit(char c) => c is >= '0' and <= '9';
    private static bool IsDelimiter(char c) => c is ' ' or '\t';

    private static bool IsIdentifier(ReadOnlySpan<char> token, int maxLength)
    {
        if (token.Length is < 1 || token.Length > maxLength) return false;
        foreach (char c in token)
        {
            if (!((c is >= 'a' and <= 'z') || (c is >= 'A' and <= 'Z') || IsDigit(c) || c is '_' or '-'))
                return false;
        }
        return true;
    }

    private static bool IsTimestampShape(ReadOnlySpan<char> token)
    {
        if (token.Length != 20) return false;
        for (int i = 0; i < 20; i++)
        {
            char c = token[i];
            char expected = i switch
            {
                4 or 7 => '-',
                10 => 'T',
                13 or 16 => ':',
                19 => 'Z',
                _ => '\0'
            };
            if (expected != '\0')
            {
                if (c != expected) return false;
            }
            else if (!IsDigit(c)) return false;
        }
        return true;
    }

    private static bool ParseLine(ReadOnlySpan<char> line, bool split, ParseResult result)
    {
        // The entire physical line must be ASCII, including ignored key/value fields.
        foreach (char c in line) if (c > 0x7f) return false;

        TokenCursor cursor = split
            ? new TokenCursor(line.ToString().Split([' ', '\t'], StringSplitOptions.RemoveEmptyEntries))
            : new TokenCursor(line);
        if (!cursor.TryNext(out ReadOnlySpan<char> token) || !IsTimestampShape(token)) return false;
        if (!cursor.TryNext(out token) || !IsIdentifier(token, 32)) return false;
        string service = token.ToString();
        if (!cursor.TryNext(out token)) return false;
        bool isError;
        if (token.SequenceEqual("DEBUG") || token.SequenceEqual("INFO") || token.SequenceEqual("WARN")) isError = false;
        else if (token.SequenceEqual("ERROR")) isError = true;
        else return false;
        if (!cursor.TryNext(out token) || !IsIdentifier(token, 48)) return false;

        bool haveLatency = false;
        long latency = 0;
        while (cursor.TryNext(out token))
        {
            int equals = -1;
            for (int i = 0; i < token.Length; i++)
            {
                if (token[i] != '=') continue;
                if (equals >= 0) return false;
                equals = i;
            }
            if (equals <= 0 || equals == token.Length - 1) return false;
            ReadOnlySpan<char> key = token[..equals];
            if (key.SequenceEqual("latency_ms"))
            {
                if (haveLatency) return false;
                ReadOnlySpan<char> value = token[(equals + 1)..];
                if (value.Length is < 1 or > 7) return false;
                long parsed = 0;
                foreach (char c in value)
                {
                    if (!IsDigit(c)) return false;
                    parsed = parsed * 10 + (c - '0');
                }
                if (parsed > 1_000_000) return false;
                latency = parsed;
                haveLatency = true;
            }
        }
        if (!haveLatency) return false;

        result.Valid++;
        result.LatencySum += latency;
        if (isError) result.Errors++;
        if (!result.Services.TryGetValue(service, out ServiceStats? stats))
        {
            stats = new ServiceStats();
            result.Services.Add(service, stats);
        }
        stats.Count++;
        stats.LatencySum += latency;
        if (isError) stats.Errors++;
        return true;
    }

    private static ParseResult ParsePass(string input, bool split)
    {
        var result = new ParseResult();
        ReadOnlySpan<char> corpus = input.AsSpan();
        int lineStart = 0;
        while (lineStart < corpus.Length)
        {
            int relativeLf = corpus[lineStart..].IndexOf('\n');
            bool hasLf = relativeLf >= 0;
            int lineEnd = hasLf ? lineStart + relativeLf : corpus.Length;
            int contentEnd = lineEnd;
            if (hasLf && contentEnd > lineStart && corpus[contentEnd - 1] == '\r') contentEnd--;
            result.Lines++;
            if (!ParseLine(corpus[lineStart..contentEnd], split, result)) result.Invalid++;
            if (!hasLf) break;
            lineStart = lineEnd + 1;
        }
        return result;
    }

    private static string ToJson(ParseResult result, int pass, long elapsedNs)
    {
        var output = new StringBuilder(256 + result.Services.Count * 80);
        output.Append("{\"pass\":").Append(pass.ToString(CultureInfo.InvariantCulture))
            .Append(",\"elapsed_ns\":").Append(elapsedNs.ToString(CultureInfo.InvariantCulture))
            .Append(",\"result\":{\"lines\":").Append(result.Lines.ToString(CultureInfo.InvariantCulture))
            .Append(",\"valid\":").Append(result.Valid.ToString(CultureInfo.InvariantCulture))
            .Append(",\"invalid\":").Append(result.Invalid.ToString(CultureInfo.InvariantCulture))
            .Append(",\"latency_sum\":").Append(result.LatencySum.ToString(CultureInfo.InvariantCulture))
            .Append(",\"errors\":").Append(result.Errors.ToString(CultureInfo.InvariantCulture))
            .Append(",\"services\":{");
        bool first = true;
        foreach ((string service, ServiceStats stats) in result.Services)
        {
            if (!first) output.Append(',');
            first = false;
            output.Append('"').Append(service).Append("\":{\"count\":")
                .Append(stats.Count.ToString(CultureInfo.InvariantCulture))
                .Append(",\"errors\":").Append(stats.Errors.ToString(CultureInfo.InvariantCulture))
                .Append(",\"latency_sum\":").Append(stats.LatencySum.ToString(CultureInfo.InvariantCulture)).Append('}');
        }
        return output.Append("}}}").ToString();
    }

    public static void Main(string[] args)
    {
        if (args.Length != 4) throw new ArgumentException("usage: <program> <input-path> <split|scan> <warmup-count> <measured-count>");
        bool split = args[1] switch
        {
            "split" => true,
            "scan" => false,
            _ => throw new ArgumentException("variant must be split or scan")
        };
        int warmups = int.Parse(args[2], CultureInfo.InvariantCulture);
        int measured = int.Parse(args[3], CultureInfo.InvariantCulture);
        if (warmups < 0 || measured < 1) throw new ArgumentException("warmup-count must be >= 0 and measured-count >= 1");

        // Preserve a BOM as input data so the ASCII-only contract rejects it equally.
        string input = new UTF8Encoding(false, true).GetString(File.ReadAllBytes(args[0]));
        for (int i = 0; i < warmups; i++) GC.KeepAlive(ParsePass(input, split));
        for (int pass = 0; pass < measured; pass++)
        {
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            ParseResult result = ParsePass(input, split);
            long elapsedNs = (long)(System.Diagnostics.Stopwatch.GetElapsedTime(start).Ticks * (1_000_000_000.0 / TimeSpan.TicksPerSecond));
            Console.WriteLine(ToJson(result, pass, elapsedNs));
            Console.Out.Flush();
        }
    }
}
