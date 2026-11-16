#!/usr/bin/env python3
"""Build a commit-identifiable source/demo archive with per-file integrity records."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[2]
SECRET = re.compile(rb'(?:sk-(?:proj-)?[A-Za-z0-9_-]{30,}|gh[pousr]_[A-Za-z0-9]{30,})')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if git('status', '--porcelain'):
        raise SystemExit('先提交当前改动，再生成与版本对应的交付包。')
    commit = git('rev-parse', 'HEAD')
    if git('rev-parse', args.tag + '^{commit}') != commit:
        raise SystemExit('交付标签没有指向当前提交。')
    payloads = {}
    for name in git('ls-files').splitlines():
        if name.startswith('data/') and name not in ('data/reports/latest.json', 'data/reports/latest.md'):
            continue
        if any(part in ('.git', '.venv', '.evidence-data', '__pycache__') for part in Path(name).parts):
            raise SystemExit('运行数据意外被跟踪：' + name)
        if Path(name).name.startswith('.env') and Path(name).name != '.env.example':
            raise SystemExit('配置文件不能进入交付包：' + name)
        file = ROOT / name
        if file.is_symlink():
            raise SystemExit('交付包不收录符号链接：' + name)
        payloads[name] = file.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp) / 'site'
        subprocess.run([sys.executable, str(ROOT / 'ops/scripts/build_pages.py'), '--state-dir', str(ROOT / 'data'),
                        '--web-dir', str(ROOT / 'web'), '--out-dir', str(site)], cwd=ROOT, check=True, capture_output=True)
        for file in site.rglob('*'):
            if file.is_file(): payloads['site/' + str(file.relative_to(site))] = file.read_bytes()
    payloads['VERSION.json'] = (json.dumps({'commit': commit, 'tag': args.tag, 'product': 'RepoAudit-Agent v3',
        'source_repository': 'https://github.com/billionsheep/repoaudit-agent'}, ensure_ascii=False, indent=2) + '\n').encode()
    for name, data in payloads.items():
        if SECRET.search(data): raise SystemExit('疑似凭证，停止打包：' + name)
    manifest = {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for name, data in sorted(payloads.items())}
    payloads['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists(): raise SystemExit('目标已存在，请使用新的交付文件名。')
    with ZipFile(args.output, 'w', ZIP_DEFLATED) as out:
        for name, data in sorted(payloads.items()): out.writestr(name, data)
    with ZipFile(args.output) as check:
        if check.testzip() is not None: raise SystemExit('压缩包完整性检查失败。')
        for name, record in manifest.items():
            if hashlib.sha256(check.read(name)).hexdigest() != record['sha256']: raise SystemExit('哈希检查失败：' + name)
    print(json.dumps({'path': str(args.output.resolve()), 'commit': commit, 'tag': args.tag,
                      'files': len(payloads), 'bytes': args.output.stat().st_size}, ensure_ascii=False))

if __name__ == '__main__': main()
