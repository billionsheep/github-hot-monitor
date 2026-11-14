#!/usr/bin/env python3
"""Local acceptance server: every browser-triggered LLM call uses the v3 budget."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8775)
    args = parser.parse_args()
    if not os.environ.get('GITHUB_TOKEN'):
        try:
            os.environ['GITHUB_TOKEN'] = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, check=True).stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            # Public read-only GitHub API remains available with anonymous limits.
            os.environ.pop('GITHUB_TOKEN', None)
    subprocess.run([sys.executable, str(ROOT / 'ops/scripts/build_pages.py'), '--state-dir', str(ROOT / 'data'),
                    '--web-dir', str(ROOT / 'web'), '--out-dir', str(ROOT / 'public')], check=True, cwd=ROOT)
    from evidence.app import app
    from evidence.agent_harness import Harness
    import evidence.harness_api as api
    from eval.v3_budget import V3BudgetAdapter
    # Evaluation-only dependency injection; production startup remains unchanged.
    api.Harness = lambda db: Harness(db, V3BudgetAdapter('browser-live'))
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port)

if __name__ == '__main__': main()
