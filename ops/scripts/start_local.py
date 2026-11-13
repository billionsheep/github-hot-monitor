#!/usr/bin/env python3
"""Build the workbench and start its local service in one command."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description='启动 RepoAudit 本地工作台')
    p.add_argument('--port',type=int,default=8773)
    args=p.parse_args()
    venv=ROOT/'.venv'/'bin'/'python'
    python=str(venv) if venv.exists() else sys.executable
    env=os.environ.copy()
    if not env.get('GITHUB_TOKEN'):
        try:
            token=subprocess.run(['gh','auth','token'],capture_output=True,text=True,timeout=5,check=True).stdout.strip()
            if token: env['GITHUB_TOKEN']=token
        except (FileNotFoundError,subprocess.SubprocessError): pass
    subprocess.run([python,str(ROOT/'ops/scripts/build_pages.py'),'--state-dir',str(ROOT/'data'),'--web-dir',str(ROOT/'web'),'--out-dir',str(ROOT/'public')],cwd=ROOT,check=True,env=env)
    print(f'工作台：http://127.0.0.1:{args.port}',flush=True)
    os.chdir(ROOT)
    os.execvpe(python,[python,'-m','uvicorn','evidence.app:app','--host','127.0.0.1','--port',str(args.port)],env)

if __name__=='__main__': main()
