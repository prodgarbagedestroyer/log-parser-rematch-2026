#!/usr/bin/env python3
"""Offline contract checks and native pilot. Outputs raw evidence before summaries."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/log-parser-rematch-2026'
ART = OUT / 'artifacts'
DATA = ROOT / 'datasets'
BIN = ROOT / 'build'
LANGS = ['rust', 'go', 'java', 'csharp']
STAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z', re.ASCII)
IDENT = re.compile(r'[A-Za-z0-9_-]+', re.ASCII)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def oracle(raw):
    out = dict(lines=0, valid=0, invalid=0, latency_sum=0, errors=0, services={})
    lines = raw.split(b'\n')
    if lines[-1] == b'':
        lines.pop()
    for line_index, line in enumerate(lines):
        out['lines'] += 1
        terminated = line_index < len(lines)-1 or raw.endswith(b'\n')
        if terminated and line.endswith(b'\r'):
            line = line[:-1]
        good = all(c < 128 for c in line)
        text = line.decode('ascii', errors='replace')
        tokens = re.findall(r'[^ \t]+', text)
        good = good and len(tokens) >= 4
        latency = None
        if good:
            stamp, service, level, event = tokens[:4]
            good = bool(STAMP.fullmatch(stamp) and IDENT.fullmatch(service) and
                        1 <= len(service) <= 32 and level in ('DEBUG', 'INFO', 'WARN', 'ERROR')
                        and IDENT.fullmatch(event) and 1 <= len(event) <= 48)
            for token in tokens[4:]:
                pair = token.split('=')
                if len(pair) != 2 or not all(pair):
                    good = False
                    continue
                key, val = pair
                if key == 'latency_ms':
                    if latency is not None or not re.fullmatch(r'[0-9]{1,7}', val) or int(val) > 1000000:
                        good = False
                    else:
                        latency = int(val)
            good = good and latency is not None
        if not good:
            out['invalid'] += 1
            continue
        error = int(level == 'ERROR')
        out['valid'] += 1
        out['latency_sum'] += latency
        out['errors'] += error
        entry = out['services'].setdefault(service, dict(count=0, errors=0, latency_sum=0))
        entry['count'] += 1
        entry['errors'] += error
        entry['latency_sum'] += latency
    return out

def prepare(n):
    DATA.mkdir(exist_ok=True)
    base = '2026-11-13T12:00:00Z api INFO request latency_ms=42'
    fixtures = [base, '', ' ', base.replace('42', '0'), base.replace('42', '1000000'),
                base.replace('42', '1000001'), base.replace('42', '-1'), base.replace('42', '+1'),
                base.replace('42', '0000000'), base.replace('42', '00000000'),
                base.replace('42', '1.5'), base.replace('42', 'x'), base + ' latency_ms=9',
                base.replace(' latency_ms=42', ''), base + ' extra=a=b', base + ' extra=',
                base + ' =value', base + ' unknown=x unknown=y', base + ' extra=é',
                base.replace('api', 'x' * 32), base.replace('api', 'x' * 33),
                base.replace('api', 'api!'), base.replace('request', 'x' * 48),
                base.replace('request', 'x' * 49), base.replace('INFO', 'ERROR'),
                base.replace('INFO', 'info'), base.replace('T12', 'X12'),
                base.replace('2026', '20x6'), base.replace('2026', '0000'),
                '\t  ' + base.replace(' ', '\t  ') + ' \t', base + '\r',
                base.replace('42', '999999'), base + ' status=500', base + '\v',
                base.replace('request', 'réquest')]
    (DATA / 'golden.log').write_bytes(('\n'.join(fixtures) + '\n').encode())
    # A second fixture preserves no-final-newline and empty-file semantics.
    (DATA / 'no-final-newline.log').write_bytes((base + '\r\n' + base.replace('INFO', 'ERROR')).encode())
    (DATA / 'empty.log').write_bytes(b'')
    (DATA / 'unterminated-cr.log').write_bytes((base + '\r').encode())
    (DATA / 'bom.log').write_bytes(b'\xef\xbb\xbf' + base.encode())
    fuzz = random.Random(711)
    mutations = []
    for i in range(1200):
        line = fuzz.choice(fixtures)
        pos = fuzz.randrange(len(line) + 1)
        op = i % 4
        if op == 0:
            line = line[:pos] + fuzz.choice(['\t', ' ', '\v', '\x00', '\r', 'é', '=', '9']) + line[pos:]
        elif op == 1 and line:
            line = line[:pos] + line[pos+1:]
        elif op == 2:
            line += ' ' + fuzz.choice(['latency_ms=1', 'x=y', 'x=y=z', 'latency_ms=9999999'])
        mutations.append(line)
    (DATA / 'mutations.log').write_bytes(('\n'.join(mutations)).encode())
    rng = random.Random(20261113)
    for name in ('clean', 'noisy'):
        with (DATA / f'{name}.log').open('wb') as f:
            for i in range(n):
                service = ['api', 'billing', 'users', 'worker', 'auth', 'gateway', 'search', 'notify'][rng.randrange(8)]
                level = rng.choices(['INFO', 'WARN', 'ERROR', 'DEBUG'], [70, 15, 10, 5])[0]
                line = f'2026-11-13T12:{i % 60:02d}:{(i // 60) % 60:02d}Z {service} {level} request latency_ms={rng.randrange(10001)} status=200 route=/items'
                if name == 'noisy' and i % 20 == 0:
                    line = fixtures[(i // 20) % len(fixtures)]
                f.write((line + '\n').encode())
    manifests = {}
    for p in DATA.glob('*.log'):
        expected = oracle(p.read_bytes())
        save(p.with_suffix('.expected.json'), expected)
        manifests[p.name] = dict(sha256=sha(p), bytes=p.stat().st_size, expected=expected)
    save(ART / 'datasets.json', dict(seed=20261113, lines_per_corpus=n, generator_sha256=sha(Path(__file__)),
                                   python_version=sys.version, fixture_version=1, corpora=manifests))
    return manifests

def environment():
    env = os.environ.copy()
    env.update(DOTNET_CLI_HOME=str(BIN / 'dotnet-home'), DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
               DOTNET_CLI_TELEMETRY_OPTOUT='1', GOCACHE=str(BIN / 'go-cache'),
               GOPATH=str(BIN / 'go-home'), GOPROXY='off', GOTOOLCHAIN='local')
    return env

def commands():
    return {
        'rust': [str(BIN / 'parser-rust')],
        'go': [str(BIN / 'parser-go')],
        'java': ['/opt/homebrew/opt/openjdk/bin/java', '-cp', str(BIN / 'java'), 'Main'],
        'csharp': ['/opt/homebrew/bin/dotnet', str(BIN / 'csharp/Parser.dll')],
    }

def build():
    BIN.mkdir(exist_ok=True)
    builds = {
        'rust': ['rustc', '-O', '--edition=2021', str(ROOT / 'implementations/rust/main.rs'), '-o', str(BIN / 'parser-rust')],
        'go': ['go', 'build', '-trimpath', '-o', str(BIN / 'parser-go'), str(ROOT / 'implementations/go/main.go')],
        'java': ['/opt/homebrew/opt/openjdk/bin/javac', '-d', str(BIN / 'java'), str(ROOT / 'implementations/java/Main.java')],
        'csharp': ['dotnet', 'build', str(ROOT / 'implementations/csharp/Parser.csproj'), '-c', 'Release', '-o', str(BIN / 'csharp'), '--ignore-failed-sources', '-p:NuGetAudit=false'],
    }
    results = []
    for lang, cmd in builds.items():
        begin = time.monotonic()
        run = subprocess.run(cmd, env=environment(), capture_output=True, text=True, timeout=180)
        result = dict(name=lang, command=cmd, exit_code=run.returncode,
                      duration_ms=(time.monotonic()-begin)*1000, stdout=run.stdout, stderr=run.stderr)
        results.append(result)
        save(ART / 'build-results.json', dict(targets=results))
        if run.returncode:
            raise RuntimeError(f'{lang} build failed: {run.stderr}')
    return results

def valid_rows(rows, expected, count):
    def integer_tree(value):
        if isinstance(value, dict):
            return all(integer_tree(v) for v in value.values())
        return type(value) is int
    return len(rows) == count and all(
        set(row) == {'pass','elapsed_ns','result'} and type(row['pass']) is int and row['pass'] == i
        and type(row['elapsed_ns']) is int and (row['elapsed_ns'] > 0 or (expected['lines'] == 0 and row['elapsed_ns'] == 0))
        and integer_tree(row['result']) and row['result'] == expected
        for i, row in enumerate(rows))

def capture_environment():
    probes = {
        'rustc':['rustc','--version'], 'go':['go','version'],
        'java':['/opt/homebrew/opt/openjdk/bin/java','--version'],
        'dotnet':['dotnet','--info'], 'os':['sw_vers'],
        'cpu':['sysctl','-n','machdep.cpu.brand_string'],
        'memory_bytes':['sysctl','-n','hw.memsize'], 'architecture':['uname','-m'],
        'power':['pmset','-g','batt'], 'git_commit':['git','rev-parse','HEAD'],
    }
    probes_out = {}
    for name, argv in probes.items():
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=20, env=environment())
            probes_out[name] = dict(command=argv, exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except Exception as exc:
            probes_out[name] = dict(error=str(exc))
    sources = list((ROOT/'implementations').rglob('*.rs')) + list((ROOT/'implementations').rglob('*.go')) + list((ROOT/'implementations').rglob('*.java')) + [ROOT/'implementations/csharp/Program.cs',ROOT/'implementations/csharp/Parser.csproj',ROOT/'CONTRACT.md',ROOT/'spec.yaml',Path(__file__)]
    binaries = [BIN/'parser-rust',BIN/'parser-go',BIN/'java/Main.class',BIN/'csharp/Parser.dll']
    return dict(ts_utc=now(), probes=probes_out, python=sys.version,
                sources_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
                binaries_sha256={str(p.relative_to(ROOT)):sha(p) for p in binaries},
                dataset_manifest_sha256=sha(ART/'datasets.json'),
                note='Native macOS pilot, no CPU or memory hard limits; background load and thermals not controlled.')

def verify():
    results = []
    for lang, cmd in commands().items():
        for variant in ('split', 'scan'):
            for fixture in ('golden', 'mutations', 'no-final-newline', 'unterminated-cr', 'bom', 'empty', 'clean', 'noisy'):
                p = DATA / f'{fixture}.log'
                argv = cmd + [str(p), variant, '1', '2']
                run = subprocess.run(argv, env=environment(), capture_output=True, text=True, timeout=60)
                expected = json.loads(p.with_suffix('.expected.json').read_text())
                try:
                    rows = [json.loads(line) for line in run.stdout.splitlines()]
                    passed = run.returncode == 0 and valid_rows(rows, expected, 2)
                except Exception:
                    passed = False
                results.append(dict(target=lang, variant=variant, fixture=fixture, passed=passed,
                                    command=argv, exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr))
                save(ART / 'test-results.json', dict(tests=results, passed=all(x['passed'] for x in results)))
                if not passed:
                    raise RuntimeError(f'Contract failed: {lang}/{variant}/{fixture}; see test-results.json')
    return results

def measure(lines):
    run_group = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    raw_root = ART / 'raw' / run_group
    raw_root.mkdir(parents=True)
    save(ART/'benchmark-results.json', dict(status='running', run_group=run_group, aggregates=[]))
    save(ART/'evidence-index.json', dict(status='running', run_group=run_group, evidence=[]))
    metadata = capture_environment()
    save(raw_root/'environment.json', metadata)
    for relative in metadata['sources_sha256']:
        target = raw_root/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
    for receipt in ('datasets.json','build-results.json','test-results.json'):
        shutil.copyfile(ART/receipt, raw_root/receipt)
    metadata_sha256 = sha(raw_root/'environment.json')
    records = []
    for trial in range(5):
        rotated = LANGS[trial % 4:] + LANGS[:trial % 4]
        if trial % 2:
            rotated.reverse()
        for corpus in (('clean', 'noisy') if trial % 2 == 0 else ('noisy', 'clean')):
            for lang in rotated:
                for variant in (('split', 'scan') if trial % 2 == 0 else ('scan', 'split')):
                    run_id = f'{lang}-{variant}-{corpus}-r{trial+1}'
                    folder = raw_root / run_id
                    folder.mkdir()
                    argv = commands()[lang] + [str(DATA / f'{corpus}.log'), variant, '5', '3']
                    origin = now()
                    start = time.monotonic()
                    try:
                        proc = subprocess.run(['/usr/bin/time', '-l'] + argv, env=environment(),
                                              capture_output=True, text=True, timeout=120)
                        elapsed = (time.monotonic()-start)*1000
                        (folder / 'stdout.jsonl').write_text(proc.stdout)
                        (folder / 'stderr.txt').write_text(proc.stderr)
                        rows = [json.loads(line) for line in proc.stdout.splitlines()]
                        expected = json.loads((DATA / f'{corpus}.expected.json').read_text())
                        ok = proc.returncode == 0 and valid_rows(rows, expected, 3)
                        rss = re.search(r'(\d+)\s+maximum resident set size', proc.stderr)
                        record = dict(run_id=run_id, target=lang, variant=variant, corpus=corpus,
                                      trial=trial+1, ts_utc=origin, command=argv, exit_code=proc.returncode,
                                      process_elapsed_ms=elapsed, peak_rss_bytes=int(rss[1]) if rss else None,
                                      correctness=ok, rows=rows,
                                      median_elapsed_ns=statistics.median(r['elapsed_ns'] for r in rows) if ok else None,
                                      source=str(folder.relative_to(OUT)), run_group=run_group,
                                      metadata_sha256=metadata_sha256, corpus_sha256=sha(DATA/f'{corpus}.log'))
                    except Exception as exc:
                        record = dict(run_id=run_id, target=lang, variant=variant, corpus=corpus,
                                      trial=trial+1, ts_utc=origin, command=argv, correctness=False,
                                      exception=str(exc), source=str(folder.relative_to(OUT)))
                    save(folder / 'manifest.json', record)
                    records.append(record)
                    save(ART / 'run-ledger.json', dict(run_group=run_group, runs=records))
                    print(f"{run_id}: {'PASS' if record['correctness'] else 'FAIL'}", flush=True)
                    if not record['correctness']:
                        raise RuntimeError(f'Invalid run {run_id}; raw retained')
                    time.sleep(.25)
    aggregates = []
    evidence = []
    for corpus in ('clean', 'noisy'):
        for lang in LANGS:
            for variant in ('split', 'scan'):
                selected = [r for r in records if (r['corpus'],r['target'],r['variant']) == (corpus,lang,variant)]
                values = [lines * 1e9/r['median_elapsed_ns'] for r in selected]
                eid = f'{lang}-{variant}-{corpus}-throughput'
                aggregates.append(dict(evidence_id=eid, corpus=corpus, target=lang, variant=variant,
                                       unit='lines/s', trial_values=values, median=statistics.median(values),
                                       min=min(values), max=max(values), stddev=statistics.stdev(values),
                                       trial_count=len(values), run_ids=[r['run_id'] for r in selected],
                                       peak_rss_bytes=[r['peak_rss_bytes'] for r in selected]))
                evidence.append(dict(id=eid, metric='resident_parse_aggregate_throughput', unit='lines/s',
                                     measurement_kind='derived', formula='median(line_count*1e9/median(3 pass elapsed_ns)) over 5 fresh processes',
                                     source_files=[r['source']+'/stdout.jsonl' for r in selected]))
    results = dict(status='measured_native_pilot', run_group=run_group, metadata_sha256=metadata_sha256, aggregates=aggregates)
    index = dict(run_group=run_group, evidence=evidence)
    save(raw_root/'benchmark-results.json', results)
    save(raw_root/'evidence-index.json', index)
    save(ART / 'benchmark-results.json', results)
    save(ART / 'evidence-index.json', index)
    hashes = {str(p.relative_to(OUT)):sha(p) for p in raw_root.rglob('*') if p.is_file()}
    save(ART / 'replay-manifest.json', dict(run_group=run_group, raw_sha256=hashes, runs=len(records)))
    return aggregates

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare','build','verify','measure','all'])
    parser.add_argument('--lines', type=int, default=200000)
    args = parser.parse_args()
    ART.mkdir(parents=True, exist_ok=True)
    actions = ['prepare','build','verify','measure'] if args.action == 'all' else [args.action]
    for action in actions:
        if action == 'prepare': prepare(args.lines)
        elif action == 'build': build()
        elif action == 'verify': verify()
        else: measure(json.loads((DATA/'clean.expected.json').read_text())['lines'])

if __name__ == '__main__':
    main()
