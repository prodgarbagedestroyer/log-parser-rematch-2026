# Log parser rematch

Does avoiding a token array improve a correct log parser? This repository contains a measured **local macOS pilot**, four implementations, a shared correctness contract, a deterministic corpus generator, and retained raw evidence.

Each language has a `split` variant that materializes per-line tokens and a `scan` variant that reads tokens as needed. Compare the intervention **within each language**: these implementations are not a universal language ranking or a reproduction of the earlier full application.

## Recorded results

Apple M4, macOS 27.2.1, arm64, 24 GiB RAM. Clean synthetic corpus: 200,000 physical lines, already resident in memory. Values are median throughput across five fresh processes; each trial uses the median of three timed passes after five warmup passes.

| Implementation | Split, million lines/s | Scan, million lines/s | Scan / split |
|---|---:|---:|---:|
| Rust | 6.00 | 9.25 | 1.54× |
| Go | 4.71 | 4.02 | 0.85× |
| Java | 3.14 | 7.97 | 2.54× |
| C# | 6.60 | 8.40 | 1.27× |

The noisy corpus shows the same direction for all four implementations. A **separate, single Go allocation diagnostic** found fewer allocated bytes per pass for the cursor, despite a longer elapsed time. Allocated bytes are not resident memory. See the [recorded summary](outputs/log-parser-rematch-2026/artifacts/summary.md), [individual trial results](outputs/log-parser-rematch-2026/artifacts/benchmark-results.json), and [Go diagnostic](outputs/log-parser-rematch-2026/artifacts/profile-go/diagnostic.json).

Java uses a precompiled whitespace-split regex; C# uses `string.Split`; Rust and Go collect token slices. Each variant shares validation and aggregation within its language. The intervention changes tokenization; timings alone do not establish why a change helped or hurt. Java Streams are not tested.

## Verify the published evidence

Requires Python 3.10+ only, with no third-party Python packages:

```bash
git clone https://github.com/prodgarbagedestroyer/log-parser-rematch-2026.git
cd log-parser-rematch-2026
python3 scripts/validate_pilot.py --recorded
```

This checks the raw-file hashes, source snapshots, recorded correctness outputs, 80 fresh-process trials / 240 timed passes, and derived medians. `--recorded` does not require the original binaries or dataset files, does not benchmark, and does not change the recorded quality gate. It verifies consistency of the published evidence, not performance on your machine.

## Reproduce on macOS

Requirements: Python 3.10+, Rust (`rustc`), Go, Homebrew OpenJDK at `/opt/homebrew/opt/openjdk/bin/`, and .NET SDK 10. The original versions are preserved in the [environment receipt](outputs/log-parser-rematch-2026/artifacts/raw/20261113T025336Z-e268b819/environment.json). No third-party runtime packages are used.

```bash
python3 scripts/experiment.py prepare
python3 scripts/experiment.py build
python3 scripts/experiment.py verify
python3 scripts/experiment.py measure
python3 scripts/validate_pilot.py
```

Run sequentially on an otherwise idle machine. The commands generate the dataset, build the four programs, compare both variants against a Python oracle, and measure the workloads. Verification covers eight fixtures/corpora for each of eight language/variant combinations: 64 checks, including 1,200 deterministic mutations. Generated `.log` files and compiled binaries/caches are not committed.

**Reproduction writes fresh manifests and summaries under `outputs/log-parser-rematch-2026/`.** Use a separate clone to preserve the published working copy. Previous timestamped raw groups remain retained. The generator's seed, corpus size, SHA-256 hashes and expected output are recorded. Original absolute machine paths remain unchanged inside historical receipts so their hashes remain verifiable.

The measurement command uses macOS `/usr/bin/time -l` for process-lifetime peak RSS; it needs normal host process-measurement permissions. The first sandbox-restricted attempt failed because `time` could not read `sysctl kern.clockrate`; its raw output is retained and excluded from the complete pilot group. Peak RSS includes the resident input, runtime and warmups and is diagnostic only.

## Workload and boundaries

Read the [shared contract](CONTRACT.md), [pre-run specification](spec.yaml), and [fairness policy](docs/fairness-policy.md).

- Timed passes cover resident-input parsing plus service-count, error-count and latency-sum aggregation. File loading and JSON serialization are outside the timer.
- Timestamps receive fixed ASCII **shape validation**, not calendar validation. This workload excludes the original app's percentile, route, anomaly and API functionality.
- One application parsing thread per process. Runtime background threads are allowed. There are no hard CPU/memory limits or thermal controls, and five warmups do not prove JIT convergence.
- No disk/streaming capacity, cold-start, request-tail-latency, container-sizing, cloud-cost or general language-superiority claim follows from these results.
- The dedicated batch evidence validator passes. The broader production/live-replay workflow remains incomplete, as explicitly recorded in [quality gates](outputs/log-parser-rematch-2026/artifacts/quality-gates.json). This is a public, scoped batch pilot, not a production benchmark verdict.

## Evidence layout

```text
implementations/                 Rust, Go, Java and C# sources
scripts/experiment.py            Generator, oracle, build/check/measurement harness
scripts/validate_pilot.py        Recorded-evidence and local-artifact validation
outputs/log-parser-rematch-2026/
  benchmark-report.json          Consolidated measured pilot report
  artifacts/
    benchmark-results.json       Per-trial throughput and aggregates
    datasets.json                Corpus hashes and expected results
    evidence-index.json          Derived-value source links
    raw/<run-group>/             Commands, stdout, stderr, source snapshots, receipts
    profile-go/                  Separate Go allocation diagnostic
```

The historical workspace revision is retained in the run metadata; it predates this standalone repository. The [original-project audit](docs/original-audit.md) explains why earlier demonstration values are not used as measured evidence. Video narration and final audiovisual production are separate from this repository publication.
