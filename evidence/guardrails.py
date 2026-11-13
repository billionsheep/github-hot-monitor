"""Evidence identity, quote checks and context-scoped range deduplication."""
import hashlib
import html
import json
import re
from evidence.harness_schemas import Verdict

REF = re.compile(r'\[((?:ev|iss|isc|tree|outline|meta|arch_profile|security_scan)_[^\]\s]+)\]')

def sha(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()

def wrap_untrusted(text, evidence_id):
    safe=text.replace('&',r'\u0026').replace('<',r'\u003c').replace('>',r'\u003e')
    return '<untrusted evidence_id="'+html.escape(evidence_id,quote=True)+'">'+safe+'</untrusted>'

def missing_ranges(start,end,covered):
    covered=sorted((max(start,a),min(end,b)) for a,b in covered if b>=start and a<=end)
    result=[]; cursor=start
    for a,b in covered:
        if a>cursor: result.append((cursor,a-1))
        cursor=max(cursor,b+1)
    if cursor<=end: result.append((cursor,end))
    return result

def expected_id(e):
    source=e.get('source_type'); repo=e['repo'].lower(); commit=e.get('commit',e.get('observed_against_commit'))
    if source=='file_lines':
        identity={'repository':repo,'commit':commit,'path':e['path'],'start_line':e['start_line'],'end_line':e['end_line'],
                  'partial_line':e['partial_line'],'empty':e['start_line'] is None,'fragment_sha256':e['fragment_sha256']}
        return 'ev_'+sha(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    if source in ('issue','issue_comment'):
        return ('iss_' if source=='issue' else 'isc_')+sha(json.dumps([repo,commit,e['item_id'],e['updated_at'],e['body_sha256']],ensure_ascii=False))
    if source=='repo_tree': return 'tree_'+sha(json.dumps([repo,commit,e['path'],e['tree_sha256']],ensure_ascii=False))
    if source=='file_outline': return 'outline_'+sha(json.dumps([repo,commit,e['path'],e['content_sha256'],e['index_sha256']],ensure_ascii=False))
    if source=='repo_metadata': return 'meta_'+sha(json.dumps([repo,commit,e['metadata_sha256']],ensure_ascii=False))
    if source in ('arch_profile','security_scan'):
        return source+'_'+sha(json.dumps([repo,commit,e['rule_version'],e['path_prefix'],e['artifact_sha256']],ensure_ascii=False))
    return ''

def validate_derived(e, lookup):
    """Check the derived content, each source identity, binding and every signal range."""
    try:
        if e['source_type'] not in ('arch_profile','security_scan') or sha(e['text'])!=e['artifact_sha256'] or expected_id(e)!=e['evidence_id']: return False
        data=json.loads(e['text']);refs=e['references'];scope=data['scope']
        if (data['rule_version']!=e['rule_version'] or scope['path_prefix']!=e['path_prefix'] or data['references']!=refs or len(refs)!=len(set(refs))): return False
        if e['rule_version']!=('arch-v1' if e['source_type']=='arch_profile' else 'security-v1'): return False
        found={}
        for ref in refs:
            base=lookup(ref)
            if not base or base.get('source_type')!='file_lines' or base.get('repo','').lower()!=e['repo'].lower() or base.get('commit')!=e['commit']: return False
            if base.get('evidence_id')!=ref or expected_id(base)!=ref or sha(base['text'])!=base['fragment_sha256']: return False
            prefix=e['path_prefix'];path=base['path']
            if prefix and not path.startswith(prefix+'/'): return False
            if path not in scope['files']: return False
            found[ref]=base
        entries=data['edges' if e['source_type']=='arch_profile' else 'findings'];used=set()
        for item in entries:
            base=found.get(item['evidence_id']);used.add(item['evidence_id'])
            if not base or item['path']!=base['path'] or not isinstance(item['start_line'],int) or not isinstance(item['end_line'],int): return False
            if base['start_line'] is None or not (base['start_line']<=item['start_line']<=item['end_line']<=base['end_line']): return False
        return used==set(refs)
    except (KeyError,TypeError,ValueError,AttributeError): return False

def source_matches_blob(e,db):
    try:
        with db.connect() as conn:
            cached=conn.execute("SELECT payload FROM file_blob_cache WHERE repo=? AND sha=? AND kind='blob' AND path=?",(e['repo'],e['commit'],e['path'])).fetchone()
        blob=json.loads(cached['payload']);text=blob['text'];parts=text.split('\n');lines=[x+'\n' for x in parts[:-1]]
        if parts[-1]: lines.append(parts[-1])
        original=''.join(lines[e['start_line']-1:e['end_line']]) if e.get('start_line') else ''
        return sha(text)==e['content_sha256']==blob['sha256'] and (original.startswith(e['text']) if e.get('partial_line') else original==e['text'])
    except (KeyError,TypeError,ValueError): return False

def verify_verdict(row:Verdict, session_id, binding, db, visible_ids=None):
    invalid=[]; valid=[]
    cited={x.evidence_id for x in row.citations}; inline=set(REF.findall(row.summary))
    if cited != inline: invalid.append('正文与结构化引用不一致')
    if row.repo.lower()!=binding['repo'].lower() or row.commit!=binding['commit']: invalid.append('结论仓库或提交不匹配')
    for citation in row.citations:
        if visible_ids is not None and citation.evidence_id not in visible_ids:
            invalid.append('证据尚未加载到当前上下文'); continue
        with db.connect() as conn:
            record=conn.execute('SELECT e.payload FROM evidence_artifacts e JOIN session_evidence s ON s.evidence_id=e.id WHERE s.session_id=? AND e.id=?',(session_id,citation.evidence_id)).fetchone()
        if not record: invalid.append('证据不属于本会话'); continue
        e=json.loads(record['payload']); raw=e.get('text',e.get('body',''))
        expected=e.get('fragment_sha256') or e.get('body_sha256') or e.get('tree_sha256') or e.get('index_sha256') or e.get('metadata_sha256') or e.get('artifact_sha256')
        actual_commit=e.get('commit',e.get('observed_against_commit'))
        file_ok=True
        if e.get('source_type')=='file_lines':
            with db.connect() as conn:
                cached=conn.execute("SELECT payload FROM file_blob_cache WHERE repo=? AND sha=? AND kind='blob' AND path=?",(binding['repo'],binding['commit'],e.get('path'))).fetchone()
            try:
                blob=json.loads(cached['payload']); text=blob['text']; parts=text.split('\n'); lines=[x+'\n' for x in parts[:-1]]
                if parts[-1]: lines.append(parts[-1])
                original=''.join(lines[e['start_line']-1:e['end_line']]) if e.get('start_line') else ''
                file_ok=sha(text)==e['content_sha256']==blob['sha256'] and (original.startswith(raw) if e.get('partial_line') else original==raw)
            except (KeyError,TypeError,ValueError): file_ok=False
        elif e.get('source_type') in ('arch_profile','security_scan'):
            def lookup(ref):
                with db.connect() as conn:
                    found=conn.execute('SELECT e.payload FROM evidence_artifacts e JOIN session_evidence s ON s.evidence_id=e.id WHERE s.session_id=? AND e.id=?',(session_id,ref)).fetchone()
                base=json.loads(found['payload']) if found else None
                return base if base and source_matches_blob(base,db) else None
            file_ok=validate_derived(e,lookup)
        try: identity_ok=expected_id(e)==citation.evidence_id==e.get('evidence_id')
        except (KeyError,TypeError,ValueError): identity_ok=False
        problems=[]
        if e.get('repo','').lower()!=binding['repo'].lower() or actual_commit!=binding['commit']: problems.append('证据仓库或提交不一致')
        if not expected or sha(raw)!=expected or not file_ok or not identity_ok: problems.append('证据身份或内容哈希不一致')
        if citation.quote not in raw: problems.append('摘录与证据原文不一致')
        if problems: invalid.extend(problems); continue
        valid.append(citation)
    if row.status!='UNVERIFIED' and not row.citations: invalid.append('强判断没有证据')
    if invalid:
        return row.model_copy(update={'repo':binding['repo'],'commit':binding['commit'],'status':'UNVERIFIED',
            'summary':'引用校验未通过，需重新核对原文。','citations':[], 'verification_basis':'insufficient',
            'runtime_validation_required':True, 'next_step':'重新读取相关证据并核对引用。'}),invalid
    return row,[]
