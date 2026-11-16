import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from evidence import cli


class SkillCliTests(unittest.TestCase):
    def invoke(self, args, transport=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main(args, transport=transport)
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        return status, json.loads(output.getvalue())

    def test_index_and_bounded_local_declarations(self):
        status, index = self.invoke(['skills'])
        self.assertEqual(status, 0)
        self.assertEqual({s['id'] for s in index['skills']}, set(cli.MODES))
        self.assertEqual(index['input_schema']['properties']['repos']['maxItems'], 3)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'pyproject.toml').write_text('[project]\nrequires-python = ">=3.11,<3.13"\n')
            (root / '.env.example').write_text('MODEL_API_KEY=example-secret\nMODEL_BASE_URL=http://local\n')
            (root / '.env').write_text('SECRET=never-read-this\n')
            (root / '.python-version').symlink_to(root / '.env')
            status, result = self.invoke(['inspect', '--project', tmp])
            self.assertEqual(status, 0)
            self.assertEqual(result['python_constraints'][0]['value'], '>=3.11,<3.13')
            self.assertEqual(result['environment_keys'], ['MODEL_API_KEY', 'MODEL_BASE_URL'])
            self.assertNotIn('example-secret', json.dumps(result))
            self.assertNotIn('never-read-this', json.dumps(result))
            self.assertTrue(any('符号链接' in x for x in result['gaps']))

    def test_replay_json_and_review_url(self):
        for name in ('v3-architecture-gateway.json', 'v3-mcp-security-signals.json'):
            with self.subTest(name=name):
                code, result = self.invoke(['replay', '--replay', name])
                self.assertEqual(code, 0)
                self.assertEqual(result['status'], 'COMPLETED')
                self.assertTrue(result['rows'])
                self.assertEqual(result['workbench_url'], cli.PUBLIC_WORKBENCH + '?replay=' + name)
                review = any(row['status'] in ('FAIL', 'RISK', 'UNVERIFIED') for row in result['rows'])
                self.assertEqual(result['review_required'], review)
                self.assertEqual(result['review_url'], result['workbench_url'] if review else None)
        code, error = self.invoke(['replay', '--replay', '../../.env.local'])
        self.assertEqual(code, 1)
        self.assertEqual(error['status'], 'ERROR')

    def test_live_api_contract_and_existing_session(self):
        fixture = json.loads(json.loads((cli.ROOT / 'web/replays/v3-pydantic-deploy-blueprint.json').read_text())['payload_json'])['session']
        fixture['id'] = 'cli-test-session'
        calls = []

        def handle(request):
            calls.append((request.method, request.url.path))
            if request.url.path == '/api/health':
                data = {'status': 'ok', 'model_ready': True}
            elif request.url.path == '/api/phase1/snapshots':
                self.assertEqual(json.loads(request.content), {'repo': 'pydantic/pydantic-ai'})
                data = {'id': 'snapshot'}
            elif request.method == 'POST':
                body = json.loads(request.content)
                self.assertEqual(body['workflow_mode'], 'deploy_readiness')
                self.assertEqual(body['snapshot_ids'], ['snapshot'])
                self.assertTrue(body['idempotency_key'])
                data = {'session_id': fixture['id']}
            else:
                data = fixture
            return httpx.Response(200, json=data)

        transport = httpx.MockTransport(handle)
        code, result = self.invoke(['run', '--workflow', 'deploy_readiness', '--repo', 'https://github.com/pydantic/pydantic-ai', '--wait', '0'], transport)
        self.assertEqual(code, 0)
        self.assertEqual(result['workbench_url'], 'http://127.0.0.1:8773/?session=cli-test-session')
        self.assertFalse(result['wait_expired'])
        self.assertEqual(len(calls), 4)
        calls.clear()
        fixture['status'] = 'INVESTIGATING'
        code, result = self.invoke(['result', '--session', fixture['id']], transport)
        self.assertEqual(code, 0)
        self.assertTrue(result['wait_expired'])
        self.assertTrue(result['review_required'])
        self.assertEqual(calls, [('GET', '/api/audit/sessions/cli-test-session')])
        failed = httpx.MockTransport(lambda request: httpx.Response(503, json={'detail': 'unavailable'}))
        code, result = self.invoke(['result', '--session', fixture['id']], failed)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['review_url'], 'http://127.0.0.1:8773/?session=cli-test-session')
        code, error = self.invoke(['result', '--session', fixture['id'], '--base-url', 'https://unrelated.example'], transport)
        self.assertEqual(code, 1)
        self.assertEqual(error['status'], 'ERROR')


if __name__ == '__main__':
    unittest.main()
