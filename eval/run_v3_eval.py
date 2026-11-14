#!/usr/bin/env python3
"""Reproducible v3 runs; each attempt is immutable and uses a shared USD ledger."""
import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence.agent_harness import Harness
from evidence.config import Settings
from evidence.db import AuditDB
from eval.run_eval import FrozenProvider, full_text_baseline, register, score, save
from eval.v3_budget import V3BudgetAdapter, DEFAULT_PATH

HERE = ROOT / 'eval'
CODE_VERSION = {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'evidence_source_sha256': hashlib.sha256(b''.join(p.name.encode() + p.read_bytes() for p in sorted((ROOT / 'evidence').glob('*.py')))).hexdigest()}


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def case_rows(public):
    return [r for group in public['reports'][-1]['repositories'] for r in group['rows']] if public['reports'] else []


def metrics(db, session):
    with db.connect() as conn:
        calls = [dict(x) for x in conn.execute('SELECT role,status,input_tokens,output_tokens,elapsed_ms FROM model_calls WHERE session_id=?', (session,))]
    return {'model_calls': len(calls), 'lead_calls': sum(x['role'] == 'lead' for x in calls),
            'lead_input_peak': max((x['input_tokens'] or 0 for x in calls if x['role'] == 'lead'), default=0),
            'known_input_tokens': sum(x['input_tokens'] or 0 for x in calls),
            'known_output_tokens': sum(x['output_tokens'] or 0 for x in calls),
            'unknown_calls': sum(x['status'] in ('UNKNOWN', 'STARTED') for x in calls)}


async def run_case(case, fixtures, route, output_dir, batch_id):
    attempt = stamp()
    label = f'{batch_id}/{case["id"]}/{route}/{attempt}'
    db_path = ROOT / '.evidence-data' / 'v3-eval' / attempt
    db = AuditDB(replace(Settings(), data_dir=db_path))
    register(db, case)
    adapter = V3BudgetAdapter(label)
    provider = FrozenProvider(db, fixtures)
    item = {'id': case['id'], 'attempt': attempt, 'batch': batch_id, 'route_requested': route,
            'origin': case.get('origin', 'synthetic'), 'query': case['query'], 'repo': case['repo'], 'commit': case['commit'],
            'model': adapter.config['model'], 'effort': adapter.config['effort'], 'db_path': str(db_path), 'code_version': CODE_VERSION,
            'input_fixture_sha256': hashlib.sha256(json.dumps(fixtures[case['repo']], sort_keys=True).encode()).hexdigest()}
    started = time.monotonic()
    try:
        if route == 'full_text':
            item.update(await full_text_baseline(case, fixtures, db, adapter))
        else:
            harness = Harness(db, adapter, provider)
            session = harness.create([case['id']], case['query'], workflow_mode=case.get('workflow_mode', 'deploy_readiness'), force_full=route == 'full')
            item['session_id'] = session
            await harness.run(session)
            public = harness.store.public(session)
            item.update(execution_status=public['status'], reports=public['reports'], usage=public['usage'],
                        grading=score(case, case_rows(public), db), tool_calls=provider.calls, metrics=metrics(db, session),
                        events=public['events'])
    except Exception as exc:
        item.update(error=str(exc), grading={'score': 0, 'reason': 'execution_error', 'observed': []})
        if item.get('session_id'):
            public = harness.store.public(item['session_id'])
            item.update(execution_status=public['status'], reports=public['reports'], usage=public['usage'],
                        metrics=metrics(db, item['session_id']), events=public['events'], tool_calls=provider.calls)
    item['duration_seconds'] = round(time.monotonic() - started, 3)
    ledger = json.loads(DEFAULT_PATH.read_text())
    item['request_records'] = [x for x in ledger['calls'] if x['label'] == label]
    save(output_dir / f'{case["id"]}-{route}-{attempt}.json', item)
    print(json.dumps({'id': case['id'], 'route': route, 'grading': item['grading'], 'error': item.get('error'),
                      'estimated_usd': round(ledger['estimated_usd'], 6), 'reserved_usd': round(ledger['reserved_usd'], 6)}, ensure_ascii=False), flush=True)
    return item


async def main(args):
    cases = json.loads((HERE / 'golden_cases.json').read_text())['cases']
    fixtures = json.loads((HERE / 'fixtures/repositories.json').read_text())
    selected = [x for x in cases if x['category'] != 'citation_guard']
    if args.cases:
        selected = [x for x in selected if x['id'] in args.cases.split(',')]
    if args.batch == 'comparison':
        selected = [x for x in selected if x['id'] in ('A1', 'A2', 'A3', 'A4')]
    batch_id = f'{args.batch}-{stamp()}'
    output = HERE / 'v3' / 'runs' / batch_id
    output.mkdir(parents=True, exist_ok=False)
    planned = [(case, route) for case in selected for route in (('full', 'full_text') if args.batch == 'comparison' else ('auto',))]
    if args.batch == 'regression' and any(x['id'] == 'C3' for x in selected):
        planned += [(next(x for x in selected if x['id'] == 'C3'), 'auto')] * 2
    save(output / 'manifest.json', {'created_at': batch_id, 'shared_ledger': str(DEFAULT_PATH),
                                   'planned': [{'id': c['id'], 'route': r} for c, r in planned], 'status': 'planned'})
    for case, route in planned:
        result = await run_case(case, fixtures, route, output, batch_id)
        if '5 美元' in result.get('error', '') or 'HTTP 401' in result.get('error', ''):
            break
    print(str(output), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', choices=['regression', 'comparison', 'pilot'], required=True)
    parser.add_argument('--cases')
    asyncio.run(main(parser.parse_args()))
