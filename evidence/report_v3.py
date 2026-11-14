"""Evidence-bound V3 report objects and conservative configuration validation."""
import ast
import json
import re
import tomllib
import yaml
from evidence.guardrails import expected_id, sha, validate_derived, source_matches_blob
from evidence.harness_schemas import IntegrationBlueprint, ArchitectureGraph, SecurityFindings, AnalysisMetrics, V3ReportExtensions


def config_syntax(fmt,content):
    try:
        if fmt=='python':
            # A portable configuration subset is verifiable in both Python and the static viewer.
            lines=[x.strip() for x in content.splitlines() if x.strip() and not x.lstrip().startswith('#')]
            literal=r'''(?:"(?:[^"\\]|\\[\\"nrt])*"|'(?:[^'\\]|\\[\\'nrt])*'|-?(?:0|[1-9]\d*)(?:\.\d+)?|True|False|None)'''
            if not lines or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\s*=\s*'+literal,x) for x in lines):return False
            ast.parse(content)
        elif fmt=='json':json.loads(content)
        elif fmt=='env':
            lines=[x.strip() for x in content.splitlines() if x.strip() and not x.lstrip().startswith('#')]
            env_value=r'''(?:[A-Za-z0-9_./:@%+\-]*|"[^"\\$`\r\n]*"|'[^'\r\n]*')'''
            if not lines or any(not re.fullmatch(r'(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*='+env_value,x) for x in lines):return False
        else:return False
        return True
    except (ValueError,SyntaxError,yaml.YAMLError,RecursionError):return False


def valid_citation(citation,binding,lookup):
    e=lookup(citation['evidence_id'])
    if not e or e.get('repo','').lower()!=binding['repo'].lower() or e.get('commit',e.get('observed_against_commit'))!=binding['commit']:return False
    raw=e.get('text',e.get('body',''));digest=e.get('fragment_sha256') or e.get('body_sha256') or e.get('tree_sha256') or e.get('index_sha256') or e.get('metadata_sha256') or e.get('artifact_sha256')
    try:return bool(digest and sha(raw)==digest and expected_id(e)==citation['evidence_id']==e['evidence_id'] and citation['quote'] and citation['quote'] in raw)
    except (KeyError,TypeError):return False


def valid_blueprint(blueprint,binding,lookup,visible=None):
    try:
        b=IntegrationBlueprint.model_validate(blueprint).model_dump()
        if not config_syntax(b['format'],b['content']):return False
        if not all(valid_citation(c,binding,lookup) and lookup(c['evidence_id']).get('source_type')=='file_lines' and (visible is None or c['evidence_id'] in visible and c['quote'] in visible[c['evidence_id']]) for c in b['citations']):return False
        source='\n'.join(c['quote'] for c in b['citations']);keys=[];values=[]
        if b['format']=='python':
            for node in ast.parse(b['content']).body:
                keys.append(node.targets[0].id);values.append(node.value.value)
        elif b['format']=='env':
            for line in b['content'].splitlines():
                line=line.strip()
                if not line or line.startswith('#'):continue
                key,value=line.removeprefix('export ').split('=',1);keys.append(key);values.append(value.strip('"\''))
        else:
            def collect(value):
                if isinstance(value,dict):
                    for key,child in value.items():keys.append(key);collect(child)
                elif isinstance(value,list):
                    for child in value:collect(child)
                else:values.append(value)
            collect(json.loads(b['content']))
        def supplied(value):
            if isinstance(value,str) and re.fullmatch(r'<[^<>\r\n]{1,100}>',value):return True
            token=json.dumps(value,ensure_ascii=False) if value is None or isinstance(value,bool) else str(value)
            return token in source
        def identifier_present(key):
            return isinstance(key,str) and bool(key) and bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(key)+r'(?![A-Za-z0-9_])',source))
        return all(identifier_present(k) for k in keys) and all(supplied(v) for v in values)
    except (ValueError,TypeError):return False


