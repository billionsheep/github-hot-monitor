"""Versioned WAL cache with lossless, verified legacy import."""
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from evidence.config import Settings

SCHEMA_VERSION = 4
class AuditDB:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.initialize()
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.settings.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            # Switching a newly created database to WAL can race other first-open
            # connections; SQLite may return BUSY immediately despite its timeout.
            for attempt in range(100):
                try:
                    db.execute('PRAGMA journal_mode=WAL')
                    break
                except sqlite3.OperationalError as exc:
                    if 'locked' not in str(exc).lower() or attempt==99: raise
                    time.sleep(0.05)
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=NORMAL')
            with db: yield db
        finally: db.close()
    def initialize(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > SCHEMA_VERSION: raise RuntimeError('Database schema is newer than this application')
            if version == 0:
                statements = [
                    "CREATE TABLE repo_snapshots (id TEXT PRIMARY KEY, repo TEXT NOT NULL, sha TEXT NOT NULL, created_at TEXT NOT NULL)",
                    "CREATE INDEX snapshot_version_idx ON repo_snapshots(repo,sha)",
                    "CREATE TABLE file_blob_cache (repo TEXT NOT NULL, sha TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, payload TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(repo,sha,kind,path))",
                    "CREATE TABLE evidence_artifacts (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, repo TEXT NOT NULL, commit_sha TEXT, observed_against_commit TEXT, path TEXT, start_line INTEGER, end_line INTEGER, item_id INTEGER, source_url TEXT NOT NULL, content_hash TEXT NOT NULL, fetched_at TEXT NOT NULL, payload TEXT NOT NULL)",
                    "CREATE INDEX evidence_source_idx ON evidence_artifacts(repo,commit_sha,path)",
                    "CREATE INDEX evidence_issue_idx ON evidence_artifacts(repo,item_id)",
                    "CREATE TABLE IF NOT EXISTS session_evidence (session_id TEXT NOT NULL, evidence_id TEXT NOT NULL REFERENCES evidence_artifacts(id), PRIMARY KEY(session_id,evidence_id))",
                    "CREATE TABLE audit_sessions (id TEXT PRIMARY KEY, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, turn_id TEXT, lease_owner TEXT, lease_until TEXT, pending_operation TEXT, last_tool_call_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL)",
                    "CREATE INDEX sessions_status_idx ON audit_sessions(status,updated_at)",
                    "CREATE TABLE tool_traces (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, turn_id TEXT, repo TEXT NOT NULL, commit_sha TEXT NOT NULL, tool_name TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)",
                    "CREATE INDEX traces_session_idx ON tool_traces(session_id,id)",
                    "CREATE TABLE audit_events (session_id TEXT NOT NULL, event_seq INTEGER NOT NULL, turn_id TEXT, event_type TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(session_id,event_seq))",
                    "CREATE TABLE model_calls (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT, role TEXT NOT NULL, status TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER, elapsed_ms INTEGER, created_at TEXT NOT NULL, payload TEXT NOT NULL)",
                    "CREATE INDEX model_calls_session_idx ON model_calls(session_id,created_at)",
                    "PRAGMA user_version=1"
                ]
                for statement in statements: db.execute(statement)
            if version < 2:
                db.execute("CREATE TABLE IF NOT EXISTS session_evidence (session_id TEXT NOT NULL, evidence_id TEXT NOT NULL REFERENCES evidence_artifacts(id), PRIMARY KEY(session_id,evidence_id))")
                db.execute('PRAGMA user_version=2')
            if version < 3:
                db.execute('ALTER TABLE repo_snapshots ADD COLUMN public_verified INTEGER NOT NULL DEFAULT 0')
                # Earlier versions only accepted records from the public-snapshot creator or legacy importer.
                db.execute('UPDATE repo_snapshots SET public_verified=1')
                db.execute('PRAGMA user_version=3')
            if version < 4:
                db.execute('CREATE TABLE IF NOT EXISTS harness_reports (session_id TEXT NOT NULL, version INTEGER NOT NULL, turn_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(session_id,version))')
                db.execute('CREATE TABLE IF NOT EXISTS harness_keys (key TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_hash TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS tool_receipts (session_id TEXT NOT NULL, turn_id TEXT NOT NULL, call_id TEXT NOT NULL, trace_id INTEGER NOT NULL, PRIMARY KEY(session_id,turn_id,call_id))')
                db.execute('PRAGMA user_version=4')
    def import_legacy(self):
        source = self.settings.legacy_path
        if not source.exists(): return {'status':'not_found','snapshots':0,'cache':0}
        backup = self.settings.data_dir / ('evidence.sqlite3.pre-audit-' + uuid.uuid4().hex + '.backup')
        origin = sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True)
        try:
            dst = sqlite3.connect(backup)
            try: origin.backup(dst)
            finally: dst.close()
        finally: origin.close()
        src = sqlite3.connect(f'{backup.as_uri()}?mode=ro', uri=True)
        try:
            if src.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('Legacy backup integrity check failed')
            src.row_factory = sqlite3.Row
            snapshots = list(src.execute('SELECT id,repo,sha,created_at FROM snapshots'))
            rows = list(src.execute('SELECT repo,sha,kind,path,payload,fetched_at FROM cache'))
            for row in rows:
                value = json.loads(row['payload'])
                if row['kind'] == 'blob':
                    actual = hashlib.sha256(value['text'].encode('utf-8')).hexdigest()
                    if actual != value['sha256']: raise ValueError('Legacy blob hash mismatch; import aborted')
            with self.connect() as db:
                db.executemany('INSERT OR IGNORE INTO repo_snapshots (id,repo,sha,created_at,public_verified) VALUES (?,?,?,?,1)', [tuple(r) for r in snapshots])
                db.executemany('INSERT OR IGNORE INTO file_blob_cache VALUES (?,?,?,?,?,?)', [tuple(r) for r in rows])
                for r in snapshots:
                    found=db.execute('SELECT repo,sha,created_at FROM repo_snapshots WHERE id=?',(r['id'],)).fetchone()
                    if tuple(found) != (r['repo'],r['sha'],r['created_at']): raise ValueError('Snapshot import conflict')
                for r in rows:
                    found=db.execute('SELECT payload,fetched_at FROM file_blob_cache WHERE repo=? AND sha=? AND kind=? AND path=?',tuple(r)[:4]).fetchone()
                    if tuple(found) != (r['payload'],r['fetched_at']): raise ValueError('Cache import conflict')
            return {'status':'imported','snapshots':len(snapshots),'cache':len(rows),'backup':str(backup)}
        finally: src.close()
    def put_snapshot(self, item):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO repo_snapshots (id,repo,sha,created_at,public_verified) VALUES (?,?,?,?,1)',(item['id'],item['repo'],item['sha'],item['created_at']))
    def get_snapshot(self, id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM repo_snapshots WHERE id=?',(id,)).fetchone()
        return dict(row) if row else None
    def has_public_binding(self, repo, sha):
        with self.connect() as db:
            return db.execute('SELECT 1 FROM repo_snapshots WHERE repo=? COLLATE NOCASE AND sha=? AND public_verified=1 LIMIT 1',(repo,sha)).fetchone() is not None
    def get_cache(self, repo, sha, kind, path):
        with self.connect() as db:
            row=db.execute('SELECT payload,fetched_at FROM file_blob_cache WHERE repo=? AND sha=? AND kind=? AND path=?',(repo,sha,kind,path)).fetchone()
        return (json.loads(row['payload']),row['fetched_at']) if row else None
    def put_cache(self, repo, sha, kind, path, payload, fetched_at):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO file_blob_cache VALUES (?,?,?,?,?,?)',(repo,sha,kind,path,json.dumps(payload,ensure_ascii=False),fetched_at))
    def save_evidence(self, evidence):
        item=evidence.model_dump(); payload=json.dumps(item,ensure_ascii=False,sort_keys=True)
        source=item['source_type']; content_hash=item.get('fragment_sha256') or item.get('body_sha256') or item.get('tree_sha256') or item.get('index_sha256') or item.get('metadata_sha256')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT payload FROM evidence_artifacts WHERE id=?',(item['evidence_id'],)).fetchone()
            if existing:
                previous=json.loads(existing['payload']); previous.pop('fetched_at',None)
                current=dict(item); current.pop('fetched_at',None)
                if previous != current: raise ValueError('Evidence ID collision with different content')
                return
            db.execute('INSERT INTO evidence_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(
                item['evidence_id'],source,item['repo'],item.get('commit'),item.get('observed_against_commit'),item.get('path'),item.get('start_line'),item.get('end_line'),item.get('item_id'),item['source_url'],content_hash,item['fetched_at'],payload))
    def has_outline(self, repo, sha, path, content_sha256):
        with self.connect() as db:
            rows=db.execute("SELECT payload FROM evidence_artifacts WHERE source_type='file_outline' AND repo=? AND commit_sha=? AND path=?",(repo,sha,path)).fetchall()
        return any(json.loads(row['payload']).get('content_sha256')==content_sha256 for row in rows)
    def get_evidence(self, id):
        with self.connect() as db: row=db.execute('SELECT payload FROM evidence_artifacts WHERE id=?',(id,)).fetchone()
        return json.loads(row['payload']) if row else None
