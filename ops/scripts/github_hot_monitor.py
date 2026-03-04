#!/usr/bin/env python3
"""GitHub hot monitor.

Features:
- Fetch candidate repositories from GitHub Search API.
- Persist snapshots locally.
- Compute star-growth velocity between snapshots.
- Rank projects by "interesting / advanced / productive" heuristics.
- Emit Markdown report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import statistics
import sys
import textwrap
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_TOPICS = [
    "ai",
    "agent",
    "developer-tools",
    "productivity",
    "llm",
    "automation",
    "infrastructure",
    "data-engineering",
]

MIN_VELOCITY_INTERVAL_DAYS = 2 / 24  # Ignore noisy growth if snapshots are too close.


@dataclass
class RepoSnapshot:
    full_name: str
    html_url: str
    description: str
    language: Optional[str]
    stars: int
    forks: int
    open_issues: int
    watchers: int
    created_at: str
    updated_at: str
    pushed_at: str
    topics: List[str]
    archived: bool

    @classmethod
    def from_api(cls, payload: Dict[str, Any]) -> "RepoSnapshot":
        return cls(
            full_name=payload.get("full_name", ""),
            html_url=payload.get("html_url", ""),
            description=(payload.get("description") or "").strip(),
            language=payload.get("language"),
            stars=int(payload.get("stargazers_count", 0)),
            forks=int(payload.get("forks_count", 0)),
            open_issues=int(payload.get("open_issues_count", 0)),
            watchers=int(payload.get("watchers_count", 0)),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            pushed_at=payload.get("pushed_at", ""),
            topics=list(payload.get("topics", []) or []),
            archived=bool(payload.get("archived", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_name": self.full_name,
            "html_url": self.html_url,
            "description": self.description,
            "language": self.language,
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "watchers": self.watchers,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pushed_at": self.pushed_at,
            "topics": self.topics,
            "archived": self.archived,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RepoSnapshot":
        return cls(
            full_name=str(payload["full_name"]),
            html_url=str(payload.get("html_url", "")),
            description=str(payload.get("description", "")),
            language=payload.get("language"),
            stars=int(payload.get("stars", 0)),
            forks=int(payload.get("forks", 0)),
            open_issues=int(payload.get("open_issues", 0)),
            watchers=int(payload.get("watchers", 0)),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            pushed_at=str(payload.get("pushed_at", "")),
            topics=list(payload.get("topics", []) or []),
            archived=bool(payload.get("archived", False)),
        )


def parse_iso8601(s: str) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_between(start_iso: str, end_iso: str) -> float:
    start = parse_iso8601(start_iso)
    end = parse_iso8601(end_iso)
    if not start or not end:
        return 0.0
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return 0.0
    return seconds / 86400.0


def recency_days(pushed_at_iso: str, now: dt.datetime) -> float:
    pushed_at = parse_iso8601(pushed_at_iso)
    if not pushed_at:
        return 365.0
    seconds = (now - pushed_at).total_seconds()
    return max(0.0, seconds / 86400.0)


class GitHubClient:
    def __init__(self, token: Optional[str], timeout: int = 20) -> None:
        self.token = token
        self.timeout = timeout

    def _request_json(self, url: str) -> Dict[str, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-hot-monitor/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)

    def search_repositories(self, query: str, per_page: int = 30) -> List[RepoSnapshot]:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": max(1, min(per_page, 100)),
            }
        )
        url = f"https://api.github.com/search/repositories?{params}"
        payload = self._request_json(url)
        items = payload.get("items", []) or []
        return [RepoSnapshot.from_api(item) for item in items]


def load_latest_snapshot(snapshot_dir: pathlib.Path) -> Tuple[Optional[str], Dict[str, RepoSnapshot]]:
    if not snapshot_dir.exists():
        return None, {}
    snapshots = sorted(snapshot_dir.glob("snapshot-*.json"))
    if not snapshots:
        return None, {}
    latest_file = snapshots[-1]
    payload = json.loads(latest_file.read_text(encoding="utf-8"))
    repos = {
        row["full_name"]: RepoSnapshot.from_dict(row)
        for row in payload.get("repos", [])
        if "full_name" in row
    }
    return payload.get("captured_at"), repos


def save_snapshot(
    snapshot_dir: pathlib.Path, captured_at: str, repos: Sequence[RepoSnapshot], queries: Sequence[str]
) -> pathlib.Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    filename = f"snapshot-{timestamp_slug(captured_at)}.json"
    snapshot_path = snapshot_dir / filename
    payload = {
        "captured_at": captured_at,
        "queries": list(queries),
        "repos": [r.to_dict() for r in repos],
    }
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_path


def dedupe_repos(repos: Sequence[RepoSnapshot]) -> List[RepoSnapshot]:
    merged: Dict[str, RepoSnapshot] = {}
    for repo in repos:
        current = merged.get(repo.full_name)
        if current is None or repo.stars > current.stars:
            merged[repo.full_name] = repo
    return list(merged.values())


def build_queries(topics: Sequence[str], days: int, min_stars: int) -> List[str]:
    created_after = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).date().isoformat()
    queries: List[str] = []
    for topic in topics:
        queries.append(f"topic:{topic} created:>{created_after} stars:>={min_stars} archived:false")
    # Broad fallback query for repositories without topic tagging.
    queries.append(f"created:>{created_after} stars:>={min_stars} archived:false")
    return queries


def velocity_stars_per_day(
    current: RepoSnapshot, previous: Optional[RepoSnapshot], days_elapsed: float
) -> float:
    if previous is None or days_elapsed < MIN_VELOCITY_INTERVAL_DAYS:
        return 0.0
    delta = current.stars - previous.stars
    if delta <= 0:
        return 0.0
    return delta / days_elapsed


def clamp_0_100(value: float) -> float:
    return max(0.0, min(100.0, value))


def safe_log10(value: float) -> float:
    if value <= 0:
        return 0.0
    return math.log10(value)


def productivity_score(repo: RepoSnapshot, now: dt.datetime) -> float:
    # Recent pushes + manageable issues vs forks indicates active maintenance.
    recency = recency_days(repo.pushed_at, now)
    recency_component = max(0.0, 45.0 - recency * 1.5)
    issue_pressure = repo.open_issues / max(1.0, repo.forks + 1.0)
    issue_component = max(0.0, 30.0 - issue_pressure * 80.0)
    popularity_component = clamp_0_100(safe_log10(repo.stars + 1.0) * 10.0)
    return clamp_0_100(recency_component + issue_component + popularity_component * 0.25)


def advanced_score(repo: RepoSnapshot) -> float:
    keywords = (
        "agent",
        "llm",
        "transformer",
        "compiler",
        "runtime",
        "distributed",
        "vector",
        "inference",
        "gpu",
        "quantization",
        "benchmark",
    )
    text = f"{repo.full_name} {repo.description} {' '.join(repo.topics)}".lower()
    keyword_hits = sum(1 for k in keywords if k in text)
    keyword_component = min(45.0, keyword_hits * 9.0)
    star_component = clamp_0_100(safe_log10(repo.stars + 1.0) * 14.0)
    fork_component = clamp_0_100(safe_log10(repo.forks + 1.0) * 20.0)
    return clamp_0_100(keyword_component + star_component * 0.5 + fork_component * 0.4)


def interesting_score(repo: RepoSnapshot, velocity: float, now: dt.datetime) -> float:
    trend_component = clamp_0_100(min(60.0, velocity * 8.0))
    freshness_component = max(0.0, 30.0 - recency_days(repo.pushed_at, now) * 0.8)
    discussion_component = clamp_0_100(safe_log10(repo.watchers + 1.0) * 25.0)
    return clamp_0_100(trend_component + freshness_component + discussion_component * 0.35)


def weighted_total(interesting: float, advanced: float, productive: float) -> float:
    return clamp_0_100(interesting * 0.45 + advanced * 0.30 + productive * 0.25)


def classify_repo(interesting: float, advanced: float, productive: float) -> str:
    axes = {
        "Trend": interesting,
        "Frontier": advanced,
        "Builder": productive,
    }
    return max(axes, key=axes.get)


def median_velocity(rows: Sequence[Dict[str, Any]]) -> float:
    values = [float(r["velocity"]) for r in rows if r["velocity"] > 0]
    if not values:
        return 0.0
    return statistics.median(values)


def top_rows(rows: Sequence[Dict[str, Any]], metric: str, top_n: int) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda r: r[metric], reverse=True)[:top_n]


def timestamp_slug(captured_at: str) -> str:
    return captured_at.replace(":", "").replace("-", "")


def build_structured_report(
    *,
    captured_at: str,
    previous_at: Optional[str],
    rows: Sequence[Dict[str, Any]],
    top_n: int,
) -> Dict[str, Any]:
    rows_total = sorted(rows, key=lambda r: r["total"], reverse=True)
    languages = sorted({(r.get("language") or "Unknown") for r in rows_total})
    return {
        "captured_at": captured_at,
        "previous_snapshot": previous_at,
        "candidate_count": len(rows_total),
        "median_velocity": median_velocity(rows_total),
        "filters": {
            "languages": languages,
        },
        "leaderboards": {
            "fastest": top_rows(rows_total, "velocity", top_n),
            "interesting": top_rows(rows_total, "interesting", top_n),
            "advanced": top_rows(rows_total, "advanced", top_n),
            "productive": top_rows(rows_total, "productive", top_n),
            "overall": top_rows(rows_total, "total", top_n),
        },
        "rows": rows_total,
    }


def format_report(
    *,
    captured_at: str,
    previous_at: Optional[str],
    rows: Sequence[Dict[str, Any]],
    top_n: int,
) -> str:
    timestamp = parse_iso8601(captured_at)
    if timestamp is None:
        readable_ts = captured_at
    else:
        readable_ts = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    previous_line = "N/A (first run)"
    if previous_at:
        prev_ts = parse_iso8601(previous_at)
        previous_line = prev_ts.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z") if prev_ts else previous_at

    fastest = top_rows(rows, "velocity", top_n)
    most_interesting = top_rows(rows, "interesting", top_n)
    most_advanced = top_rows(rows, "advanced", top_n)
    most_productive = top_rows(rows, "productive", top_n)
    total_rank = top_rows(rows, "total", top_n)

    def table(title: str, items: Sequence[Dict[str, Any]], metric: str) -> str:
        lines = [f"## {title}", "", "| Repo | Stars | Metric | Notes |", "|---|---:|---:|---|"]
        for row in items:
            notes = row["description"][:120].replace("\n", " ")
            lines.append(
                f"| [{row['full_name']}]({row['url']}) | {row['stars']} | {row[metric]:.2f} | {notes} |"
            )
        lines.append("")
        return "\n".join(lines)

    lines = [
        "# GitHub Hot Monitor Report",
        "",
        f"- Captured at: `{readable_ts}`",
        f"- Previous snapshot: `{previous_line}`",
        f"- Candidate repos: `{len(rows)}`",
        f"- Median star velocity: `{median_velocity(rows):.2f} stars/day`",
        "",
        table("Fastest Star Growth", fastest, "velocity"),
        table("Most Interesting", most_interesting, "interesting"),
        table("Most Advanced", most_advanced, "advanced"),
        table("Most Productive", most_productive, "productive"),
        table("Overall Rank", total_rank, "total"),
    ]
    return "\n".join(lines).strip() + "\n"


def collect_repositories(
    client: GitHubClient,
    queries: Sequence[str],
    per_query: int,
) -> List[RepoSnapshot]:
    all_repos: List[RepoSnapshot] = []
    for query in queries:
        try:
            repos = client.search_repositories(query, per_page=per_query)
            all_repos.extend(repos)
        except Exception as exc:  # pragma: no cover
            print(f"[warn] query failed: {query} ({exc})", file=sys.stderr)
    return dedupe_repos(all_repos)


def generate_rank_rows(
    repos: Sequence[RepoSnapshot],
    previous_map: Dict[str, RepoSnapshot],
    elapsed_days: float,
    now: dt.datetime,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for repo in repos:
        prev = previous_map.get(repo.full_name)
        velocity = velocity_stars_per_day(repo, prev, elapsed_days)
        interesting = interesting_score(repo, velocity, now)
        advanced = advanced_score(repo)
        productive = productivity_score(repo, now)
        total = weighted_total(interesting, advanced, productive)
        segment = classify_repo(interesting, advanced, productive)
        rows.append(
            {
                "full_name": repo.full_name,
                "url": repo.html_url,
                "description": repo.description or "",
                "language": repo.language or "Unknown",
                "topics": repo.topics,
                "stars": repo.stars,
                "forks": repo.forks,
                "watchers": repo.watchers,
                "open_issues": repo.open_issues,
                "created_at": repo.created_at,
                "updated_at": repo.updated_at,
                "pushed_at": repo.pushed_at,
                "velocity": velocity,
                "interesting": interesting,
                "advanced": advanced,
                "productive": productive,
                "total": total,
                "segment": segment,
            }
        )
    return rows


def parse_topics(topics_arg: Optional[str]) -> List[str]:
    if not topics_arg:
        return list(DEFAULT_TOPICS)
    parts = [x.strip() for x in topics_arg.split(",")]
    return [x for x in parts if x]


def cli(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="github_hot_monitor.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Monitor fast-rising GitHub repositories and generate rankings.

            Examples:
              python3 ops/scripts/github_hot_monitor.py scan
              python3 ops/scripts/github_hot_monitor.py scan --topics ai,agent,devtools --top 15
            """
        ),
    )
    parser.add_argument("command", choices=["scan"], help="Currently supported command")
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN", ""), help="GitHub token")
    parser.add_argument("--topics", default=None, help="Comma-separated GitHub topics")
    parser.add_argument("--query-days", type=int, default=30, help="Only search repos created in last N days")
    parser.add_argument("--min-stars", type=int, default=50, help="Minimum stars in GitHub search query")
    parser.add_argument("--per-query", type=int, default=30, help="Search result size for each query (max 100)")
    parser.add_argument("--top", type=int, default=10, help="Top N rows per leaderboard in report")
    parser.add_argument(
        "--state-dir",
        default="data",
        help="Directory for snapshots and reports (default: data)",
    )
    args = parser.parse_args(argv)

    token = args.token.strip() or None
    topics = parse_topics(args.topics)
    now = dt.datetime.now(dt.timezone.utc)
    captured_at = now.isoformat()

    state_dir = pathlib.Path(args.state_dir)
    snapshot_dir = state_dir / "snapshots"
    report_dir = state_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    previous_at, previous_map = load_latest_snapshot(snapshot_dir)
    elapsed_days = days_between(previous_at or "", captured_at) if previous_at else 0.0

    queries = build_queries(topics, days=args.query_days, min_stars=args.min_stars)
    client = GitHubClient(token=token)
    repos = collect_repositories(client, queries=queries, per_query=args.per_query)
    repos = [r for r in repos if not r.archived]

    if not repos:
        print("No repositories found. Check token, topics, or thresholds.", file=sys.stderr)
        return 2

    snapshot_path = save_snapshot(snapshot_dir, captured_at, repos, queries)
    rows = generate_rank_rows(repos, previous_map=previous_map, elapsed_days=elapsed_days, now=now)
    report = format_report(captured_at=captured_at, previous_at=previous_at, rows=rows, top_n=args.top)
    structured = build_structured_report(
        captured_at=captured_at,
        previous_at=previous_at,
        rows=rows,
        top_n=args.top,
    )
    latest_report_path = report_dir / "latest.md"
    dated_report_path = report_dir / f"report-{timestamp_slug(captured_at)}.md"
    latest_report_json_path = report_dir / "latest.json"
    dated_report_json_path = report_dir / f"report-{timestamp_slug(captured_at)}.json"
    latest_report_path.write_text(report, encoding="utf-8")
    dated_report_path.write_text(report, encoding="utf-8")
    latest_report_json_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_report_json_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Snapshot: {snapshot_path}")
    print(f"Report  : {latest_report_path}")
    print(f"JSON    : {latest_report_json_path}")
    print(f"Top repo: {max(rows, key=lambda r: r['total'])['full_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
