#!/usr/bin/env python3
"""Reconcile the latest pilot with immutable raw output and source snapshots."""
import json
import argparse
import math
from pathlib import Path
import statistics
from experiment import ART, DATA, OUT, ROOT, LANGS, sha, save, valid_rows

def validate(recorded=False):
    results = json.loads((ART/'benchmark-results.json').read_text())
    ledger = json.loads((ART/'run-ledger.json').read_text())
    replay = json.loads((ART/'replay-manifest.json').read_text())
    assert results['status'] == 'measured_native_pilot'
    group = results['run_group']
    assert ledger['run_group'] == replay['run_group'] == group
    raw = ART/'raw'/group
    environment = json.loads((raw/'environment.json').read_text())
    assert sha(raw/'environment.json') == results['metadata_sha256']
    for relative, digest in environment['sources_sha256'].items():
        assert sha(raw/'source'/relative) == digest, relative
    if not recorded:
        for relative, digest in environment['binaries_sha256'].items():
            assert sha(ROOT/relative) == digest, relative
    for relative, digest in replay['raw_sha256'].items():
        assert sha(OUT/relative) == digest, relative
    datasets = json.loads((raw/'datasets.json').read_text())
    assert sha(raw/'datasets.json') == environment['dataset_manifest_sha256']
    tests = json.loads((raw/'test-results.json').read_text())
    builds = json.loads((raw/'build-results.json').read_text())
    assert tests['passed'] and len(tests['tests']) == 64
    assert len(builds['targets']) == 4 and all(t['exit_code'] == 0 for t in builds['targets'])
    runs = ledger['runs']
    assert len(runs) == 80
    run_ids = set()
    for run in runs:
        assert run['run_id'] not in run_ids
        run_ids.add(run['run_id'])
        assert run['correctness'] and run['exit_code'] == 0 and run['run_group'] == group
        folder = OUT/run['source']
        stored = json.loads((folder/'manifest.json').read_text())
        assert stored == run
        rows = [json.loads(line) for line in (folder/'stdout.jsonl').read_text().splitlines()]
        expected = datasets['corpora'][run['corpus']+'.log']['expected']
        assert valid_rows(rows, expected, 3)
        assert run['corpus_sha256'] == datasets['corpora'][run['corpus']+'.log']['sha256']
        if not recorded:
            assert sha(DATA/(run['corpus']+'.log')) == run['corpus_sha256']
        assert rows == run['rows']
        assert statistics.median(r['elapsed_ns'] for r in rows) == run['median_elapsed_ns']
        assert run['peak_rss_bytes'] is not None and run['peak_rss_bytes'] > 0
    assert len(results['aggregates']) == 16
    for corpus in ('clean','noisy'):
        for lang in LANGS:
            for variant in ('split','scan'):
                selected = [r for r in runs if (r['corpus'],r['target'],r['variant']) == (corpus,lang,variant)]
                assert len(selected) == 5 and {r['trial'] for r in selected} == {1,2,3,4,5}
                lines = datasets['corpora'][corpus+'.log']['expected']['lines']
                values = [lines*1e9/r['median_elapsed_ns'] for r in selected]
                aggregate = next(a for a in results['aggregates'] if (a['corpus'],a['target'],a['variant']) == (corpus,lang,variant))
                assert aggregate['trial_values'] == values
                assert math.isclose(aggregate['median'], statistics.median(values), rel_tol=1e-12)
                assert aggregate['run_ids'] == [r['run_id'] for r in selected]
    gates = dict(run_group=group, local_pilot_integrity_passed=True,
                 evidence_ready_for_scoped_local_pilot_story=True, production_verdict_valid=False,
                 full_replay_contract_passed=False,
                 full_replay_contract_note='Generic experiment-runner validator fails: this batch pilot lacks canonical replay streams, live-preview datasets, top-level environment/actions receipt and a final verdict. The local validator verifies the narrower raw batch evidence only.',
                 contract_tests=64, fresh_process_trials=80, timed_passes=240,
                 raw_hashes_verified=len(replay['raw_sha256']), publication_ready=False,
                 limitations=['native host without hard resource isolation or thermal monitoring',
                              'shape-only timestamp validation, scoped aggregation kernel',
                              'no cross-runtime allocation profiles or demonstrated JIT convergence',
                              'not a reproduction of the original app or its demonstration figures'],
                 prior_attempts=[dict(run_group=p.name, disposition='retained, excluded from latest pilot')
                                 for p in (ART/'raw').iterdir() if p.is_dir() and p.name != group])
    if recorded:
        print(json.dumps(dict(recorded_evidence_integrity_passed=True, run_group=group,
            contract_tests=64, fresh_process_trials=80, timed_passes=240,
            raw_hashes_verified=len(replay['raw_sha256']),
            note='Historical evidence verified. Local binaries and regenerated corpus bytes are not checked in --recorded mode.'), indent=2))
    else:
        save(ART/'quality-gates.json', gates)
        print(json.dumps(gates, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recorded', action='store_true', help='Verify published evidence without requiring the original machine binaries or corpora; does not modify the recorded quality gate.')
    validate(parser.parse_args().recorded)