def visible_texts(history):
    found={}
    def walk(value):
        if isinstance(value,dict):
            if isinstance(value.get('evidence_id'),str) and isinstance(value.get('text'),str):found[value['evidence_id']]=value['text']
            for x in value.values():walk(x)
        elif isinstance(value,list):
            for x in value:walk(x)
    for item in history:
        raw=item.get('output') if item.get('type')=='function_call_output' else item.get('content') if item.get('role')=='user' else None
        if not isinstance(raw,str) or not raw.startswith('<untrusted '):continue
        try:walk(json.loads(raw[raw.index('>')+1:raw.rindex('</untrusted>')]))
        except (ValueError,TypeError):continue
    return found


def review_quotes_finding(quote,finding,evidence):
    """Require an actual, substantive part of the quote to overlap the hit lines."""
    if not isinstance(quote,str) or not quote or not evidence:return False
    raw=evidence.get('text','');start=evidence.get('start_line');end=evidence.get('end_line')
    first=finding.get('start_line');last=finding.get('end_line')
    if not all(isinstance(n,int) for n in (start,end,first,last)) or not (start<=first<=last<=end):return False
    lines=raw.splitlines(keepends=True)
    hit_start=sum(map(len,lines[:first-start]));hit_end=sum(map(len,lines[:last-start+1]))
    hit_lines=[line.strip().strip(' ,;:()[]{}') for line in lines[first-start:last-start+1]]
    pos=raw.find(quote)
    while pos>=0:
        overlap=raw[max(pos,hit_start):min(pos+len(quote),hit_end)]
        if any(line in overlap and re.search(r'[A-Za-z0-9_]{3,}|[\u4e00-\u9fff]{2,}',line) for line in hit_lines):return True
        pos=raw.find(quote,pos+1)
    return False


def validate_report_extras(report,lookup):
    V3ReportExtensions.model_validate({k:report[k] for k in ('architecture_graph','security_findings','analysis_metrics','integration_blueprint','analysis_gaps') if k in report})
    bindings={(x['binding']['repo'].lower(),x['binding']['commit']) for x in report.get('repositories',[])}
    for field,kind,bodyfield in [('architecture_graph','arch_profile','edges'),('security_findings','security_scan','findings'),('analysis_metrics',None,None)]:
        groups=report.get(field) or []
        if not isinstance(groups,list) or len(groups)>24:raise ValueError('invalid report group')
        for group in groups:
            {'architecture_graph':ArchitectureGraph,'security_findings':SecurityFindings,'analysis_metrics':AnalysisMetrics}[field].model_validate(group)
            b={'repo':group['repo'],'commit':group['commit']}
            if (b['repo'].lower(),b['commit']) not in bindings:raise ValueError('foreign report group')
            e=lookup(group['artifact_id'])
            if not e or e['repo'].lower()!=b['repo'].lower() or e['commit']!=b['commit'] or (kind and e['source_type']!=kind) or e['source_type'] not in ('arch_profile','security_scan') or not validate_derived(e,lookup):raise ValueError('invalid derived report source')
            data=json.loads(e['text'])
            if field=='analysis_metrics':
                if group['scope']!=data['scope']:raise ValueError('metrics do not match scan scope')
            elif field=='architecture_graph':
                if group['edges']!=data['edges']:raise ValueError('graph edges do not match scan')
            else:
                original=data['findings'];items=group['findings']
                if len(items)!=len(original):raise ValueError('finding count mismatch')
                for item,source in zip(items,original):
                    candidate=dict(item);review=candidate.pop('review',None)
                    if candidate.get('assessment')=='context_reviewed':
                        candidate['assessment']=source['assessment']
                        if not review or len(review.get('explanation',''))<10 or not valid_citation({'evidence_id':source['evidence_id'],'quote':review.get('quote','')},b,lookup) or not review_quotes_finding(review.get('quote',''),source,lookup(source['evidence_id'])):raise ValueError('review lacks source support')
                    elif review is not None:raise ValueError('review status mismatch')
                    if candidate!=source:raise ValueError('finding does not match scan')
    for group in report.get('integration_blueprint') or []:
        if set(group)!={'repo','commit','blueprint'}:raise ValueError('invalid blueprint group')
        b={'repo':group['repo'],'commit':group['commit']}
        if (b['repo'].lower(),b['commit']) not in bindings:raise ValueError('foreign blueprint')
        if not valid_blueprint(group['blueprint'],b,lookup):raise ValueError('invalid blueprint')
    return True


