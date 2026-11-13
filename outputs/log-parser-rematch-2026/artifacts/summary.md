# Local pilot — evidence summary

Run: `20261113T025336Z-e268b819`. Integrity checks: 64 contract cases, 80 fresh processes, 240 timed passes, 254 raw-file hashes verified.

Clean corpus: 200,000 physical lines. Resident-input parsing and service aggregation only.

| Implementation | Split, million lines/s | Scan, million lines/s | Scan/split |
|---|---:|---:|---:|
| Rust | 6.00 | 9.25 | 1.54× |
| Go | 4.71 | 4.02 | 0.85× |
| Java | 3.14 | 7.97 | 2.54× |
| C# | 6.60 | 8.40 | 1.27× |

The noisy corpus preserves the direction for every language. These ratios compare variants within each language; they are not historical speedups or universal language rankings. Full min/max and individual trials are in `artifacts/benchmark-results.json`.

The first attempt was retained and excluded: macOS `/usr/bin/time -l` exited 1 because the sandbox denied `sysctl kern.clockrate`, despite valid parser output. The complete subsequent group ran with process-measurement access. No runs were deleted or replaced within the scored group.

Raw source snapshots, compiler/runtime versions, corpus/binary/source hashes, stdout and stderr are retained in `artifacts/raw/`. Native macOS has no hard CPU/memory isolation or thermal monitoring, and five warmups do not prove JIT convergence. No production or cloud verdict is publication-ready.

The dedicated batch-pilot integrity validator passes. The generic experiment-runner replay validator does not pass: canonical live/replay datasets and raw event/terminal streams, top-level environment/action receipts and a final verdict are absent. This is a scoped batch evidence package and script draft, not a completed replay-grade production experiment or a final video.

Narration draft: 401 words, approximately 155–172 seconds at 155–140 words/minute. Actual duration and scene sync follow approved audio.
