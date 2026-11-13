# Log parser rematch contract v1

This is a NEW scoped workload, not a reproduction of the old app or validation of its sample numbers.
Four language implementations, two variants each: `split` (materialize whitespace tokens) and `scan` (iterate token slices/spans without materializing the whole token list). Same aggregation and validation. No third-party packages required.

CLI: `<program> <input-path> <split|scan> <warmup-count> <measured-count>`.
Read UTF-8 file once before warmup; corpus fits memory. Process each pass from the same resident input. Single-thread application parsing (runtime background threads allowed). Warmup and measured passes in SAME process. Fresh aggregation per pass. Use monotonic timer around each full parse + aggregate pass; exclude input load and JSON output. Emit ONE JSON object per measured pass to stdout, flush each line:
`{"pass":0,"elapsed_ns":123,"result":{"lines":1,"valid":1,"invalid":0,"latency_sum":42,"errors":0,"services":{"api":{"count":1,"errors":0,"latency_sum":42}}}}`
JSON key ordering irrelevant; all integers, no floating point. `pass` zero-based measured index. Keep a reference to result through output to prevent dead-code elimination. Invalid lines increment lines/invalid and never affect any other field.

Input grammar, deliberately narrower than original app:
- Nonempty ASCII lines separated by LF, optional CR before LF; last line may lack LF. Empty file = zero lines; empty interior line = invalid line. No phantom extra line for trailing LF.
- ASCII space and tab delimit tokens; multiple/leading/trailing delimiters allowed.
- Header: timestamp, service, level, event (at least 4 tokens), then arbitrary key=value tokens.
- Timestamp: exactly `YYYY-MM-DDTHH:MM:SSZ` 20 bytes; separators fixed; all other positions ASCII digits. This version checks SHAPE ONLY, not calendar validity; equal reduced work in both variants/all lanes.
- service: 1–32 chars from ASCII a-z A-Z 0-9 underscore hyphen.
- level: DEBUG, INFO, WARN, ERROR exactly.
- event: 1–48 chars from ASCII a-z A-Z 0-9 underscore hyphen.
- Every remaining token must contain exactly one `=` with nonempty key and value. Unknown keys accepted, no further validation. Known key `latency_ms` must occur exactly once; value 1–7 ASCII digits, integer 0..1000000 inclusive. Duplicate or missing latency invalid. Other keys may repeat. `status` is an ignored field, not an error detector.
- A non-ASCII character anywhere invalidates the whole line (UTF-8 data may be decoded but the line must be rejected).
- Error = valid line with level ERROR; no other error inference.
- Output counts every physical line; sums and per-service aggregation of all valid records. Service map includes only services with valid records. All counters 64-bit.

`split` and `scan` must differ only in tokenization mechanism. Both scan physical lines without splitting the entire corpus into line arrays. `split` may use standard-library split APIs or collect a token iterator to an array/vector; `scan` iterates token boundaries without constructing a per-line token array. Both may create service strings for map lookup. No manual special-casing corpus literals or precomputed outputs. No SIMD/parallel parsing, timestamp skipping, or different validation.

Memory metric is process lifetime peak RSS, including resident corpus, runtime and warmups; not parser allocation or container requirement. Externally timed process duration includes input loading, warmup, parse passes and output; not cold start to readiness. Throughput is resident-input parse+aggregation, not disk/streaming throughput. No p99 request latency or cost extrapolation.

Implementations live in implementations/{go,rust,java,csharp}. Offline builds: Go standard library; rustc -O standalone Rust file; javac with Java standard library; .NET SDK console project no NuGet deps. Do not add results or claims in implementation files.
