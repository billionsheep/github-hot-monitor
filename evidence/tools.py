"""Six read-only evidence tools; results report facts, coverage and source identity."""
import ast
import asyncio
import hashlib
import json
import re
import tomllib
from urllib.parse import quote
import yaml
from pydantic import ValidationError
from evidence.github_client import GitHubClient, GitHubError
from evidence.schemas import Binding, OverviewInput, PathInput, OutlineInput, ScanInput, SecurityScanInput, LinesInput, IssueInput, FileEvidence, IssueEvidence, TreeEvidence, OutlineEvidence, MetadataEvidence, DerivedEvidence, Coverage, ToolError, ToolResult
from evidence.analysis_v3 import python_index, scan_files, python_signals, rule_signals, file_category
from evidence.github_client import timestamp


def digest(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()
def lines_of(text):
    parts=text.split('\n'); out=[p+'\n' for p in parts[:-1]]
    if parts[-1]: out.append(parts[-1])
    return out

def evidence_from_scanned_file(repo,commit,file,start,end,max_chars=6000):
    """Build a normal file fragment from bytes already counted by the scanner."""
    rows=lines_of(file['text']);selected=[];count=0;partial=False
    for line in rows[start-1:min(end,start+119,len(rows))]:
        if count+len(line)>max_chars:
            if not selected: selected.append(line[:max_chars]);partial=True
            break
        selected.append(line);count+=len(line)
    if not selected:return None
    first=start;last=start+len(selected)-1;text=''.join(selected);frag_hash=digest(text)
    identity={'repository':repo.lower(),'commit':commit,'path':file['path'],'start_line':first,'end_line':last,'partial_line':partial,'empty':False,'fragment_sha256':frag_hash}
    eid='ev_'+digest(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    url=f'https://github.com/{repo}/blob/{commit}/{quote(file["path"],safe="/")}#L{first}-L{last}'
    return FileEvidence(evidence_id=eid,repo=repo,commit=commit,path=file['path'],start_line=first,end_line=last,text=text,content_sha256=file['sha256'],fragment_sha256=frag_hash,source_url=url,fetched_at=file['fetched_at'],partial_line=partial)

def error(tool,repo,commit,exc):
    if isinstance(exc,GitHubError): code,message=exc.code,exc.message
    elif isinstance(exc,ValidationError): code,message='invalid_input','参数不符合工具契约。'
    else: code,message='invalid_input',str(exc)
    return ToolResult(tool=tool,repo=repo,commit=commit,coverage=Coverage(complete=False,notes=[message]),errors=[ToolError(code=code,message=message)])

def json_positions(text):
    """Map JSON paths to the exact start of the parsed value, including compact JSON."""
    decoder=json.JSONDecoder(); positions={}; length=len(text)
    def ws(i):
        while i<length and text[i] in ' \t\r\n': i+=1
        return i
    def parse(i,path):
        i=ws(i); start=i
        if text[i]=='{':
            obj={}; i=ws(i+1)
            while i<length and text[i]!='}':
                key_start=i
                key,end=decoder.raw_decode(text,i)
                if not isinstance(key,str): raise ValueError('invalid JSON key')
                i=ws(end)
                if text[i]!=':': raise ValueError('invalid JSON object')
                value,i=parse(i+1,path+(key,)); obj[key]=value
                entry=positions[path+(key,)]
                positions[path+(key,)]=(entry[0],text.count('\n',0,key_start)+1,entry[2])
                i=ws(i)
                if text[i]==',': i=ws(i+1)
                elif text[i]!='}': raise ValueError('invalid JSON object')
            result=obj; i+=1
        elif text[i]=='[':
            result=[]; i=ws(i+1)
            while i<length and text[i]!=']':
                value,i=parse(i,path+(str(len(result)),)); result.append(value); i=ws(i)
                if text[i]==',': i=ws(i+1)
                elif text[i]!=']': raise ValueError('invalid JSON array')
            i+=1
        else:
            result,i=decoder.raw_decode(text,i)
        positions[path]=(result,text.count('\n',0,start)+1,text.count('\n',0,max(start,i-1))+1)
        return result,i
    value,end=parse(0,())
    if ws(end)!=length: raise ValueError('trailing JSON')
    return value,positions


def structured_values(path, text, parsed):
    """Return parsed scalar declarations only when a precise source line is known."""
    base=path.rsplit('/',1)[-1].lower(); rows=lines_of(text); found=[]
    def add(key,value,line,end=None):
        if isinstance(value,(str,int,float,bool)) and value is not None: found.append((str(key),str(value),line,end or line))
    def toml_scalar(table,key,expected):
        section=''
        for i,line in enumerate(rows,1):
            head=re.match(r'^\s*\[([^\[\]]+)\]\s*(?:#.*)?$',line)
            if head: section=head.group(1).strip(); continue
            if section!=table: continue
            match=re.match(r'^\s*'+re.escape(key)+r'\s*=\s*(.*?)\s*$',line)
            if not match: continue
            try: value=tomllib.loads('value='+match.group(1))['value']
            except (ValueError,tomllib.TOMLDecodeError): continue
            if value==expected: return i
        return None
    if base=='.python-version':
        for i,line in enumerate(rows,1):
            if line.strip() and not line.lstrip().startswith('#'): add('python.version',line.strip(),i); break
    if base=='dockerfile' or base.startswith('dockerfile.'):
        for i,line in enumerate(rows,1):
            m=re.match(r'^\s*(FROM|EXPOSE|ARG|ENV|WORKDIR|CMD|ENTRYPOINT)\s+(.+?)\s*$',line,re.I)
            if m: add('docker.'+m.group(1).upper(),m.group(2),i)
    if base=='pyproject.toml' and isinstance(parsed,dict):
        project=parsed.get('project',{}) if isinstance(parsed.get('project',{}),dict) else {}
        expected=project.get('requires-python')
        if isinstance(expected,str):
            line=toml_scalar('project','requires-python',expected)
            if line: add('project.requires-python',expected,line)
        poetry=parsed.get('tool',{}).get('poetry',{}) if isinstance(parsed.get('tool',{}),dict) else {}
        deps=poetry.get('dependencies',{}) if isinstance(poetry,dict) else {}
        if isinstance(deps,dict):
            for key,value in deps.items():
                if isinstance(value,(str,int,float,bool)):
                    line=toml_scalar('tool.poetry.dependencies',key,value)
                    if line: add('tool.poetry.dependencies.'+key,value,line)
    if base in ('package.json','package-lock.json','npm-shrinkwrap.json') and isinstance(parsed,dict):
        _,positions=json_positions(text)
        prefix=() if base=='package.json' else ('packages','')
        for section in ('engines','dependencies','devDependencies','peerDependencies','optionalDependencies'):
            section_item=positions.get(prefix+(section,))
            if not section_item or not isinstance(section_item[0],dict): continue
            for key in section_item[0]:
                item=positions.get(prefix+(section,key))
                if item: add(section+'.'+key,item[0],item[1],item[2])
    if base.startswith('requirements') and base.endswith('.txt'):
        for i,line in enumerate(rows,1):
            t=line.strip()
            if t and not t.startswith('#'): add('requirement',t,i)
    if base.endswith(('.yml','.yaml')):
        node=yaml.compose(text,Loader=yaml.SafeLoader); seen_nodes=set()
        def walk(n,prefix=''):
            if id(n) in seen_nodes: return
            seen_nodes.add(id(n))
            if isinstance(n,yaml.MappingNode):
                for key,value in n.value:
                    if not isinstance(key,yaml.ScalarNode): continue
                    name=key.value; location=prefix+'.'+name if prefix else name
                    if isinstance(value,yaml.ScalarNode) and name in ('image','build','context','dockerfile','target','published','protocol','restart','command','python-version','env_file','specifier','version'):
                        add(location,value.value,key.start_mark.line+1,value.end_mark.line+1)
                    if name=='environment' and isinstance(value,yaml.MappingNode):
                        for envkey,envval in value.value:
                            if isinstance(envkey,yaml.ScalarNode) and isinstance(envval,yaml.ScalarNode): add(location+'.'+envkey.value,envval.value,envkey.start_mark.line+1,envval.end_mark.line+1)
                    if name in ('ports','environment','env_file') and isinstance(value,yaml.SequenceNode):
                        for child in value.value:
                            if isinstance(child,yaml.ScalarNode): add(location,child.value,child.start_mark.line+1)
                    walk(value,location)
            elif isinstance(n,yaml.SequenceNode):
                for child in n.value: walk(child,prefix)
        if node: walk(node)
    return found

class AuditTools:
    def __init__(self, binding, client=None):
        self.binding=Binding.model_validate(binding); self.client=client or GitHubClient()
    def check(self, data, cls):
        value=cls.model_validate(data)
        if value.repo.lower()!=self.binding.repo.lower() or value.commit!=self.binding.commit: raise GitHubError('binding_mismatch','请求仓库或提交与绑定对象不一致。')
        return value
    async def close(self): await self.client.close()
    async def get_repo_overview_and_tree(self, data):
        name='get_repo_overview_and_tree'; repo=self.binding.repo; sha=self.binding.commit
        try:
            req=self.check(data,OverviewInput); root,fetched,hit=await self.client.tree(repo,sha,req.path); metadata,observed=await self.client.metadata(repo)
            meta_text=json.dumps(metadata,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            meta_hash=digest(meta_text); meta_id='meta_'+digest(json.dumps([repo.lower(),sha,meta_hash],ensure_ascii=False))
            meta_ev=MetadataEvidence(evidence_id=meta_id,repo=repo,observed_against_commit=sha,text=meta_text,metadata_sha256=meta_hash,source_url=f'https://github.com/{repo}',fetched_at=observed)
            await asyncio.to_thread(self.client.db.save_evidence,meta_ev)
            meta_ev=MetadataEvidence.model_validate(await asyncio.to_thread(self.client.db.get_evidence,meta_id))
            facts=[{'kind':'metadata','observed_at':meta_ev.fetched_at,'data':metadata,'evidence_id':meta_id}]; evidence=[meta_ev]; notes=[]; inspected=[]; total=0
            async def add_tree(path,listing,when):
                nonlocal total
                filtered=[e for e in listing['entries'] if e['name'] not in ('.git','node_modules','__pycache__','.venv','vendor')]
                limited=filtered[:max(0,200-total)]; total+=len(limited)
                incomplete=listing['truncated'] or len(limited)<len(filtered)
                if incomplete: notes.append(f'{path or "/"} 目录不完整；可进入该目录继续浏览。')
                tree_text=json.dumps({'entries':limited,'truncated':incomplete},ensure_ascii=False,sort_keys=True,separators=(',',':'))
                tree_hash=digest(tree_text); eid='tree_'+digest(json.dumps([repo.lower(),sha,path,tree_hash],ensure_ascii=False))
                ev=TreeEvidence(evidence_id=eid,repo=repo,commit=sha,path=path,text=tree_text,tree_sha256=tree_hash,source_url=f'https://github.com/{repo}/tree/{sha}'+('/'+quote(path,safe='/') if path else ''),fetched_at=when)
                await asyncio.to_thread(self.client.db.save_evidence,ev); evidence.append(ev); inspected.append(path or '/')
                facts.append({'kind':'tree','path':path,'entries':limited,'fetched_at':when,'evidence_id':eid})
                return filtered
            filtered=await add_tree(req.path,root,fetched)
            dirs=[x for x in filtered if x['type']=='tree']
            if len(dirs)>8: notes.append('子目录超过 8 个；其余可按目录继续浏览。')
            for item in dirs[:8]:
                path=f'{req.path}/{item["name"]}' if req.path else item['name']
                try:
                    listing,when,child_hit=await self.client.tree(repo,sha,path);hit=hit and child_hit
                    await add_tree(path,listing,when)
                except GitHubError as exc: notes.append(f'{path}: {exc.message}')
            return ToolResult(tool=name,repo=repo,commit=sha,facts=facts,evidence=evidence,coverage=Coverage(complete=not notes,truncated=bool(notes),inspected=inspected,notes=notes,continuation='指定 path 继续浏览' if notes else None),cache_hit=hit)
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,sha,exc)
    async def read_file_lines(self,data):
        return await self._read_file_lines(data,False)
    async def _read_file_lines(self,data,allow_unindexed):
        name='read_file_lines'; repo=self.binding.repo; sha=self.binding.commit
        try:
            req=self.check(data,LinesInput); blob,fetched,hit=await self.client.file(repo,sha,req.path); all_lines=lines_of(blob['text'])
            if len(all_lines)>150 and not allow_unindexed and not await asyncio.to_thread(self.client.db.has_outline,repo,sha,req.path,blob['sha256']):
                raise GitHubError('outline_required','文件超过 150 行，请先读取大纲。')
            if not all_lines:
                if req.start_line!=1: raise GitHubError('line_out_of_range','起始行超过文件末尾。')
                selected=[]; partial=False; truncated=False; first=last=None
            else:
                if req.start_line>len(all_lines): raise GitHubError('line_out_of_range','起始行超过文件末尾。')
                selected=[]; count=0; partial=False
                limit=min(req.end_line,req.start_line+self.client.settings.max_fragment_lines-1,len(all_lines))
                for line in all_lines[req.start_line-1:limit]:
                    if count+len(line)>self.client.settings.max_fragment_chars:
                        if not selected: selected.append(line[:self.client.settings.max_fragment_chars]); partial=True
                        break
                    selected.append(line); count+=len(line)
                first=req.start_line; last=first+len(selected)-1
                truncated=partial or last<min(req.end_line,len(all_lines)) or req.end_line>len(all_lines)
            text=''.join(selected); frag_hash=digest(text)
            identity={'repository':repo.lower(),'commit':sha,'path':req.path,'start_line':first,'end_line':last,'partial_line':partial,'empty':not all_lines,'fragment_sha256':frag_hash}
            eid='ev_'+digest(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')))
            url=f'https://github.com/{repo}/blob/{sha}/{quote(req.path,safe="/")}' + (f'#L{first}-L{last}' if first is not None else '')
            evidence=FileEvidence(evidence_id=eid,repo=repo,commit=sha,path=req.path,start_line=first,end_line=last,text=text,content_sha256=blob['sha256'],fragment_sha256=frag_hash,source_url=url,fetched_at=fetched,partial_line=partial)
            await asyncio.to_thread(self.client.db.save_evidence,evidence)
            notes=[]
            if partial: notes.append('单行超过字符上限，仅返回前缀；请查来源。')
            elif truncated: notes.append('片段范围被限制或超过文件末尾。')
            return ToolResult(tool=name,repo=repo,commit=sha,evidence=[evidence],facts=[{'kind':'empty_file','value':not all_lines}],coverage=Coverage(complete=not truncated,truncated=truncated,inspected=[req.path],notes=notes,continuation=f'{req.path}:{last+1}' if truncated and not partial and last is not None and last<len(all_lines) else None),cache_hit=hit)
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,sha,exc)
    async def get_markdown_outline(self,data):
        name='get_markdown_outline'; repo=self.binding.repo; sha=self.binding.commit
        try:
            req=self.check(data,OutlineInput); blob,fetched,hit=await self.client.file(repo,sha,req.path); rows=lines_of(blob['text']); entries=[]; mode='line_blocks'; notes=[]
            if req.path.lower().endswith(('.md','.markdown')):
                mode='markdown_headings'; fence=None
                for i,line in enumerate(rows,1):
                    m=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
                    if m:
                        marker=m.group(1)
                        if fence is None: fence=(marker[0],len(marker))
                        elif marker[0]==fence[0] and len(marker)>=fence[1] and re.fullmatch(r'\s*',line[m.end():]): fence=None
                        continue
                    if fence: continue
                    h=re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$',line.rstrip('\r\n'))
                    if h:
                        title=h.group(2)
                        if len(title)>300: title=title[:300]; notes.append(f'第 {i} 行标题索引已截断。')
                        entries.append({'title':title,'level':len(h.group(1)),'start_line':i})
                for idx,item in enumerate(entries):
                    item['end_line']=next((x['start_line']-1 for x in entries[idx+1:] if x['level']<=item['level']),len(rows))
            elif req.path.lower().endswith('.py'):
                mode='python_ast'
                try:
                    _,entries,_,_=python_index(blob['text'])
                    if any(e.get('calls_truncated') for e in entries): notes.append('函数或类内调用摘要超过 60 项；独立调用索引仍可按提示检索。')
                except SyntaxError:
                    mode='line_blocks'; notes.append('Python 语法解析失败，改用行块索引。')
            if mode=='markdown_headings' and not entries and rows:
                mode='line_blocks'; notes.append('没有 Markdown 标题，使用行块索引。')
            if mode=='line_blocks': entries=[{'start_line':i,'end_line':min(i+49,len(rows))} for i in range(1,len(rows)+1,50)]
            if req.symbol_or_param_hint:
                hint=req.symbol_or_param_hint.casefold()
                entries=sorted(entries,key=lambda e:(hint not in json.dumps(e,ensure_ascii=False).casefold(),0 if e.get('kind') in ('Call','Assign','AnnAssign','AugAssign','Return') else 1,e['start_line']))
            limited=entries[:120]; truncated=len(entries)>len(limited)
            if truncated: notes.append('索引超过 120 项，仅展示前 120 项。')
            index_text=json.dumps({'kind':mode,'entries':limited},ensure_ascii=False,sort_keys=True,separators=(',',':'))
            index_hash=digest(index_text); eid='outline_'+digest(json.dumps([repo.lower(),sha,req.path,blob['sha256'],index_hash],ensure_ascii=False))
            evidence=OutlineEvidence(evidence_id=eid,repo=repo,commit=sha,path=req.path,text=index_text,content_sha256=blob['sha256'],index_sha256=index_hash,source_url=f'https://github.com/{repo}/blob/{sha}/{quote(req.path,safe="/")}',fetched_at=fetched)
            await asyncio.to_thread(self.client.db.save_evidence,evidence)
            return ToolResult(tool=name,repo=repo,commit=sha,evidence=[evidence],facts=[{'kind':mode,'path':req.path,'total_lines':len(rows),'entries':limited,'content_sha256':blob['sha256'],'evidence_id':eid}],coverage=Coverage(complete=not truncated and not notes,truncated=truncated,inspected=[req.path],notes=notes,continuation=f'{req.path}:{limited[-1]["start_line"]+1}' if truncated and limited else None),cache_hit=hit)
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,sha,exc)
    async def candidates(self,kind):
        repo=self.binding.repo; sha=self.binding.commit; found=[]; notes=[]; seen=[]; hits=[]
        root,_,hit=await self.client.tree(repo,sha,''); hits.append(hit); seen.append('/')
        if root['truncated']: notes.append('根目录截断，结果不完整。')
        dirs=['']+[e['name'] for e in root['entries'] if e['type']=='tree' and e['name'] in ('.github','docker','deploy','config','requirements')][:4]
        if '.github' in dirs:
            listing,_,hit=await self.client.tree(repo,sha,'.github');hits.append(hit);seen.append('.github')
            if listing['truncated']: notes.append('.github 目录截断。')
            dirs.remove('.github')
            if any(e['name']=='workflows' and e['type']=='tree' for e in listing['entries']): dirs.append('.github/workflows')
        for directory in dirs:
            if directory=='': listing=root
            else:
                try: listing,_,hit=await self.client.tree(repo,sha,directory); hits.append(hit); seen.append(directory)
                except GitHubError as e: notes.append(f'{directory}: {e.message}');continue
                if listing['truncated']: notes.append(f'{directory} 目录截断。')
            for e in listing['entries']:
                if e['type']!='blob': continue
                name=e['name']; path=f'{directory}/{name}' if directory else name
                if kind=='dependencies': matches=bool(re.match(r'^(pyproject\.toml|requirements.*\.txt|setup\.py|setup\.cfg|package\.json|package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|Pipfile(?:\.lock)?|\.python-version|go\.(?:mod|sum)|Cargo\.(?:toml|lock))$',name,re.I))
                else: matches=bool(re.match(r'^(Dockerfile(?:\..*)?|(?:docker-)?compose[^/]*\.ya?ml|\.env\.example|Makefile)$',name,re.I) or (directory=='.github/workflows' and name.endswith(('.yml','.yaml'))))
                if matches: found.append(path)
        if len(found)>self.client.settings.max_files: notes.append('相关文件超过 8 个，仅处理前 8 个。')
        return found[:self.client.settings.max_files],notes,seen,all(hits)
    async def inspect_dependencies_and_env(self,data): return await self._aggregate(data,'dependencies')
    async def inspect_deployment_artifacts(self,data): return await self._aggregate(data,'deployment')
    async def _aggregate(self,data,kind):
        name='inspect_dependencies_and_env' if kind=='dependencies' else 'inspect_deployment_artifacts'; repo=self.binding.repo; sha=self.binding.commit
        try:
            self.check(data,Binding); files,notes,inspected,hit=await self.candidates(kind); facts=[]; evidence=[]; errors=[]
            output_chars=0
            for path in files:
                try:
                    blob,_,file_hit=await self.client.file(repo,sha,path); hit=hit and file_hit; text=blob['text']; rows=lines_of(text); base=path.rsplit('/',1)[-1].lower()
                    parsed=None; status='parsed'
                    try:
                        if base in ('pyproject.toml','cargo.toml','cargo.lock','poetry.lock','pipfile'): parsed=tomllib.loads(text)
                        elif base in ('package.json','package-lock.json','npm-shrinkwrap.json','pipfile.lock'): parsed=json.loads(text)
                        elif base.endswith(('.yml','.yaml')): parsed=yaml.safe_load(text)
                        elif base in ('setup.py','makefile'): status='dynamic_not_executed'
                        elif base in ('yarn.lock','go.sum'): status='line_index_only'
                    except (ValueError,tomllib.TOMLDecodeError,yaml.YAMLError): status='parse_error'; notes.append(f'{path} 解析失败。')
                    if status in ('dynamic_not_executed','line_index_only'): notes.append(f'{path}: {status}。')
                    pattern=(r'(?i)(requires-python|python_requires|python-version|python[><=~!]|\b(?:openai|ollama|litellm|langchain|fastapi|torch|numpy|postgres|redis|milvus|sqlalchemy)\b|^\s*(?:name|version|dependencies|devDependencies)\s*[:=])' if kind=='dependencies' else r'(?i)(^\s*(?:FROM|EXPOSE|ARG|ENV|ENTRYPOINT|CMD|WORKDIR)\b|^\s*(?:image|build|ports|environment|env_file|services|depends_on|python-version|uses|run)\s*:|\$\{[A-Za-z_][A-Za-z0-9_]*|^\s*[A-Z_][A-Z0-9_]*\s*=)')
                    structured=structured_values(path,text,parsed) if status=='parsed' else []
                    if len(structured)>12: notes.append(f'{path} 结构化声明只返回前 12 项。')
                    structured=structured[:12]
                    for key,value,line_no,end_no in structured:
                        part=await self._read_file_lines({'repo':repo,'commit':sha,'path':path,'start_line':line_no,'end_line':end_no},True)
                        if part.errors: errors.extend(part.errors); notes.append(f'{path}:{line_no} 读取失败。'); continue
                        if part.coverage.truncated or part.evidence[0].partial_line:
                            notes.append(f'{path}:{line_no} 证据范围过长，未返回结构化值。'); continue
                        if output_chars+len(part.evidence[0].text)+len(value)>12000: notes.append('聚合结果达到 12000 字符上限。'); break
                        output_chars+=len(part.evidence[0].text)+len(value); evidence.extend(part.evidence)
                        facts.append({'kind':'config_value','path':path,'key':key,'value':value,'line':line_no,'evidence_id':part.evidence[0].evidence_id})
                    matching=[i for i,line in enumerate(rows,1) if re.search(pattern,line)]
                    if kind=='dependencies' and (base.startswith('requirements') or base in ('.python-version','go.mod','setup.cfg')):
                        matching=sorted(set(matching+[i for i,line in enumerate(rows,1) if line.strip() and not line.lstrip().startswith('#')]))
                    if kind=='dependencies' and base=='package.json' and isinstance(parsed,dict):
                        names=set()
                        for section in ('dependencies','devDependencies','peerDependencies','optionalDependencies','engines'):
                            value=parsed.get(section,{})
                            if isinstance(value,dict): names.update(value)
                        matching=sorted(set(matching+[i for i,line in enumerate(rows,1) if any(re.search(r'"'+re.escape(n)+r'"\s*:',line) for n in names)]))
                    if kind=='deployment' and isinstance(parsed,dict) and isinstance(parsed.get('services'),dict):
                        service_names=parsed['services'].keys()
                        matching=sorted(set(matching+[i for i,line in enumerate(rows,1) if any(re.match(r'^\s*'+re.escape(n)+r'\s*:',line) for n in service_names)]))
                    # Bound facts and evidence per file; their values are original lines.
                    if len(matching)>12: notes.append(f'{path} 只返回前 12 条匹配行。'); matching=matching[:12]
                    facts.append({'kind':'file_parse','path':path,'format':base,'status':status,'line_count':len(rows),'parsed_type':type(parsed).__name__ if parsed is not None else None})
                    for line_no in matching:
                        part=await self._read_file_lines({'repo':repo,'commit':sha,'path':path,'start_line':line_no,'end_line':line_no},True)
                        if part.errors: errors.extend(part.errors); notes.append(f'{path}:{line_no} 读取失败。'); continue
                        if output_chars+len(part.evidence[0].text)>12000:
                            notes.append('聚合结果达到 12000 字符上限，后续匹配行未返回。'); break
                        output_chars+=len(part.evidence[0].text)
                        evidence.extend(part.evidence)
                        facts.append({'kind':'declaration_line' if kind=='dependencies' else 'deployment_line','path':path,'line':line_no,'value':part.evidence[0].text,'evidence_id':part.evidence[0].evidence_id})
                        if part.coverage.truncated: notes.append(f'{path}:{line_no} 行被截断。')
                except GitHubError as exc: notes.append(f'{path}: {exc.message}');errors.append(ToolError(code=exc.code,message=exc.message))
            notes.append('仅检查已列目录；其他目录尚未检查。')
            return ToolResult(tool=name,repo=repo,commit=sha,facts=facts,evidence=evidence,coverage=Coverage(complete=False,truncated=any('超过' in n or '截断' in n or '达到' in n or '未返回结构化值' in n for n in notes),inspected=inspected+files,notes=notes),errors=errors,cache_hit=hit)
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,sha,exc)
    async def analyze_architecture_profile(self,data):
        return await self._derived_scan(data,'arch_profile')
    async def scan_security_and_risk_sinks(self,data):
        return await self._derived_scan(data,'security_scan')
    async def _derived_scan(self,data,kind):
        name='analyze_architecture_profile' if kind=='arch_profile' else 'scan_security_and_risk_sinks'
        repo=self.binding.repo;commit=self.binding.commit
        try:
            req=self.check(data,ScanInput if kind=='arch_profile' else SecurityScanInput)
            scan=await scan_files(self.client,self.binding,req.path_prefix)
            mode=getattr(req,'mode','all'); signals=[]; evidence={};notes=list(scan.notes);errors=list(scan.errors)
            omitted=False;matches_by_path={}
            for file in scan.files:
                path=file['path'];text=file['text']
                if path.lower().endswith(('.py','.pyi')):
                    try:
                        matches=python_signals(text,kind)
                        if kind=='security_scan': matches += [x for x in rule_signals(path,text,kind) if x['category']=='prompt_injection']
                    except (SyntaxError,ValueError,RecursionError):
                        notes.append(f'{path} Python AST 解析失败，使用文本规则线索。');scan.gap(path,'file')
                        matches=rule_signals(path,text,kind)
                else: matches=rule_signals(path,text,kind)
                matches_by_path[path]=matches
            if kind=='arch_profile':
                # Select direct calls across files before imports and text mentions.
                # A busy file must not consume the entire graph budget.
                queues={p:sorted(items,key=lambda x:0 if x['signal']=='ast_call' else 1 if x['signal']=='import' else 2) for p,items in matches_by_path.items()}
                selected={p:[] for p in queues};remaining=40
                for priority in (0,1,2):
                    while remaining:
                        advanced=False
                        for path,items in queues.items():
                            if items and (0 if items[0]['signal']=='ast_call' else 1 if items[0]['signal']=='import' else 2)==priority:
                                selected[path].append(items.pop(0));remaining-=1;advanced=True
                                if not remaining:break
                        if not advanced:break
                for path,items in queues.items():
                    if items:omitted=True;scan.gap(path,'file')
                matches_by_path=selected
            for file in scan.files:
                path=file['path'];text=file['text'];rows=lines_of(text);matches=matches_by_path[path]
                seen=set()
                for item in matches:
                    if kind=='security_scan' and mode!='all' and item['category']!=mode: continue
                    fingerprint=(item['category'],item['relation'],item['to'],item['start_line'],item['end_line'])
                    if fingerprint in seen: continue
                    seen.add(fingerprint)
                    if len(signals)>=40: omitted=True;scan.gap(path,'file');continue
                    start=max(1,item['start_line']-20);end=min(len(rows),item['end_line']+20)
                    # The originating statement must fit intact in the line and character limits.
                    if item['end_line']-item['start_line']+1>120:
                        notes.append(f"{path}:{item['start_line']}-{item['end_line']} 完整语句超出片段行数上限。");scan.gap(path,'file');continue
                    if end-start+1>120:
                        start=item['start_line'];end=item['end_line']
                    ev=evidence_from_scanned_file(repo,commit,file,start,end,self.client.settings.max_fragment_chars)
                    context_complete=bool(ev and ev.start_line==start and ev.end_line==end and not ev.partial_line)
                    if not ev or ev.end_line<item['end_line'] or ev.partial_line:
                        # Retry exactly the statement before declaring the context unavailable.
                        ev=evidence_from_scanned_file(repo,commit,file,item['start_line'],item['end_line'],self.client.settings.max_fragment_chars)
                    if not ev or ev.end_line<item['end_line'] or ev.partial_line:
                        notes.append(f"{path}:{item['start_line']}-{item['end_line']} 完整语句超过字符预算，未生成线索。");scan.gap(path,'file');continue
                    await asyncio.to_thread(self.client.db.save_evidence,ev); evidence[ev.evidence_id]=ev
                    if not context_complete:
                        notes.append(f"{path}:{item['start_line']} 的上下文未完整返回。");scan.gap(path,'file')
                    signals.append({**item,'path':path,'evidence_id':ev.evidence_id,'assessment':('rule_hit' if context_complete else 'insufficient_evidence') if kind=='security_scan' else 'source_signal',**({'context_complete':context_complete,'needs_review':True} if kind=='security_scan' else {})})
            if omitted: notes.append('线索超过 40 项，仅保留前 40 项，其他线索未展开。')
            scope={'path_prefix':req.path_prefix,'directories':scan.directories,'files':[x['path'] for x in scan.files],
                   'bytes_read':scan.bytes_read,'attempted_directories':scan.attempted_directories,'attempted_files':scan.attempted_files,
                   'file_categories':{'denominator':len(scan.files),**{category:sum(file_category(f['path'])==category for f in scan.files) for category in ('src','doc','config','other')}},
                   'complete':not notes and not errors,'notes':notes,'continuation':scan.continuation,'continuations':scan.continuations,'mode':mode if kind=='security_scan' else None}
            refs=sorted(evidence);rule_version='arch-v1' if kind=='arch_profile' else 'security-v1'
            body={'rule_version':rule_version,'scope':scope,'references':refs,'edges' if kind=='arch_profile' else 'findings':signals,
                  'interpretation':'规则线索须结合上下文复核，命中不等于漏洞；无命中不等于安全。' if kind=='security_scan' else '静态线索；导入与调用分别标注，需结合原文核对。'}
            text=json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')); h=digest(text)
            eid=kind+'_'+digest(json.dumps([repo.lower(),commit,rule_version,req.path_prefix,h],ensure_ascii=False))
            url=f'https://github.com/{repo}/tree/{commit}'+('/'+quote(req.path_prefix,safe='/') if req.path_prefix else '')
            artifact=DerivedEvidence(source_type=kind,evidence_id=eid,repo=repo,commit=commit,path_prefix=req.path_prefix,rule_version=rule_version,artifact_sha256=h,references=refs,text=text,source_url=url,fetched_at=timestamp())
            await asyncio.to_thread(self.client.db.save_evidence,artifact)
            return ToolResult(tool=name,repo=repo,commit=commit,facts=[{'kind':kind,'evidence_id':eid}],evidence=[artifact,*evidence.values()],
                              coverage=Coverage(complete=scope['complete'],truncated=bool(notes),notes=notes,inspected=scope['files'],continuation=scan.continuation),errors=[ToolError(**e) for e in errors],cache_hit=bool(scan.cache_hits) and all(scan.cache_hits))
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,commit,exc)

    async def search_repo_issues_and_risks(self,data):
        name='search_repo_issues_and_risks'; repo=self.binding.repo; sha=self.binding.commit
        try:
            req=self.check(data,IssueInput); result,truncated,fetched=await self.client.issues(repo,req.query_keywords,req.state); facts=[]; evidence=[]; notes=[]; errors=[]; output_chars=0
            if truncated: notes.append('Issue 搜索结果不完整或超过 5 条。')
            for item in result.get('items',[])[:self.client.settings.max_issues]:
                number=item['number']
                expected_repo=f'https://api.github.com/repos/{repo}'.lower()
                expected_issue=f'https://github.com/{repo}/issues/{number}'.lower()
                if str(item.get('repository_url','')).lower()!=expected_repo or str(item.get('html_url','')).lower()!=expected_issue:
                    errors.append(ToolError(code='issue_repository_mismatch',message='跳过不属于绑定仓库的 Issue。')); notes.append('搜索结果包含来源不匹配的 Issue。'); continue
                body=item.get('body') or ''
                if len(body)>6000 or output_chars+len(body)>24000:
                    truncated=True; notes.append(f'Issue #{number} 正文超出返回预算，未读取该条。'); continue
                output_chars+=len(body)
                eid='iss_'+digest(json.dumps([repo.lower(),sha,item['id'],item['updated_at'],digest(body)],ensure_ascii=False))
                ev=IssueEvidence(source_type='issue',evidence_id=eid,repo=repo,observed_against_commit=sha,issue_number=number,item_id=item['id'],updated_at=item['updated_at'],fetched_at=fetched,body=body,body_sha256=digest(body),source_url=item['html_url'])
                await asyncio.to_thread(self.client.db.save_evidence,ev); ev=IssueEvidence.model_validate(await asyncio.to_thread(self.client.db.get_evidence,eid)); evidence.append(ev)
                facts.append({'kind':'community_report','issue_number':number,'title':item['title'],'state':item['state'],'evidence_id':eid})
                if item.get('comments',0):
                    try:
                        comments,more,when=await self.client.comments(repo,number)
                        if more or item['comments']>len(comments): truncated=True; notes.append(f'Issue #{number} 评论未全部读取。')
                        for c in comments[:self.client.settings.max_comments]:
                            issue_api=f'https://api.github.com/repos/{repo}/issues/{number}'.lower()
                            expected_url=f'https://github.com/{repo}/issues/{number}#issuecomment-{c["id"]}'.lower()
                            if str(c.get('issue_url','')).lower()!=issue_api or str(c.get('html_url','')).lower()!=expected_url:
                                errors.append(ToolError(code='comment_repository_mismatch',message='跳过来源不匹配的评论。')); notes.append(f'Issue #{number} 存在来源不匹配的评论。'); continue
                            text=c.get('body') or ''
                            if len(text)>6000 or output_chars+len(text)>24000:
                                truncated=True; notes.append(f'Issue #{number} 评论超出返回预算，未读取该条。'); continue
                            output_chars+=len(text)
                            cid='isc_'+digest(json.dumps([repo.lower(),sha,c['id'],c['updated_at'],digest(text)],ensure_ascii=False))
                            cev=IssueEvidence(source_type='issue_comment',evidence_id=cid,repo=repo,observed_against_commit=sha,issue_number=number,item_id=c['id'],updated_at=c['updated_at'],fetched_at=when,body=text,body_sha256=digest(text),source_url=c['html_url'])
                            await asyncio.to_thread(self.client.db.save_evidence,cev); cev=IssueEvidence.model_validate(await asyncio.to_thread(self.client.db.get_evidence,cid)); evidence.append(cev)
                    except GitHubError as exc: errors.append(ToolError(code=exc.code,message=exc.message));notes.append(f'Issue #{number} 评论读取失败。')
            notes.append('社区反馈为抓取时记录，不能单凭标题判断当前提交存在缺陷。')
            return ToolResult(tool=name,repo=repo,commit=sha,facts=facts,evidence=evidence,coverage=Coverage(complete=not truncated and not errors,truncated=truncated,notes=notes,inspected=[f'issues:{req.query_keywords}']),errors=errors,cache_hit=False)
        except (GitHubError,ValidationError,ValueError) as exc: return error(name,repo,sha,exc)


def _guard_tool(method):
    async def guarded(self, data):
        try:
            return await method(self, data)
        except (KeyError, TypeError, AttributeError, IndexError, UnicodeError, RecursionError):
            return ToolResult(tool=method.__name__,repo=self.binding.repo,commit=self.binding.commit,
                coverage=Coverage(complete=False,notes=['上游响应结构无效。']),
                errors=[ToolError(code='invalid_response',message='上游响应结构无效。')])
    return guarded

for _name in ('get_repo_overview_and_tree','get_markdown_outline','read_file_lines',
              'inspect_dependencies_and_env','inspect_deployment_artifacts','search_repo_issues_and_risks',
              'analyze_architecture_profile','scan_security_and_risk_sinks'):
    setattr(AuditTools, _name, _guard_tool(getattr(AuditTools, _name)))
