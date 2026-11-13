import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from fastapi.testclient import TestClient
from evidence import app as mod

SHA = "a" * 40
class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(mod, "DB_PATH", Path(self.tmp.name) / "db.sqlite")
        self.db_patch.start()
        self.client = TestClient(mod.app)
        self.raw = b'# Hello\n<script>alert(1)</script>\n'
        self.entries = [{"path": "README.md", "type": "blob", "sha": "b" * 40, "size": len(self.raw), "mode": "100644"}, {"path": "src", "type": "tree", "sha": "c" * 40, "mode": "040000"}]
        self.calls = []
        self.mock = patch.object(mod, "github_json", side_effect=self.github)
        self.mock.start()
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.db_patch.stop); self.addCleanup(self.mock.stop)
    def github(self, path):
        self.calls.append(path)
        if path == '/repos/test/repo': return {"full_name":"test/repo", "default_branch":"main", "private":False}
        if '/commits/' in path: return {"sha":SHA}
        if '/git/trees/' in path: return {"tree":self.entries, "truncated":False}
        if '/git/blobs/' in path: return {"size":len(self.raw), "content":base64.b64encode(self.raw).decode()}
        raise AssertionError(path)
    def create(self):
        r = self.client.post('/api/snapshots', json={'repository':'https://github.com/test/repo'})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['id']
    def get(self, id, path='README.md', **kwargs):
        return self.client.get(f'/api/snapshots/{id}/fragment', params={'path':path, **kwargs})
    def test_snapshot_fragment_cache_and_source(self):
        id = self.create()
        a = self.get(id).json(); b = self.get(id).json()
        self.assertFalse(a['cache_hit']); self.assertTrue(b['cache_hit'])
        self.assertEqual(a['text'], self.raw.decode()); self.assertEqual(a['content_sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(a['source_url'], f'https://github.com/test/repo/blob/{SHA}/README.md#L1-L2')
        self.assertEqual(sum('/git/blobs/' in x for x in self.calls), 1)
        self.assertIn(SHA, next(x for x in self.calls if '/git/trees/' in x))
    def test_invalid_repository_and_paths(self):
        for repo in ['https://evil.com/a/b', 'https://github.com/a/b/issues', 'a/../b']:
            self.assertEqual(self.client.post('/api/snapshots',json={'repository':repo}).status_code, 422)
        id = self.create()
        for path in ['../secret', '/etc/passwd', 'a//b', 'https://github.com/other/repo', 'a\\b']:
            self.assertEqual(self.get(id, path).status_code, 422)
    def test_missing_readme_and_tree_truncation(self):
        self.entries = []
        id = self.create()
        self.assertEqual(self.get(id).json()['detail']['code'], 'path_not_found')
        with mod.database() as db: db.execute('DELETE FROM cache')
        self.mock.stop()
        with patch.object(mod, 'github_json', return_value={'tree':[], 'truncated':True}):
            tree = self.client.get(f'/api/snapshots/{id}/tree').json()
            self.assertTrue(tree['truncated'])
            self.assertEqual(self.get(id).json()['detail']['code'], 'tree_incomplete')
    def test_binary_and_size_and_limits(self):
        self.raw = b'\x00binary'
        id = self.create(); self.assertEqual(self.get(id).status_code, 415)
        self.entries[0]['size'] = mod.MAX_FILE + 1
        with mod.database() as db: db.execute('DELETE FROM cache')
        self.assertEqual(self.get(id).status_code, 413)
        self.assertEqual(self.get(id, lines=201).status_code, 422)
    def test_line_and_byte_truncation(self):
        self.raw = (b'x\n' * 250)
        id = self.create(); result = self.get(id).json()
        self.assertEqual(result['end_line'], 200); self.assertTrue(result['truncated']); self.assertFalse(result['partial_line'])
        with mod.database() as db: db.execute('DELETE FROM cache')
        self.raw = ('汉' * 6000).encode()
        result = self.get(id).json()
        self.assertLessEqual(len(result['text'].encode()), 16384); self.assertTrue(result['partial_line']); self.assertTrue(result['truncated'])
    def test_preserves_complete_lines_before_byte_limit(self):
        self.raw = b'first\n' + b'x' * 16384 + b'\nlast\n'
        id = self.create()
        first = self.get(id).json()
        self.assertEqual(first['text'], 'first\n')
        self.assertEqual(first['end_line'], 1)
        self.assertTrue(first['truncated']); self.assertFalse(first['partial_line'])
        second = self.get(id, start=2).json()
        self.assertTrue(second['partial_line']); self.assertEqual(second['end_line'], 2)
    def test_line_numbers_follow_lf_only(self):
        self.raw = 'a\u2028b\r c\nlast'.encode()
        id = self.create()
        item = self.get(id).json()
        self.assertEqual(item['end_line'], 2)
        self.assertEqual(item['text'], self.raw.decode())
    def test_empty_file_has_no_line_numbers_and_stable_identity(self):
        self.raw = b''
        id = self.create()
        first = self.get(id).json()
        second = self.get(self.create()).json()
        self.assertTrue(first['empty'])
        self.assertIsNone(first['start_line']); self.assertIsNone(first['end_line'])
        self.assertNotIn('#L', first['source_url'])
        self.assertEqual(first['fragment_sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual(first['evidence_id'], second['evidence_id'])
    def test_evidence_id_tracks_range_content_and_commit(self):
        id = self.create()
        a = self.get(id, lines=1).json(); b = self.get(id, lines=1).json()
        c = self.get(id, start=2).json()
        self.assertEqual(a['evidence_id'], b['evidence_id'])
        self.assertNotEqual(a['evidence_id'], c['evidence_id'])
        self.assertEqual(a['fragment_sha256'], hashlib.sha256(b'# Hello\n').hexdigest())
        with mod.database() as db: db.execute('UPDATE snapshots SET sha=? WHERE id=?', ('d' * 40, id))
        d = self.get(id, lines=1).json()
        self.assertNotEqual(a['evidence_id'], d['evidence_id'])
    def test_response_contracts_and_validation_error(self):
        schema = self.client.get('/openapi.json').json()['components']['schemas']
        for name in ('SnapshotResponse', 'TreeResponse', 'FragmentResponse', 'ErrorResponse'):
            self.assertIn(name, schema)
        self.assertEqual(self.client.get('/api/capabilities').json()['service'], 'github-hot-monitor-evidence')
        self.assertEqual(self.client.post('/api/snapshots', json={}).json()['detail']['code'], 'invalid_request')
    def test_snapshot_missing_and_repository_missing(self):
        self.assertEqual(self.client.get('/api/snapshots/no/tree').status_code, 404)
        with patch.object(mod, 'github_json', side_effect=mod.HTTPException(404, detail={'code':'github_not_found','message':'missing'})):
            self.assertEqual(self.client.post('/api/snapshots',json={'repository':'test/missing'}).json()['detail']['code'], 'github_not_found')

class NetworkErrorsTest(unittest.TestCase):
    def test_rate_limit_and_timeout(self):
        error = HTTPError('https://api.github.com', 403, '', {'X-RateLimit-Remaining':'0'}, None)
        with patch.object(mod, 'urlopen', side_effect=error):
            with self.assertRaises(mod.HTTPException) as ctx: mod.github_json('/x')
            self.assertEqual(ctx.exception.detail['code'], 'rate_limited')
        with patch.object(mod, 'urlopen', side_effect=URLError('timeout')) as req, patch.object(mod.time, 'sleep'):
            with self.assertRaises(mod.HTTPException) as ctx: mod.github_json('/x')
            self.assertEqual(ctx.exception.detail['code'], 'github_timeout'); self.assertEqual(req.call_count, 3)
    def test_github_not_found(self):
        with patch.object(mod, 'urlopen', side_effect=HTTPError('https://api.github.com',404,'',{},None)):
            with self.assertRaises(mod.HTTPException) as ctx: mod.github_json('/x')
            self.assertEqual(ctx.exception.detail['code'], 'github_not_found')

if __name__ == '__main__': unittest.main()
