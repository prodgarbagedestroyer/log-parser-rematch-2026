import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Pattern;

/** Contract-v1 log parser rematch. No third-party dependencies. */
public final class Main {
    private static volatile Result warmupSink;
    private static final Pattern SPLIT_DELIMITER = Pattern.compile("[ \\t]+");

    private static final class ServiceStats {
        long count;
        long errors;
        long latencySum;
    }

    private static final class Result {
        long lines;
        long valid;
        long invalid;
        long latencySum;
        long errors;
        final Map<String, ServiceStats> services = new HashMap<>();
    }

    private static final class Token {
        String source;
        int start;
        int end;

        int length() { return end - start; }
        char at(int index) { return source.charAt(start + index); }
        String text() { return source.substring(start, end); }
        boolean regionEquals(int tokenOffset, int regionLength, String value) {
            if (regionLength != value.length()) return false;
            for (int i = 0; i < value.length(); i++) if (at(tokenOffset + i) != value.charAt(i)) return false;
            return true;
        }
        boolean equalsAscii(String value) {
            if (length() != value.length()) return false;
            for (int i = 0; i < length(); i++) if (at(i) != value.charAt(i)) return false;
            return true;
        }
    }

    private interface TokenCursor {
        boolean next(Token token);
    }

    /** split variant: standard regex split materializes the token array. */
    private static final class SplitCursor implements TokenCursor {
        private final String[] tokens;
        private int index;
        SplitCursor(String line) { tokens = SPLIT_DELIMITER.split(line); }
        public boolean next(Token token) {
            while (index < tokens.length) {
                String part = tokens[index++];
                if (!part.isEmpty()) {
                    token.source = part;
                    token.start = 0;
                    token.end = part.length();
                    return true;
                }
            }
            return false;
        }
    }

    /** scan variant: yields token slices directly from the current line. */
    private static final class ScanCursor implements TokenCursor {
        private final String line;
        private int index;
        ScanCursor(String line) { this.line = line; }
        public boolean next(Token token) {
            while (index < line.length() && delimiter(line.charAt(index))) index++;
            if (index == line.length()) return false;
            int start = index;
            while (index < line.length() && !delimiter(line.charAt(index))) index++;
            token.source = line;
            token.start = start;
            token.end = index;
            return true;
        }
    }

    private static boolean delimiter(char c) { return c == ' ' || c == '\t'; }
    private static boolean digit(char c) { return c >= '0' && c <= '9'; }

