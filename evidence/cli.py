"""Small IDE-facing client for the existing RepoAudit API and frozen replays."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import tomllib
from urllib.parse import urlencode, urlsplit, urlunsplit
import uuid

import httpx
from evidence.github_client import GitHubError

ROOT = Path(__file__).resolve().parents[1]
MODES = ('arch_research', 'sec_sentinel', 'deploy_readiness')
PUBLIC_WORKBENCH = 'https://billionsheep.github.io/repoaudit-agent/'


def skill_index(root=ROOT):
    text = (root / 'skills/INDEX.md').read_text(encoding='utf-8')
    blocks = re.findall(r'```json\s*\n(.*?)\n```', text, re.S)
    if len(blocks) != 1:
        raise ValueError('INDEX.md 必须有一个机器可读 JSON 契约。')
    data = json.loads(blocks[0])
    if data['schema_version'] != '1.0' or len(data['skills']) != 3 or {x['id'] for x in data['skills']} != set(MODES):
        raise ValueError('技能索引与工作流不一致。')
    for item in data['skills']:
        if item['path'] != f"{item['id']}/SKILL.md" or not (root / 'skills' / item['path']).is_file():
            raise ValueError('技能路径不存在或不属于当前目录。')
    return data


def inspect_project(project):
    """Read only bounded declarations; never load .env values or execute project code."""
    root = Path(project).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('project 必须是本机项目目录。')
    result = {'python_constraints': [], 'artifacts': [], 'environment_keys': [], 'gaps': []}
    names = ('pyproject.toml', '.python-version', 'requirements.txt', 'uv.lock', 'poetry.lock',
             'Dockerfile', 'compose.yml', 'compose.yaml', 'docker-compose.yml', 'docker-compose.yaml', '.env.example')
    for name in names:
        path = root / name
        if path.is_symlink():
            result['gaps'].append(f'{name}: 跳过符号链接')
            continue
        if not path.is_file():
            continue
        result['artifacts'].append(name)
        if name not in ('pyproject.toml', '.python-version', '.env.example'):
            continue
        if path.stat().st_size > 65536:
            result['gaps'].append(f'{name}: 超过64KiB，仅记录存在')
            continue
        try:
            text = path.read_text(encoding='utf-8')
            if name == 'pyproject.toml':
                data = tomllib.loads(text)
                values = [(data.get('project', {}).get('requires-python'), 'project.requires-python'),
                          (data.get('tool', {}).get('poetry', {}).get('dependencies', {}).get('python'), 'tool.poetry.dependencies.python')]
            elif name == '.python-version':
                values = [(text.strip(), '.python-version')]
            else:
                result['environment_keys'] = sorted(set(re.findall(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', text, re.M)))[:100]
                continue
            for value, field in values:
                if isinstance(value, str) and len(value) <= 120 and re.fullmatch(r'[0-9A-Za-z.*<>=!~^,|+\- \t]+', value):
                    result['python_constraints'].append({'value': value, 'source': name, 'field': field})
        except (ValueError, UnicodeError, OSError, AttributeError):
            result['gaps'].append(f'{name}: 无法解析声明')
    if not result['python_constraints']:
        result['gaps'].append('未识别到Python版本声明；不推断当前解释器就是部署要求。')
    return result


def workbench_url(base, **selection):
    u = urlsplit(base)
    if u.scheme not in ('http', 'https') or not u.netloc or u.username or u.password:
        raise ValueError('工作台地址须为不含凭据的 HTTP(S) URL。')
    return urlunsplit((u.scheme, u.netloc, u.path.rstrip('/') + '/', urlencode(selection), ''))


def compact(session, url, local=None):
    report = (session.get('reports') or [None])[-1]
    rows = []
    if report:
        for group in report['repositories']:
            for row in group['rows']:
                rows.append({key: row[key] for key in ('repo', 'criterion_id', 'status', 'summary', 'next_step')})
                rows[-1]['evidence_ids'] = [c['evidence_id'] for c in row['citations']]
    review = not rows or not report or session['status'] != 'COMPLETED' or any(x['status'] != 'PASS' for x in rows)
    return {'schema_version': '1.0', 'session_id': session['id'], 'status': session['status'],
            'workflow_mode': (report or session).get('workflow_mode', 'deploy_readiness'),
            'bindings': session.get('bindings', []),
            'summary': (report or {}).get('summary', ''), 'rows': rows,
            'review_required': review, 'workbench_url': url, 'review_url': url if review else None,
            'usage': session.get('usage', {}), 'local_context': local}


def request(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def run_remote(args, client):
    local = inspect_project(args.project) if getattr(args, 'project', None) else None
    if args.command == 'run':
        repos = args.repo or []
        if not 1 <= len(repos) <= 3:
            raise ValueError('run 需要1至3个 --repo。')
        from evidence.github_client import valid_repo
        normalized = []
        for repo in repos:
            if repo.startswith('https://github.com/'):
                u = urlsplit(repo)
                if u.query or u.fragment or u.username or u.password:
                    raise ValueError('请提供标准GitHub仓库URL。')
                repo = u.path.strip('/')
            normalized.append(valid_repo(repo))
        if len({r.lower() for r in normalized}) != len(normalized):
            raise ValueError('仓库不能重复。')
        presets = json.loads((ROOT / 'evidence/workflows.json').read_text())['workflows']
        query = args.query or next(x['preset'] for x in presets if x['id'] == args.workflow)
        # Local declarations are context about the caller, never target-repository evidence.
        if local:
            versions = ', '.join(x['value'] for x in local['python_constraints']) or '未知'
            query += f'\n调用方本地声明（非目标仓库证据）：Python {versions}；配置文件：' + ', '.join(local['artifacts'])
        if not 1 <= len(query) <= 1500:
            raise ValueError('组合问题须在1至1500字符内；请缩短 query。')
        health = request(client, 'GET', '/api/health')
        if not health.get('model_ready'):
            raise ValueError('本机服务尚未配置模型；请按RUNBOOK配置后启动。')
        snapshots = [request(client, 'POST', '/api/phase1/snapshots', json={'repo': r})['id'] for r in normalized]
        key = args.idempotency_key or uuid.uuid4().hex
        created = request(client, 'POST', '/api/audit/sessions', json={
            'snapshot_ids': snapshots, 'query': query, 'workflow_mode': args.workflow, 'idempotency_key': key})
        session_id = created['session_id']
    else:
        session_id = args.session
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', session_id):
        raise ValueError('会话标识无效。')
    url = workbench_url(args.base_url, session=session_id)
    deadline = time.monotonic() + args.wait
    while True:
        try:
            session = request(client, 'GET', f'/api/audit/sessions/{session_id}')
        except (httpx.HTTPError, ValueError):
            return {'schema_version': '1.0', 'session_id': session_id, 'status': 'UNAVAILABLE',
                    'review_required': True, 'workbench_url': url, 'review_url': url,
                    'error': '会话已创建或指定，暂时读取失败；请打开工作台或使用result重试，勿重新创建。'}
        result = compact(session, url, local)
        if session['status'] in ('COMPLETED', 'FAILED', 'INTERRUPTED') or time.monotonic() >= deadline:
            result['wait_expired'] = session['status'] not in ('COMPLETED', 'FAILED', 'INTERRUPTED')
            return result
        time.sleep(min(1, max(0, deadline - time.monotonic())))


def parser():
    p = argparse.ArgumentParser(description='RepoAudit：IDE工作流调用与JSON报告入口')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('skills', help='输出渐进式技能索引及输入Schema')
    inspect = sub.add_parser('inspect', help='只读探测本机声明和环境变量名称')
    inspect.add_argument('--project', default='.')
    replay = sub.add_parser('replay', help='读取一份内置录制，零模型调用')
    replay.add_argument('--replay', default='v3-architecture-gateway.json')
    replay.add_argument('--workbench-url', default=PUBLIC_WORKBENCH)
    for command in ('run', 'result'):
        cmd = sub.add_parser(command, help='启动核查' if command == 'run' else '读取已有会话')
        cmd.add_argument('--base-url', default='http://127.0.0.1:8773')
        cmd.add_argument('--wait', type=float, default=300 if command == 'run' else 0)
        if command == 'run':
            cmd.add_argument('--workflow', choices=MODES, required=True)
            cmd.add_argument('--repo', action='append', required=True)
            cmd.add_argument('--query')
            cmd.add_argument('--project')
            cmd.add_argument('--idempotency-key')
        else:
            cmd.add_argument('--session', required=True)
    return p


def main(argv=None, *, transport=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'skills':
            output = skill_index()
        elif args.command == 'inspect':
            output = inspect_project(args.project)
        elif args.command == 'replay':
            from evidence.replay import read_bundle
            name = args.replay.removeprefix('replays/')
            entries = json.loads((ROOT / 'web/replays/index.json').read_text())['replays']
            if f'replays/{name}' not in {x['path'] for x in entries}:
                raise ValueError('请选择内置回放文件名；不接受其他文件或远端地址。')
            payload = read_bundle((ROOT / 'web/replays' / name).read_bytes())
            output = compact(payload['session'], workbench_url(args.workbench_url, replay=name))
        else:
            base = urlsplit(args.base_url)
            if base.scheme != 'http' or base.hostname not in ('localhost', '127.0.0.1', '::1') or base.username or base.password or base.query or base.fragment or base.path not in ('', '/'):
                raise ValueError('base-url 须为本机HTTP服务根地址，例如 http://127.0.0.1:8773。')
            if not 0 <= args.wait <= 600:
                raise ValueError('wait 须为0至600秒。')
            with httpx.Client(base_url=args.base_url, timeout=30, follow_redirects=False, transport=transport) as client:
                output = run_remote(args, client)
        print(json.dumps(output, ensure_ascii=False, separators=(',', ':')))
        return 1 if output.get('status') == 'UNAVAILABLE' else 0
    except (OSError, ValueError, KeyError, GitHubError, httpx.HTTPError) as exc:
        # Avoid echoing URLs, request content or provider responses containing secrets.
        message = str(exc) if isinstance(exc, (ValueError, GitHubError)) else f'调用失败（{type(exc).__name__}），请确认本机服务与输入。'
        print(json.dumps({'schema_version': '1.0', 'status': 'ERROR', 'error': message}, ensure_ascii=False, separators=(',', ':')))
        return 1


if __name__ == '__main__':
    sys.exit(main())
