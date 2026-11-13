# Original benchmark audit

## Finding

The published numbers are demonstration fixtures, not traceable measurements of the log processor. Do not repeat them as benchmark results or use them to rank languages. The rematch is a new, narrower workload defined by [`../CONTRACT.md`](../CONTRACT.md), not a reproduction or validation of the old app.

## Evidence and provenance

- `projects/log-processor-benchmark-main/scripts/run-benchmark.sh:15-18` invokes the dataset generator. At `:20-63` it writes hard-coded sample metrics directly into `results/sample-results.json`; at `:67-73` it builds the charts from that file. The script therefore does not measure those displayed values.
- The same script labels the result-generation step “for demonstration” (`:20-23`). Although the fixture lists Rust, Go, Java, and C# (`:24-62`), that list is not evidence that four programs ran.
- `projects/log-processor-benchmark-main/scripts/generate_datasets.py:1-5, 14-37` describes social-app JSON datasets (users, posts, messages, events, conversations), not log lines. Its generation/output code is at `:378-405`.
- `projects/log-processor-benchmark-main/go/main.go:20-90, 1134-1263` defines social application models and HTTP routes/server. This is not a Go log-parser implementation.
- Java source does exist at `projects/log-processor-benchmark-main/java/src/main/java/com/logprocessor/Main.java`. It is an implementation of the old, broader app: `:195-249` compiles a shared regex pattern, parses timestamps and fields, and splits key/value text; the surrounding data models and aggregations describe the app's richer output. Its presence does not establish a comparable four-language run.
- No C# source is present in the old project tree. The C# row in the generated sample fixture is therefore not evidence of a C# implementation or run.
- The old narration's throughput, cold-start, and memory figures match the values written by the fixture script. Their provenance is the script, not a captured benchmark run.

## Scope for the rematch

Use only the contract's ASCII log-line shape-validation and per-service counter workload. Each language gets `split` and `scan` variants with the same validation and aggregation. This deliberately excludes the original app's full parsing semantics, API behavior, and output. State that scope in narration and graphics; don't frame the result as a general language contest.

## Before interpreting any future output

1. Confirm all eight implementations build and satisfy the same contract.
2. Run correctness fixtures first, including malformed, boundary, CRLF, and trailing-newline cases.
3. Preserve the exact generator seed/configuration, corpus hashes, source revision, build commands, runtime/compiler versions, and raw per-pass JSON.
4. Treat performance claims as pending until the planned pilot completes and the output is audited. No result or winner is asserted in this document.
