"""Portable, self-contained and integrity-checked public session recordings."""
import hashlib
import json
import re
from urllib.parse import quote, urlsplit
from evidence.agent import configuration
from evidence.guardrails import expected_id, sha, validate_derived
from evidence.github_client import timestamp
from evidence.harness_store import HarnessStore
from evidence.report_v3 import validate_report_extras

MAX_REPLAY_BYTES=5*1024*1024

def validate_payload(payload):
    session=payload['session']; bindings={(b['repo'].lower(),b['commit']) for b in session['bindings']}
    evidence=payload['evidence']
    if not bindings or len(bindings)>3 or not isinstance(evidence,dict): raise ValueError('invalid bindings or evidence')
    for key,e in evidence.items():
        binding=(e['repo'].lower(),e.get('commit',e.get('observed_against_commit')))
        if binding not in bindings: raise ValueError('foreign evidence')
        url=urlsplit(e['source_url']); prefix='/'+e['repo'].lower()+'/'
        if url.scheme!='https' or url.netloc.lower()!='github.com' or not (url.path.lower()+'/' if url.path.count('/')==2 else url.path.lower()).startswith(prefix): raise ValueError('invalid source URL')
        kind=e['source_type']; root=f"/{e['repo']}"
        if kind in ('file_lines','file_outline'):
            expected=f"{root}/blob/{binding[1]}/{quote(e['path'],safe='/')}"
            if url.path!=expected: raise ValueError('file URL does not match commit and path')
        if kind in ('repo_tree','arch_profile','security_scan'):
            path=e.get('path',e.get('path_prefix',''))
            expected=f"{root}/tree/{binding[1]}"+('/'+quote(path,safe='/') if path else '')
            if url.path!=expected: raise ValueError('tree URL does not match commit and path')
        if kind in ('issue','issue_comment') and url.path!=f"{root}/issues/{e['issue_number']}": raise ValueError('issue URL does not match issue')
        raw=e.get('text',e.get('body','')); digest=e.get('fragment_sha256') or e.get('body_sha256') or e.get('tree_sha256') or e.get('index_sha256') or e.get('metadata_sha256') or e.get('artifact_sha256')
        if sha(raw)!=digest or expected_id(e)!=key or e.get('evidence_id')!=key: raise ValueError('invalid evidence hash or identity')
        if kind in ('arch_profile','security_scan') and not validate_derived(e,evidence.get): raise ValueError('invalid derived evidence references')
    previous=0
    for event in session['events']:
        if not isinstance(event['id'],int) or event['id']<=previous: raise ValueError('invalid event order')
        previous=event['id']
    for report in session['reports']:
        for repo in report['repositories']:
            b=repo['binding']; binding=(b['repo'].lower(),b['commit'])
            if binding not in bindings: raise ValueError('foreign report')
            for row in repo['rows']:
                if (row['repo'].lower(),row['commit'])!=binding: raise ValueError('foreign verdict')
                for c in row['citations']:
                    e=evidence[c['evidence_id']]
                    if (e['repo'].lower(),e.get('commit',e.get('observed_against_commit')))!=binding or c['quote'] not in e.get('text',e.get('body','')): raise ValueError('invalid citation')
                inline=set(re.findall(r'\[((?:ev|iss|isc|tree|outline|meta|arch_profile|security_scan)_[^\]\s]+)\]',row['summary']))
                if inline!={c['evidence_id'] for c in row['citations']}: raise ValueError('unresolved inline citation')
        validate_report_extras(report,evidence.get)
    for trace in payload['traces']:
        binding=(trace['repo'].lower(),trace['commit'])
        if binding not in bindings: raise ValueError('foreign trace')
        for key in trace.get('evidence_ids',[]):
            e=evidence[key]
            if (e['repo'].lower(),e.get('commit',e.get('observed_against_commit')))!=binding: raise ValueError('foreign trace evidence')
    return payload

