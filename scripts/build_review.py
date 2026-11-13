#!/usr/bin/env python3
"""Generate review text and chart data from the validated pilot, never demo values."""
import json
import re
from pathlib import Path
from experiment import ART, OUT, ROOT, save

REVIEW = ROOT/'review'
results = json.loads((ART/'benchmark-results.json').read_text())
quality = json.loads((ART/'quality-gates.json').read_text())
assert quality['local_pilot_integrity_passed'] and results['run_group'] == quality['run_group']
cells = {(a['corpus'],a['target'],a['variant']):a for a in results['aggregates']}
claims = {}
for corpus in ('clean','noisy'):
    for lang in ('rust','go','java','csharp'):
        split, scan = [cells[corpus,lang,v] for v in ('split','scan')]
        ratio = scan['median']/split['median']
        claims[f'{corpus}-{lang}'] = dict(split=split['median'], scan=scan['median'], ratio=ratio,
            throughput_change_pct=(ratio-1)*100, evidence_ids=[split['evidence_id'],scan['evidence_id']],
            formula='scan median lines/s / split median lines/s; percent=(ratio-1)*100')
save(ART/'review-claims.json',dict(run_group=results['run_group'], claims=claims))
j,r,g,c = [claims['clean-'+x] for x in ('java','rust','go','csharp')]
profile_dir = ART/'profile-go'
profile_text = (profile_dir/'benchmark-output.txt').read_text()
profile_rows = {}
for name,ns,allocated,allocations in re.findall(r'Benchmark(Split|Scan)-\d+\s+\d+\s+(\d+) ns/op\s+(\d+) B/op\s+(\d+) allocs/op',profile_text):
    profile_rows[name.lower()] = dict(ns_per_pass=int(ns), bytes_per_pass=int(allocated), allocations_per_pass=int(allocations))
assert set(profile_rows) == {'split','scan'}
save(profile_dir/'diagnostic.json',dict(status='single_separate_diagnostic', rows=profile_rows,
    source='benchmark-output.txt', unit_note='B/op means cumulative allocated bytes per full corpus pass, not resident memory',
    corpus='clean', source_sha256=(profile_dir/'source-hash.txt').read_text().split(': ')[1].splitlines()[0]))
script = f'''# Narration draft — review before audio

Working concept: Can a parser change save you a language rewrite?
Format: vertical Short, target 2–3 minutes. Timing remains provisional until approved narration is generated.
Evidence: local Apple M4/macOS pilot `{results['run_group']}`. Throughput values derive from verified raw passes; Go allocation observations come from a separate diagnostic run.

## Spoken narration

This Java parser processed {j['ratio']:.2f} times as many log lines after this change. This Go parser processed about {abs(g['throughput_change_pct']):.0f} percent fewer. The idea? Stop building a token array for every line.

First, a correction. The old project's chart script wrote demonstration numbers. Those aren't measured evidence. So I rebuilt a smaller, testable workload. This is a new experiment, not confirmation of the old leaderboard.

Each parser checks the same line format, requires a valid latency value, counts errors, and aggregates totals by service. Every output has to match an independent reference. Wrong answers don't qualify as fast.

The baseline materializes the tokens. The alternative walks through them as needed. Both keep the same validation and aggregation within each language. Java's whitespace-split pattern is compiled once. This tests tokenization, not Java Streams; that needs a separate controlled comparison.

On the clean input, that Java change moved throughput from {j['split']/1e6:.2f} million to {j['scan']/1e6:.2f} million lines per second. That's more than double the work per second, without changing languages.

Rust improved too: about {r['ratio']:.2f} times the throughput. C sharp gained about {c['throughput_change_pct']:.0f} percent. But Go went the other way. Its token cursor processed fewer lines per second than its materialized-token version.

In a separate Go allocation diagnostic, the cursor allocated far fewer bytes per pass and still took longer. Less allocation didn't automatically buy more throughput here. That's allocated bytes over a full pass, not resident memory.

That's the catch. These languages don't have identical split implementations. Java uses a precompiled regex. C sharp splits strings. Rust and Go collect token slices. Replacing that work with a cursor is a hypothesis, not a guaranteed optimization. These timings don't isolate which internal cost caused the difference.

The direction held on noisy input too. Every measured output still matched the reference. The faster versions weren't winning by silently accepting malformed records.

This was a local Mac test, with the input already in memory. Five fresh processes per case, warmup passes, then timed passes. It checks timestamp shape, not calendar validity. It doesn't measure disk throughput, a production pipeline, or a cloud bill.

My decision: test the hot path before paying for a rewrite. Keep the cursor where your own measurements show a useful gain. For this Go implementation, the array wins throughput; the cursor cuts allocations. Choose your constraint, then measure it.

Next test: does that decision survive when the logs arrive over a real stream?

## Review notes — not spoken

- Numbers are medians across five process-level medians; each process contributes three timed passes after five warmups.
- The four languages are contextual diagnostics, not an equal-optimization championship. Source representations and tokenizers differ.
- No allocation-causality, cold-start, memory-sizing or price claim is made. The Go allocation diagnostic is a single separate Go benchmark run, not an additional scored trial.
- The legacy correction is deliberate: old narration matches hardcoded demonstration fixtures; no historical measured speedup is claimed.
- This is a draft for approval. No final audio, VideoData, subtitles or metadata are created yet.
'''
REVIEW.mkdir(parents=True,exist_ok=True)
(REVIEW/'script.md').write_text(script)
spoken = script.split('## Spoken narration\n\n')[1].split('\n## Review notes')[0]
words = len(spoken.split())
table = ['| Implementation | Split, million lines/s | Scan, million lines/s | Scan/split |',
         '|---|---:|---:|---:|']