    private static boolean identifier(Token token, int maxLength) {
        if (token.length() < 1 || token.length() > maxLength) return false;
        for (int i = 0; i < token.length(); i++) {
            char c = token.at(i);
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    digit(c) || c == '_' || c == '-')) return false;
        }
        return true;
    }

    private static boolean timestampShape(Token token) {
        if (token.length() != 20) return false;
        for (int i = 0; i < 20; i++) {
            char c = token.at(i);
            boolean separator = i == 4 || i == 7 || i == 10 || i == 13 || i == 16;
            if (separator) {
                char expected = switch (i) {
                    case 4, 7 -> '-';
                    case 10 -> 'T';
                    case 13, 16 -> ':';
                    default -> 0;
                };
                if (c != expected) return false;
            } else if (i == 19) {
                if (c != 'Z') return false;
            } else if (!digit(c)) return false;
        }
        return true;
    }

    private static boolean parseLine(String line, boolean split, Result result) {
        // Any non-ASCII character invalidates the entire physical line.
        for (int i = 0; i < line.length(); i++) if (line.charAt(i) > 0x7f) return false;

        TokenCursor cursor = split ? new SplitCursor(line) : new ScanCursor(line);
        Token token = new Token();
        if (!cursor.next(token) || !timestampShape(token)) return false;
        if (!cursor.next(token) || !identifier(token, 32)) return false;
        String service = token.text();
        if (!cursor.next(token)) return false;
        boolean isError;
        if (token.equalsAscii("DEBUG") || token.equalsAscii("INFO") || token.equalsAscii("WARN")) {
            isError = false;
        } else if (token.equalsAscii("ERROR")) {
            isError = true;
        } else return false;
        if (!cursor.next(token) || !identifier(token, 48)) return false;

        boolean haveLatency = false;
        long latency = 0;
        while (cursor.next(token)) {
            int equals = -1;
            for (int i = 0; i < token.length(); i++) {
                if (token.at(i) == '=') {
                    if (equals >= 0) return false;
                    equals = i;
                }
            }
            if (equals <= 0 || equals == token.length() - 1) return false;
            boolean latencyKey = equals == 10 && token.regionEquals(0, equals, "latency_ms");
            if (latencyKey) {
                if (haveLatency) return false;
                int digits = token.length() - equals - 1;
                if (digits < 1 || digits > 7) return false;
                long parsed = 0;
                for (int i = equals + 1; i < token.length(); i++) {
                    char c = token.at(i);
                    if (!digit(c)) return false;
                    parsed = parsed * 10 + (c - '0');
                }
                if (parsed > 1_000_000) return false;
                latency = parsed;
                haveLatency = true;
            }
        }
        if (!haveLatency) return false;

        result.valid++;
        result.latencySum += latency;
        if (isError) result.errors++;
        ServiceStats stats = result.services.computeIfAbsent(service, ignored -> new ServiceStats());
        stats.count++;
        stats.latencySum += latency;
        if (isError) stats.errors++;
        return true;
    }

    private static Result parsePass(String input, boolean split) {
        Result result = new Result();
        int length = input.length();
        int lineStart = 0;
        while (lineStart < length) {
            int lineEnd = input.indexOf('\n', lineStart);
            boolean hasLf = lineEnd >= 0;
            if (!hasLf) lineEnd = length;
            int contentEnd = lineEnd;
            if (hasLf && contentEnd > lineStart && input.charAt(contentEnd - 1) == '\r') contentEnd--;
            result.lines++;
            String line = input.substring(lineStart, contentEnd);
            if (!parseLine(line, split, result)) result.invalid++;
            if (!hasLf) break;
            lineStart = lineEnd + 1;
        }
        return result;
    }

    private static String json(Result r, int pass, long elapsedNs) {
        StringBuilder out = new StringBuilder(256 + r.services.size() * 80);
        out.append("{\"pass\":").append(pass).append(",\"elapsed_ns\":").append(elapsedNs)
           .append(",\"result\":{\"lines\":").append(r.lines)
           .append(",\"valid\":").append(r.valid).append(",\"invalid\":").append(r.invalid)
           .append(",\"latency_sum\":").append(r.latencySum).append(",\"errors\":").append(r.errors)
           .append(",\"services\":{");
        boolean first = true;
        for (Map.Entry<String, ServiceStats> entry : r.services.entrySet()) {
            if (!first) out.append(',');
            first = false;
            ServiceStats s = entry.getValue();
            out.append('"').append(entry.getKey()).append("\":{\"count\":").append(s.count)
               .append(",\"errors\":").append(s.errors).append(",\"latency_sum\":").append(s.latencySum).append('}');
        }
        return out.append("}}}").toString();
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 4) throw new IllegalArgumentException("usage: java Main <input-path> <split|scan> <warmup-count> <measured-count>");
        boolean split = switch (args[1]) {
            case "split" -> true;
            case "scan" -> false;
            default -> throw new IllegalArgumentException("variant must be split or scan");
        };
        int warmups = Integer.parseInt(args[2]);
        int measured = Integer.parseInt(args[3]);
        if (warmups < 0 || measured < 1) throw new IllegalArgumentException("warmup-count must be >= 0 and measured-count >= 1");
        String input = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);
        for (int i = 0; i < warmups; i++) warmupSink = parsePass(input, split);
        for (int pass = 0; pass < measured; pass++) {
            long start = System.nanoTime();
            Result result = parsePass(input, split);
            long elapsed = System.nanoTime() - start;
            // The measured result is consumed and kept live through serialization.
            System.out.println(json(result, pass, elapsed));
            System.out.flush();
        }
    }
}