def make_bundle(db,id):
    store=HarnessStore(db); session=store.public(id); session_row,_=store.get(id)
    with db.connect() as c:
        evidence={r['id']:json.loads(r['payload']) for r in c.execute('SELECT e.id,e.payload FROM evidence_artifacts e JOIN session_evidence s ON s.evidence_id=e.id WHERE s.session_id=?',(id,))}
        traces=[{'repo':r['repo'],'commit':r['commit_sha'],'tool':r['tool_name'],'status':r['status'],'created_at':r['created_at'],**{k:v for k,v in json.loads(r['payload']).items() if k in ('args','duration_ms','evidence_ids')}} for r in c.execute('SELECT * FROM tool_traces WHERE session_id=? ORDER BY id',(id,))]
    config=configuration(); payload={'recorded_at':session_row['updated_at'],'exported_at':timestamp(),'session':session,'evidence':evidence,'traces':traces,'model':{'name':config['model'],'reasoning_effort':config['effort']}}
    validate_payload(payload)
    raw=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    bundle={'schema_version':'2.0','payload_json':raw,'sha256':sha(raw)}
    if len(json.dumps(bundle,ensure_ascii=False).encode())>MAX_REPLAY_BYTES: raise ValueError('replay too large')
    return bundle

def read_bundle(raw):
    if len(raw)>MAX_REPLAY_BYTES: raise ValueError('replay too large')
    b=json.loads(raw)
    if set(b)!={'schema_version','payload_json','sha256'} or b['schema_version'] not in ('1.0','2.0') or sha(b['payload_json'])!=b['sha256']: raise ValueError('invalid replay envelope')
    return validate_payload(json.loads(b['payload_json']))

def markdown(session,evidence=None):
    evidence=evidence or {}
    result=['# 仓库尽调报告','',f"会话：{session['id']}  ",f"状态：{session['status']}",'']
    for report in session['reports']:
        result += ['## 问题',report.get('query',''),'','## 结果']
        for repo in report.get('repositories',[]):
            b=repo['binding']; result += ['',f"### {b['repo']} @ {b['commit']}"]
            for row in repo['rows']:
                result += ['',f"- **{row['criterion_id']} · {row['status']}**：{row['summary']}",f"  - 依据：{row['verification_basis']}；需运行验证：{row['runtime_validation_required']}",f"  - 下一步：{row['next_step']}"]
                for citation in row['citations']:
                    item=evidence.get(citation['evidence_id'],{}); url=item.get('source_url',''); label=citation['evidence_id']
                    source=f'[{label}]({url})' if url else label
                    result += [f"  - {source}：`{citation['quote'].strip()}`"]
        result += ['',report.get('summary','')]
        for graph in report.get('architecture_graph') or []:
            result += ['',f"### 架构线索 · {graph['repo']}"]
            for edge in graph['edges']:
                item=(evidence or {}).get(edge['evidence_id'],{});url=item.get('source_url','')
                source=f"[{edge['path']}:{edge['start_line']}-{edge['end_line']}]({url})" if url else edge['evidence_id']
                result.append(f"- {edge['from']} —{edge['relation']}→ {edge['to']} · {source}")
        for group in report.get('security_findings') or []:
            result += ['',f"### 安全线索 · {group['repo']}"]
            for finding in group['findings']:result.append(f"- {finding['assessment']} · {finding['category']} · {finding['path']}:{finding['start_line']}-{finding['end_line']} [{finding['evidence_id']}]")
        for item in report.get('analysis_metrics') or []:
            scope=item['scope'];result += ['',f"### 扫描范围 · {item['repo']}",f"文件 {len(scope.get('files',[]))}，覆盖完整：{scope.get('complete')}；缺口：{'；'.join(scope.get('notes',[])) or '无'}"]
        for group in report.get('integration_blueprint') or []:
            b=group['blueprint'];result += ['',f"### 配置示例 · {group['repo']}",b['applicability'],'',f"```{b['format']}",b['content'],'```','',*['- '+step for step in b['verification_steps']]]
    return '\n'.join(result)+'\n'
