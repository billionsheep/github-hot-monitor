#!/usr/bin/env python3
"""Real read-only repository demos, persistent attempts and globally budgeted model calls."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence.agent_harness import Harness
from evidence.db import AuditDB
from evidence.replay import make_bundle, read_bundle, markdown
from eval.run_eval import save
from eval.run_v3_eval import metrics, CODE_VERSION
from eval.v3_budget import V3BudgetAdapter, DEFAULT_PATH


async def main(args):
    cases = json.loads((ROOT / 'eval/v3/recording_cases.json').read_text())['cases']
    case = next(x for x in cases if x['id'] == args.case)
    if not os.environ.get('GITHUB_TOKEN'):
        os.environ['GITHUB_TOKEN'] = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, check=True).stdout.strip()
    db = AuditDB()
    index = ROOT / '.evidence-data/v3-recordings' / (case['id'] + '.json')
    attempt = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    label = f'recording/{case["id"]}/{attempt}'
    harness = Harness(db, V3BudgetAdapter(label))
    if index.exists() and not args.new:
        session = json.loads(index.read_text())['session_id']
    else:
        snapshots = []
        with db.connect() as conn:
            for b in case['bindings']:
                row = conn.execute('SELECT id FROM repo_snapshots WHERE repo=? AND sha=? AND public_verified=1 LIMIT 1', (b['repo'], b['commit'])).fetchone()
                if not row: raise ValueError('先创建并验证固定提交快照：' + b['repo'])
                snapshots.append(row['id'])
        session = harness.create(snapshots, case['query'], workflow_mode=case['workflow_mode'])
        save(index, {'session_id': session, 'case': case['id'], 'created_at': attempt})
    result = {'case': case['id'], 'attempt': attempt, 'session_id': session, 'workflow_mode': case['workflow_mode'], 'followup': args.followup, 'code_version': CODE_VERSION}
    started = time.monotonic()
    try:
        if args.followup:
            harness.store.followup(session, case['followup'])
        await harness.run(session)
    except Exception as exc:
        result['error'] = str(exc)
    public = harness.store.public(session)
    result.update(status=public['status'], reports=public['reports'], events=public['events'], usage=public['usage'], metrics=metrics(db, session),
                  duration_seconds=round(time.monotonic()-started, 3))
    ledger = json.loads(DEFAULT_PATH.read_text())
    result['request_records'] = [c for c in ledger['calls'] if c['label'] == label]
    if args.export and public['status'] == 'COMPLETED':
        try:
            bundle = make_bundle(db, session)
            data = (json.dumps(bundle, ensure_ascii=False, indent=2) + '\n').encode()
            payload = read_bundle(data)
            archive = ROOT / 'eval/v3/recording_bundles' / (case['id'] + '-' + attempt + '.json')
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(data)
            target = ROOT / 'web/replays' / ('v3-' + case['id'] + '.json')
            target.write_bytes(data)
            (ROOT / 'docs/project/examples' / ('v3-' + case['id'] + '.md')).write_text('\n'.join(line.rstrip() for line in markdown(payload['session'], payload['evidence']).splitlines()) + '\n')
            result['export'] = {'path': str(target.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'schema_version': bundle['schema_version']}
        except Exception as exc:
            result['export_error'] = str(exc)
    save(ROOT / 'eval/v3/recordings' / (case['id'] + '-' + attempt + '.json'), result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('reports', 'events', 'request_records')}, ensure_ascii=False), flush=True)
    if public['status'] != 'COMPLETED' or result.get('export_error'):
        raise SystemExit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--followup', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--new', action='store_true')
    asyncio.run(main(parser.parse_args()))
