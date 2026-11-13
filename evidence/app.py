"""Local GitHub evidence API. Repository data is always treated as untrusted."""
import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Query, Request as FastAPIRequest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("EVIDENCE_DB", ROOT / ".evidence-data" / "evidence.sqlite3"))
MAX_FILE = 512 * 1024
MAX_FRAGMENT = 16 * 1024
app = FastAPI(title="GitHub evidence reader")


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, repo TEXT NOT NULL, sha TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cache (repo TEXT NOT NULL, sha TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, payload TEXT NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY (repo, sha, kind, path));
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def api_error(status, code, message):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def parse_repo(value):
    value = value.strip()
    if "://" in value:
        u = urlsplit(value)
        if u.scheme != "https" or u.netloc.lower() not in ("github.com", "www.github.com") or u.query or u.fragment:
            api_error(422, "invalid_repository", "请输入 GitHub 公开仓库地址或 owner/repo。")
        value = u.path.strip("/")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}", value) or value.endswith(".git") or value.split("/")[1] in (".", ".."):
        api_error(422, "invalid_repository", "请输入 GitHub 公开仓库地址或 owner/repo。")
    return value


def valid_path(path, allow_empty=False):
    if path == "" and allow_empty:
        return path
    if not path or path.startswith("/") or "\\" in path or any(p in ("", ".", "..") for p in path.split("/")) or any(ord(c) < 32 for c in path):
        api_error(422, "invalid_path", "路径必须是仓库内的相对路径。")
    return path


def github_json(path):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "github-hot-monitor-evidence", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    for attempt in range(3):
        try:
            with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=12) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429 or (exc.code == 403 and (exc.headers.get("X-RateLimit-Remaining") == "0" or exc.headers.get("Retry-After"))):
                api_error(429, "rate_limited", "GitHub 请求达到限额，请稍后重试或在服务端配置令牌。")
            if exc.code == 404:
                api_error(404, "github_not_found", "GitHub 仓库或对象不存在，或无法公开访问。")
            if exc.code >= 500 and attempt < 2:
                time.sleep(0.2 * (attempt + 1)); continue
            api_error(502, "github_error", f"GitHub 请求失败（HTTP {exc.code}）。")
        except (TimeoutError, URLError, OSError):
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1)); continue
            api_error(504, "github_timeout", "连接 GitHub 超时或网络不可用，请重试。")
        except (ValueError, UnicodeDecodeError):
            api_error(502, "github_response", "GitHub 返回了无法解析的数据。")


def cached(repo, sha, kind, path, fetch):
    with database() as db:
        row = db.execute("SELECT payload, fetched_at FROM cache WHERE repo=? AND sha=? AND kind=? AND path=?", (repo, sha, kind, path)).fetchone()
        if row:
            return json.loads(row["payload"]), row["fetched_at"], True
    payload = fetch()
    fetched = now()
    with database() as db:
        db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?, ?)", (repo, sha, kind, path, json.dumps(payload, ensure_ascii=False), fetched))
    return payload, fetched, False


def snapshot(id):
    with database() as db:
        row = db.execute("SELECT * FROM snapshots WHERE id=?", (id,)).fetchone()
    if not row:
        api_error(404, "snapshot_not_found", "快照不存在。")
    return dict(row)


def tree(snap, path):
    valid_path(path, allow_empty=True)
    repo, commit = snap["repo"], snap["sha"]
    obj_sha = commit
    if path:
        parent, _, name = path.rpartition("/")
        listing, _, _ = tree(snap, parent)
        entry = next((e for e in listing["entries"] if e["name"] == name and e["type"] == "tree"), None)
        if not entry:
            if listing["truncated"]:
                api_error(409, "tree_incomplete", "上级目录被截断，无法判断该目录是否存在。")
            api_error(404, "path_not_found", "目录不存在。")
        obj_sha = entry["sha"]
    def fetch():
        data = github_json(f"/repos/{repo}/git/trees/{obj_sha}")
        return {"entries": [{"name": e["path"], "type": e["type"], "sha": e["sha"], "size": e.get("size"), "mode": e.get("mode")} for e in data.get("tree", [])], "truncated": bool(data.get("truncated"))}
    return cached(repo, commit, "tree", path, fetch)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class SnapshotInput(BaseModel):
    repository: str = Field(min_length=1, max_length=250)


class SnapshotResponse(BaseModel):
    id: str
    repo: str
    sha: str
    created_at: str


class TreeEntry(BaseModel):
    name: str
    type: str
    sha: str
    size: int | None = None
    mode: str | None = None


class TreeResponse(BaseModel):
    repository: str
    commit: str
    path: str
    entries: list[TreeEntry]
    truncated: bool
    fetched_at: str
    cache_hit: bool


class FragmentResponse(BaseModel):
    repository: str
    commit: str
    path: str
    empty: bool
    start_line: int | None
    end_line: int | None
    text: str
    truncated: bool
    partial_line: bool
    fetched_at: str
    content_sha256: str
    fragment_sha256: str
    evidence_id: str
    source_url: str
    cache_hit: bool


class CapabilitiesResponse(BaseModel):
    service: str = "github-hot-monitor-evidence"
    version: str = "1.1"


ERRORS = {code: {"model": ErrorResponse} for code in (403, 404, 409, 413, 415, 416, 422, 429, 502, 504)}