def collect_report_extras(db,session_id,turn_id,summaries):
    with db.connect() as c:
        items=[json.loads(r['payload']) for r in c.execute('SELECT payload FROM tool_traces WHERE session_id=? AND turn_id=? AND tool_name IN (?,?) ORDER BY id',(session_id,turn_id,'analyze_architecture_profile','scan_security_and_risk_sinks'))]
        rows=c.execute('SELECT e.id,e.payload FROM evidence_artifacts e JOIN session_evidence s ON s.evidence_id=e.id WHERE s.session_id=?',(session_id,)).fetchall()
    pool={r['id']:json.loads(r['payload']) for r in rows}
    def source(id):
        e=pool.get(id)
        return e if e and (e.get('source_type')!='file_lines' or source_matches_blob(e,db)) else None
    graph=[];security=[];metrics=[];warnings=[];seen=set()
    reviews={(x['binding']['repo'].lower(),x['binding']['commit']):x.get('security_reviews',[]) for x in summaries}
    for trace in items:
        for e in trace.get('result',{}).get('evidence',[]):
            if e.get('source_type') not in ('arch_profile','security_scan') or e['evidence_id'] in seen:continue
            artifact=source(e['evidence_id'])
            if not artifact or not validate_derived(artifact,source):warnings.append('扫描产物或底层证据校验失败，已排除。');continue
            seen.add(e['evidence_id']);data=json.loads(artifact['text']);group={'repo':artifact['repo'],'commit':artifact['commit'],'artifact_id':artifact['evidence_id']}
            metrics.append({**group,'scope':data['scope']})
            if e['source_type']=='arch_profile':graph.append({**group,'edges':data['edges']})
            else:
                findings=[]
                for finding in data['findings']:
                    out=dict(finding)
                    for review in reviews.get((e['repo'].lower(),e['commit']),[]):
                        if (review['evidence_id'],review['path'],review['start_line'],review['end_line'])==(finding['evidence_id'],finding['path'],finding['start_line'],finding['end_line']):
                            if valid_citation({'evidence_id':review['evidence_id'],'quote':review['quote']},group,source) and review_quotes_finding(review['quote'],finding,source(review['evidence_id'])):
                                out['assessment']='context_reviewed';out['review']={'quote':review['quote'],'explanation':review['explanation']}
                            break
                    findings.append(out)
                security.append({**group,'findings':findings})
    blueprints=[]
    for item in summaries:
        if item.get('integration_blueprint'):blueprints.append({**item['binding'],'blueprint':item['integration_blueprint']})
        requested=item.get('requested_outputs',[]);repo=item['binding']['repo'];commit=item['binding']['commit']
        if 'integration_blueprint' in requested and not item.get('integration_blueprint'):
            warnings.append(f'{repo}：请求的配置示例未生成，现有来源或结果不足以形成可引用示例。')
        if 'security_reviews' in requested and not any(g['repo'].lower()==repo.lower() and g['commit']==commit and any(f.get('review') for f in g['findings']) for g in security):
            warnings.append(f'{repo}：请求的安全线索上下文复核未形成可引用结果，请继续核对命中原文。')
    return {'architecture_graph':graph,'security_findings':security,'analysis_metrics':metrics,'integration_blueprint':blueprints,'analysis_gaps':warnings}