for lang,label in [('rust','Rust'),('go','Go'),('java','Java'),('csharp','C#')]:
    x=claims['clean-'+lang]
    table.append(f"| {label} | {x['split']/1e6:.2f} | {x['scan']/1e6:.2f} | {x['ratio']:.2f}× |")
summary = f'''# Local pilot — evidence summary

Run: `{results['run_group']}`. Integrity checks: {quality['contract_tests']} contract cases, {quality['fresh_process_trials']} fresh processes, {quality['timed_passes']} timed passes, {quality['raw_hashes_verified']} raw-file hashes verified.

Clean corpus: 200,000 physical lines. Resident-input parsing and service aggregation only.

{chr(10).join(table)}

The noisy corpus preserves the direction for every language. These ratios compare variants within each language; they are not historical speedups or universal language rankings. Full min/max and individual trials are in `artifacts/benchmark-results.json`.

The first attempt was retained and excluded: macOS `/usr/bin/time -l` exited 1 because the sandbox denied `sysctl kern.clockrate`, despite valid parser output. The complete subsequent group ran with process-measurement access. No runs were deleted or replaced within the scored group.

Raw source snapshots, compiler/runtime versions, corpus/binary/source hashes, stdout and stderr are retained in `artifacts/raw/`. Native macOS has no hard CPU/memory isolation or thermal monitoring, and five warmups do not prove JIT convergence. No production or cloud verdict is publication-ready.

The dedicated batch-pilot integrity validator passes. The generic experiment-runner replay validator does not pass: canonical live/replay datasets and raw event/terminal streams, top-level environment/action receipts and a final verdict are absent. This is a scoped batch evidence package and script draft, not a completed replay-grade production experiment or a final video.

Narration draft: {words} words, approximately {words/155*60:.0f}–{words/140*60:.0f} seconds at 155–140 words/minute. Actual duration and scene sync follow approved audio.
'''
(ART/'summary.md').write_text(summary)
(REVIEW/'evidence-summary.md').write_text(summary)
charts = []
for corpus in ('clean','noisy'):
    for lang in ('rust','go','java','csharp'):
        charts.append(dict(key=f'{corpus}-{lang}', type='paired-bars',
            title=f'{lang} — {corpus}', unit='lines/s', measurement_kind='derived',
            source_run_group=results['run_group'],
            series=[dict(variant=v,value=cells[corpus,lang,v]['median'],
                         min=cells[corpus,lang,v]['min'], max=cells[corpus,lang,v]['max'],
                         evidence_id=cells[corpus,lang,v]['evidence_id']) for v in ('split','scan')]))
save(ART/'charts-data.json', dict(charts=charts))
index = json.loads((ART/'evidence-index.json').read_text())
index['evidence'] = [e for e in index['evidence'] if e['id'] != 'go-clean-allocation-diagnostic']
index['evidence'].append(dict(id='go-clean-allocation-diagnostic', measurement_kind='diagnostic',
    source_file='artifacts/profile-go/benchmark-output.txt', unit='B per full corpus pass; ns per full corpus pass',
    confidence='single separate benchmark run; no causal attribution'))
save(ART/'evidence-index.json',index)
save(ART/'evidence-map.json',dict(run_group=results['run_group'],
    scenes={**{f'paired-bars-{k}':v['evidence_ids'] for k,v in claims.items()},
            'go-allocation-diagnostic':['go-clean-allocation-diagnostic']},
    note='Editorial plan only. Actual VideoData display keys follow approved audio/composition.'))
raw_group = ART/'raw'/results['run_group']
save(OUT/'benchmark-report.json',dict(schema_version='1.0',
    meta=dict(scenario_id='resident-parser-tokenization',run_group=results['run_group']),
    environment=json.loads((raw_group/'environment.json').read_text()),
    methodology=dict(spec='../../spec.yaml',contract='../../CONTRACT.md',warmup_passes=5,
                     measured_passes_per_process=3,fresh_process_trials=5,primary_scope='within-language'),
    raw_runs=json.loads((ART/'run-ledger.json').read_text())['runs'],
    aggregates=results['aggregates'],resources=dict(peak_rss='process lifetime diagnostic in raw manifests'),
    resource_samples=None,cost_model=None,derived=claims,
    quality_flags=quality,
    scene_recommendations=dict(order=['outcome','legacy correction','correctness','intervention','paired results','Go diagnostic','scope','verdict'],
        required_categories=['comparison','distribution','tradeoff','context'],
        confidence_by_metric=dict(local_throughput='moderate: five fresh processes, native host',
                                  allocation='diagnostic only: one separate Go benchmark',production=None))))
save(profile_dir/'manifest.json',dict(measurement_kind='diagnostic',
    files_sha256={p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in profile_dir.iterdir() if p.is_file() and p.name != 'manifest.json'}))
print(json.dumps(dict(review=str(REVIEW), words=words, seconds_at_150_wpm=words/150*60)))