@app.exception_handler(RequestValidationError)
async def validation_error(request: FastAPIRequest, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request", "message": "请求参数无效，请检查输入。"}})


@app.get("/api/capabilities", response_model=CapabilitiesResponse)
def capabilities():
    return CapabilitiesResponse()


@app.post("/api/snapshots", response_model=SnapshotResponse, responses=ERRORS)
def create_snapshot(body: SnapshotInput):
    repo = parse_repo(body.repository)
    meta = github_json(f"/repos/{repo}")
    if meta.get("private"):
        api_error(403, "private_repository", "只支持公开仓库。")
    repo = meta["full_name"]
    branch = meta["default_branch"]
    commit = github_json(f"/repos/{repo}/commits/{quote(branch, safe='')}")["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        api_error(502, "github_response", "GitHub 返回了无效的提交标识。")
    item = {"id": uuid.uuid4().hex, "repo": repo, "sha": commit, "created_at": now()}
    with database() as db:
        db.execute("INSERT INTO snapshots VALUES (:id, :repo, :sha, :created_at)", item)
    return item


@app.get("/api/snapshots/{id}/tree", response_model=TreeResponse, responses=ERRORS)
def get_tree(id: str, path: str = ""):
    snap = snapshot(id)
    data, fetched, hit = tree(snap, path)
    return {"repository": snap["repo"], "commit": snap["sha"], "path": path, **data, "fetched_at": fetched, "cache_hit": hit}


@app.get("/api/snapshots/{id}/fragment", response_model=FragmentResponse, responses=ERRORS)
def fragment(id: str, path: str, start: int = Query(1, ge=1), lines: int = Query(200, ge=1, le=200)):
    valid_path(path)
    snap = snapshot(id)
    parent, _, name = path.rpartition("/")
    listing, _, _ = tree(snap, parent)
    entry = next((e for e in listing["entries"] if e["name"] == name), None)
    if not entry:
        if listing["truncated"]:
            api_error(409, "tree_incomplete", "目录被截断，无法判断文件是否存在。")
        api_error(404, "path_not_found", "文件不存在。")
    if entry["type"] != "blob" or entry.get("mode") not in ("100644", "100755"):
        api_error(422, "not_regular_file", "请选择普通文本文件。")
    if entry.get("size") is not None and entry["size"] > MAX_FILE:
        api_error(413, "file_too_large", "文件超过 512 KiB。")
    def fetch():
        blob = github_json(f"/repos/{snap['repo']}/git/blobs/{entry['sha']}")
        if blob.get("size", 0) > MAX_FILE:
            api_error(413, "file_too_large", "文件超过 512 KiB。")
        try:
            raw = base64.b64decode(blob["content"], validate=False)
            if len(raw) > MAX_FILE:
                api_error(413, "file_too_large", "文件超过 512 KiB。")
            decoded = raw.decode("utf-8")
            if "\x00" in decoded:
                raise ValueError()
        except (KeyError, ValueError, UnicodeDecodeError, binascii.Error):
            api_error(415, "binary_file", "文件不是可读取的 UTF-8 文本。")
        return {"text": decoded, "sha256": hashlib.sha256(raw).hexdigest()}
    data, fetched, hit = cached(snap["repo"], snap["sha"], "blob", path, fetch)
    parts = data["text"].split("\n")
    all_lines = [part + "\n" for part in parts[:-1]]
    if parts[-1]: all_lines.append(parts[-1])
    if start > len(all_lines) and not (start == 1 and not all_lines):
        api_error(416, "line_out_of_range", "起始行超过文件末尾。")
    selected = []
    used = 0
    partial_line = False
    for line in all_lines[start - 1:start - 1 + lines]:
        encoded = line.encode("utf-8")
        if used + len(encoded) > MAX_FRAGMENT:
            # A single long line is truncated at a UTF-8 boundary, preserving its original prefix.
            if not selected:
                part = encoded[:MAX_FRAGMENT].decode("utf-8", errors="ignore")
                if part: selected.append(part)
                partial_line = True
            break
        selected.append(line); used += len(encoded)
    text = "".join(selected)
    empty = not all_lines
    end = start + len(selected) - 1 if selected else None
    first = start if selected else None
    truncated = text != "".join(all_lines[start - 1:])
    url = f"https://github.com/{snap['repo']}/blob/{snap['sha']}/{quote(path, safe='/')}"
    if selected: url += f"#L{start}-L{end}"
    fragment_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = {"repository": snap["repo"].lower(), "commit": snap["sha"], "path": path,
                "start_line": first, "end_line": end, "partial_line": partial_line,
                "empty": empty, "fragment_sha256": fragment_hash}
    evidence_id = "ev_" + hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"repository": snap["repo"], "commit": snap["sha"], "path": path, "empty": empty,
            "start_line": first, "end_line": end, "text": text, "truncated": truncated,
            "partial_line": partial_line, "fetched_at": fetched, "content_sha256": data["sha256"],
            "fragment_sha256": fragment_hash, "evidence_id": evidence_id, "source_url": url, "cache_hit": hit}


from evidence.agent import router as agent_router
app.include_router(agent_router)

app.mount("/", StaticFiles(directory=ROOT / "public", html=True, check_dir=False), name="site")
