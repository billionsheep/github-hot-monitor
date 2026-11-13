#!/usr/bin/env python3
"""Four multi-file tool contracts; recorded separately from model quality runs."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence.config import Settings
from evidence.db import AuditDB
from evidence.guardrails import validate_derived
from eval.run_eval import FrozenProvider, save


async def main():
    fixtures = {}
    for file in ('fixtures/real_candidates.json', 'v3/mcp_fixture.json', 'v3/security_fixtures.json'):
        fixtures.update(json.loads((ROOT / 'eval' / file).read_text()))
    cases = [
        ('M1', ['pydantic/pydantic-ai', 'agno-agi/agno'], 'analyze_architecture_profile', 'real selected source snapshots'),
        ('M2', ['modelcontextprotocol/python-sdk'], 'analyze_architecture_profile', 'real selected source snapshots'),
        ('M3', ['eval/v3-exec'], 'scan_security_and_risk_sinks', 'synthetic contrast'),
        ('M4', ['eval/v3-credential-prompt'], 'scan_security_and_risk_sinks', 'synthetic contrast'),
    ]
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        db = AuditDB(replace(Settings(), data_dir=Path(tmp)))
        provider = FrozenProvider(db, fixtures)
        for id, repos, tool, origin in cases:
            item = {'id': id, 'origin': origin, 'tool': tool, 'checks': [], 'repos': []}
            for repo in repos:
                f = fixtures[repo];binding = {'repo': repo, 'commit': f['commit']}
                args = {'path_prefix': ''}
                if tool == 'scan_security_and_risk_sinks': args['mode'] = 'all'
                result = await provider.call(binding, tool, args)
                derived = [e for e in result['evidence'] if e['source_type'] in ('arch_profile', 'security_scan')]
                if not derived:
                    item['checks'].append({'name': repo + ' produces artifact', 'passed': False, 'errors': result['errors']});continue
                body = json.loads(derived[0]['text'])
                entries = body.get('edges', body.get('findings', []))
                valid = validate_derived(derived[0], db.get_evidence)
                item['checks'].append({'name': repo + ' source binding/hash/range', 'passed': valid})
                if f.get('selected_files_only'):
                    item['checks'].append({'name': repo + ' marks selected scope incomplete', 'passed': not body['scope']['complete']})
                if id == 'M3':
                    paths = {x['path'] for x in entries if x['category'] == 'exec_sinks'}
                    item['checks'].append({'name': 'both legitimate and input-dependent execution are review signals', 'passed': {'safe_exec.py', 'review_exec.py'} <= paths})
                    item['checks'].append({'name': 'no rule match is marked confirmed vulnerability', 'passed': all(x['assessment'] in ('rule_hit', 'insufficient_evidence') for x in entries)})
                if id == 'M4':
                    env = {x['path'] for x in entries if x['category'] == 'env_and_network'}
                    injection = {x['path'] for x in entries if x['category'] == 'prompt_injection'}
                    item['checks'].append({'name': 'standalone environment and transmission are visible separately', 'passed': {'env_local.py', 'network_review.py'} <= env})
                    item['checks'].append({'name': 'instruction override appears as untrusted document signal', 'passed': 'README.md' in injection})
                item['repos'].append({'binding': binding, 'scope': body['scope'], 'entry_count': len(entries),
                                      'derived_evidence_id': derived[0]['evidence_id'], 'artifact_sha256': derived[0]['artifact_sha256'], 'entries': entries})
            item['passed'] = all(x['passed'] for x in item['checks'])
            results.append(item)
            print(json.dumps({'id': id, 'passed': item['passed'], 'checks': item['checks']}, ensure_ascii=False))
    save(ROOT / 'eval/v3/multifile_tool_results.json', {'evaluation_type': 'deterministic_tool_contract_not_model_score', 'cases': results})
    if not all(x['passed'] for x in results): raise SystemExit(1)

if __name__ == '__main__': asyncio.run(main())
