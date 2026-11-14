#!/usr/bin/env python3
"""Offline verification of delivered recordings against local frozen source blobs."""
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence.db import AuditDB
from evidence.guardrails import source_matches_blob
from evidence.replay import read_bundle


def main():
    db = AuditDB()
    baseline = json.loads((ROOT / 'eval/v3/baseline.json').read_text())
    checks = [{'check': 'v2_original_bytes', 'path': path,
               'passed': hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected}
              for path, expected in baseline['original_replays'].items()]
    records = []
    for path in sorted((ROOT / 'web/replays').glob('v3-*.json')):
        payload = read_bundle(path.read_bytes())
        files = [e for e in payload['evidence'].values() if e['source_type'] == 'file_lines']
        matched = sum(source_matches_blob(e, db) for e in files)
        reports = payload['session']['reports']
        entry = {'file': str(path.relative_to(ROOT)), 'session_id': payload['session']['id'],
                 'workflow_mode': reports[0]['workflow_mode'], 'reports': len(reports),
                 'file_evidence': len(files), 'matches_frozen_blob': matched,
                 'graph_edges': sum(len(g['edges']) for r in reports for g in r.get('architecture_graph', [])),
                 'security_findings': sum(len(g['findings']) for r in reports for g in r.get('security_findings', [])),
                 'context_reviews': sum(f['assessment'] == 'context_reviewed' for r in reports for g in r.get('security_findings', []) for f in g['findings']),
                 'blueprints': sum(len(r.get('integration_blueprint', [])) for r in reports),
                 'passed': bool(files) and matched == len(files)}
        quotes = '\n'.join(c['quote'] for report in reports for group in report['repositories'] for row in group['rows'] for c in row['citations'])
        if entry['workflow_mode'] == 'arch_research':
            entry['workflow_contract'] = entry['graph_edges'] > 0 and 'base_url=base_url' in quotes and 'OpenAIClient(**client_params)' in quotes
        elif entry['workflow_mode'] == 'sec_sentinel':
            entry['workflow_contract'] = entry['security_findings'] > 0 and entry['context_reviews'] > 0
        else:
            entry['workflow_contract'] = entry['blueprints'] > 0
        entry['passed'] = entry['passed'] and entry['workflow_contract'] and len(reports) >= 2
        records.append(entry)
    modes = {r['workflow_mode'] for r in records}
    checks.append({'check': 'three_workflows', 'passed': modes == {'arch_research','sec_sentinel','deploy_readiness'}})
    result = {'checks': checks, 'recordings': records,
              'passed': all(x['passed'] for x in checks + records),
              'verification_scope': 'Bundle contracts plus comparison to locally cached fixed-commit blobs; semantic judgments reviewed separately.'}
    target = ROOT / 'eval/v3/delivery_validation.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
    if not result['passed']: raise SystemExit(1)


if __name__ == '__main__': main()
