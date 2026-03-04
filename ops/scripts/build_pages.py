#!/usr/bin/env python3
"""Build a static site bundle for GitHub Pages."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sys
from typing import Any, Dict


def read_json(path: pathlib.Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def copy_tree_contents(src: pathlib.Path, dst: pathlib.Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Web source not found: {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, target)


def enrich_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = payload.get("rows", []) or []
    segment_counts = {"Trend": 0, "Frontier": 0, "Builder": 0}
    for row in rows:
        segment = row.get("segment")
        if segment in segment_counts:
            segment_counts[segment] += 1

    enriched = dict(payload)
    enriched["site_meta"] = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "segment_counts": segment_counts,
    }
    return enriched


def cli() -> int:
    parser = argparse.ArgumentParser(description="Build static site bundle for GitHub Pages")
    parser.add_argument("--state-dir", default="data", help="State directory containing reports/")
    parser.add_argument("--web-dir", default="web", help="Static web template directory")
    parser.add_argument("--out-dir", default="public", help="Output directory for Pages artifact")
    args = parser.parse_args()

    state_dir = pathlib.Path(args.state_dir)
    web_dir = pathlib.Path(args.web_dir)
    out_dir = pathlib.Path(args.out_dir)
    latest_json = state_dir / "reports" / "latest.json"
    latest_md = state_dir / "reports" / "latest.md"

    if not latest_json.exists():
        print(f"Missing report JSON: {latest_json}", file=sys.stderr)
        return 2

    if out_dir.exists():
        shutil.rmtree(out_dir)

    copy_tree_contents(web_dir, out_dir)
    payload = enrich_payload(read_json(latest_json))
    write_json(out_dir / "data" / "latest.json", payload)
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    if latest_md.exists():
        (out_dir / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(latest_md, out_dir / "data" / "latest.md")

    print(f"Built Pages bundle at: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
