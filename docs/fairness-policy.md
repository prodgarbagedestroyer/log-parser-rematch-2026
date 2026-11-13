# Rematch fairness policy

This policy operationalizes [`../CONTRACT.md`](../CONTRACT.md). It defines a local macOS pilot; it does not claim platform neutrality or production representativeness.

## Scope and variants

- Four languages, two variants each: `split` materializes per-line tokens; `scan` walks token spans without building a per-line token array.
- Both variants perform identical shape validation, required `latency_ms` checks, error classification, and service aggregation. Only tokenization may differ.
- Input is generated deterministically in clean and noisy forms. Record generator revision, seed, parameters, file size, line count, and SHA-256 for each corpus.
- Read UTF-8 input once before warmup. Each pass processes the same resident bytes on one application parsing thread. Timer covers full parse plus aggregation; it excludes input load and JSON output.
- Keep the contract's line grammar, counters, CLI, output schema, overflow behavior, and invalid-line rules identical across languages. No external packages, corpus-specific shortcuts, skipped validation, SIMD, or parallel parsing.

## Correctness gate

Do not time a variant until it matches the language-neutral reference on the same fixtures and corpora. Verify every pass's result object, including physical lines, valid/invalid totals, latency sum, error count, and per-service counts/errors/sums. Include empty input, empty interior lines, optional CRLF, no final LF, multiple delimiters, invalid ASCII/non-ASCII, timestamp shape boundaries, duplicate/missing latency, and malformed key/value tokens. A mismatch blocks that implementation from speed comparison until resolved.

## Pilot procedure

1. Build optimized artifacts using the contract's offline toolchains. Record exact commands, versions, flags, OS, hardware, power mode, and available background-load conditions.
2. Verify the Podman VM is unavailable for this pilot; run natively on the same macOS host for every implementation. Label all captures **local macOS pilot**.
3. For each language/variant/corpus cell, launch five fresh processes in balanced, rotated order. In each process, perform five untimed warmup passes followed by three timed passes, as specified by the contract. Preserve every measured JSON line and process exit status.
4. Keep the machine idle and conditions consistent; record interruptions or thermal/power changes. If a run is interrupted or correctness fails, retain the record and repeat the whole affected cell under the same rule, documenting why.
5. Compare `split` with `scan` within each language first. Only after those paired interventions are valid, show cross-language results as diagnostics under these exact builds and this workload.

## Reporting and claim limits

- Report per-pass observations and robust summaries across the five process launches; show spread, not just a pooled headline. Treat the three passes within one process as repeated observations, not three independent machines or runs.
- Use the same verified corpus bytes for every cell. Throughput is resident-input parse-plus-aggregation throughput, not disk, streaming, or end-to-end service throughput.
- Process-lifetime peak RSS is diagnostic only: it includes runtime, resident input, and warmups. It is not parser allocation, a container-sizing recommendation, or an apples-to-apples per-record memory measure.
- Do not claim cold-start-to-readiness, request latency or p99, cloud cost, production behavior, general language superiority, or results on other operating systems/hardware.
- Attribute mechanisms only to inspected code or collected profiles. Keep measured observations, causal interpretation, and untested hypotheses distinct.
- Publish no performance values, rank, or winner until raw output, correctness, build metadata, and run protocol have been reviewed. If the pilot has noisy or overlapping results, say the evidence is inconclusive at this scope.
