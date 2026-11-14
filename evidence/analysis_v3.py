"""Bounded source traversal and conservative AST/rule signals for RepoAudit v3."""
import ast
from collections import deque
from dataclasses import dataclass, field
from evidence.github_client import GitHubError, valid_path

MAX_DIRS=24
MAX_FILES=24
MAX_BYTES=1024*1024
MAX_FILE_BYTES=512*1024
EXCLUDED={'.git','.hg','.svn','.venv','venv','node_modules','__pycache__','.mypy_cache','.pytest_cache','.ruff_cache','dist','build','coverage','vendor','target','.next','.tox'}
TEXT_SUFFIXES=('.py','.pyi','.js','.jsx','.ts','.tsx','.mjs','.cjs','.sh','.bash','.zsh','.md','.markdown','.txt','.toml','.yaml','.yml','.json','.ini','.cfg')
TEXT_NAMES={'dockerfile','makefile','.env.example','.env.template','license','licence','copying','notice'}

def dotted(node):
    if isinstance(node,ast.Name): return node.id
    if isinstance(node,ast.Attribute):
        parent=dotted(node.value)
        return f'{parent}.{node.attr}' if parent else node.attr
    return ''

def aliases_for(tree):
    aliases={}; rows=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):
            for item in node.names:
                name=item.asname or item.name.split('.')[0]; target=item.name if item.asname else name
                aliases[name]=target;rows.append({'name':name,'target':target,'start_line':node.lineno,'end_line':node.end_lineno})
        if isinstance(node,ast.ImportFrom):
            for item in node.names:
                name=item.asname or item.name; target='.'*node.level+(node.module or '')+'.'+item.name
                aliases[name]=target.lstrip('.') if not node.level else target
                rows.append({'name':name,'target':aliases[name],'start_line':node.lineno,'end_line':node.end_lineno})
    return aliases,rows

def resolve(name,aliases):
    head,sep,tail=name.partition('.')
    return aliases.get(head,head)+(sep+tail if sep else '')

def params_for(node):
    if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): return []
    args=node.args;pos=list(args.posonlyargs)+list(args.args); defaults=[False]*(len(pos)-len(args.defaults))+[True]*len(args.defaults)
    result=[{'name':arg.arg,'kind':'positional_only' if i<len(args.posonlyargs) else 'positional','has_default':default,'line':arg.lineno} for i,(arg,default) in enumerate(zip(pos,defaults))]
    if args.vararg: result.append({'name':args.vararg.arg,'kind':'vararg','has_default':False,'line':args.vararg.lineno})
    result.extend({'name':arg.arg,'kind':'keyword_only','has_default':default is not None,'line':arg.lineno} for arg,default in zip(args.kwonlyargs,args.kw_defaults))
    if args.kwarg: result.append({'name':args.kwarg.arg,'kind':'kwarg','has_default':False,'line':args.kwarg.lineno})
    return result

def python_index(text):
    tree=ast.parse(text);aliases,imports=aliases_for(tree);parents={child:parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    def statement(node):
        current=node
        while current in parents and not isinstance(current,ast.stmt): current=parents[current]
        return current
    def call_info(call):
        stmt=statement(call)
        return {'name':dotted(call.func),'resolved':resolve(dotted(call.func),aliases),'keywords':[k.arg or '**' for k in call.keywords],
                'keyword_arguments':[{'name':k.arg or '**','value':ast.unparse(k.value)[:200]} for k in call.keywords],
                'start_line':call.lineno,'end_line':call.end_lineno,'statement_start':stmt.lineno,'statement_end':stmt.end_lineno}
    entries=[]; calls=[]
    for item in imports:
        entries.append({'title':item['name'],'kind':'Import','start_line':item['start_line'],'end_line':item['end_line'],'parameters':[],'calls':[],'aliases':[item]})
    for n in ast.walk(tree):
        if isinstance(n,(ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Return)):
            symbols=[]
            for part in ast.walk(n):
                if isinstance(part,ast.Name): value=part.id
                elif isinstance(part,ast.Attribute): value=dotted(part)
                elif isinstance(part,ast.Constant) and isinstance(part.value,str) and len(part.value)<=100: value=part.value
                else: continue
                if value and value not in symbols:symbols.append(value)
            if symbols:
                entries.append({'title':symbols[0],'kind':type(n).__name__,'start_line':n.lineno,'end_line':n.end_lineno,'parameters':[],'calls':[],'aliases':[],'symbols':symbols[:80]})
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            nested=[]
            for call in ast.walk(n):
                if isinstance(call,ast.Call):
                    nested.append(call_info(call))
            entries.append({'title':n.name,'kind':type(n).__name__,'start_line':n.lineno,'end_line':n.end_lineno,'parameters':params_for(n),'calls':nested[:60],'calls_truncated':len(nested)>60,'aliases':imports[:60]})
        if isinstance(n,ast.Call):
            stmt=statement(n);calls.append(call_info(n))
            entries.append({'title':resolve(dotted(n.func),aliases),'kind':'Call','start_line':stmt.lineno,'end_line':stmt.end_lineno,'parameters':[],'calls':[calls[-1]],'aliases':[]})
    entries.sort(key=lambda x:(x['start_line'],x['end_line']));calls.sort(key=lambda x:(x['start_line'],x['end_line']))
    return tree,entries,calls,imports

@dataclass
class ScanResult:
    files: list=field(default_factory=list)
    directories: list=field(default_factory=list)
    notes: list=field(default_factory=list)
    errors: list=field(default_factory=list)
    continuation: str | None=None
    bytes_read: int=0
    attempted_directories: int=0
    attempted_files: int=0
    continuations: list=field(default_factory=list)
    cache_hits: list=field(default_factory=list)
    @property
    def complete(self): return not self.notes and not self.errors

    def gap(self,path,kind):
        prefix=path.rpartition('/')[0] if kind=='file' else ('' if path=='/' else path)
        item={'kind':kind,'path':path,'path_prefix':prefix}
        if item not in self.continuations:self.continuations.append(item)
        if self.continuation is None:self.continuation=prefix

def file_priority(item):
    path=item[0];base=path.rsplit('/',1)[-1].lower()
    if base in ('pyproject.toml','package.json','dockerfile','compose.yaml','docker-compose.yml','docker-compose.yaml'): rank=0
    elif base.endswith(('.py','.pyi','.js','.jsx','.ts','.tsx','.mjs','.cjs','.sh','.bash','.zsh')): rank=1
    elif base.endswith(('.toml','.yaml','.yml','.json','.ini','.cfg')) or base in ('.env.example','.env.template','makefile'): rank=2
    else: rank=3
    return (rank,path.lower(),path)

def file_category(path):
    base=path.rsplit('/',1)[-1].lower()
    if base.endswith(('.py','.pyi','.js','.jsx','.ts','.tsx','.mjs','.cjs','.sh','.bash','.zsh')):return 'src'
    if base.endswith(('.toml','.yaml','.yml','.json','.ini','.cfg')) or base in ('dockerfile','makefile','.env.example','.env.template'):return 'config'
    if base.endswith(('.md','.markdown','.txt')) or base in ('license','licence','copying','notice'):return 'doc'
    return 'other'

def directory_priority(item):
    name=item['name'].lower()
    preferred=('src','app','apps','lib','libs','packages','server','api','python','mcp','core')
    return (preferred.index(name) if name in preferred else len(preferred),name)

async def scan_files(client,binding,prefix):
    valid_path(prefix,True)
    result=ScanResult(); repo=binding.repo;sha=binding.commit
    # Visiting the ancestors explicitly bounds path resolution and makes their cost visible.
    ancestors=[];parts=prefix.split('/') if prefix else []
    if len(parts)>=MAX_DIRS:
        result.notes.append('路径前缀层级超过目录预算。');result.gap(prefix,'directory');return result
    for i in range(len(parts)):
        path='/'.join(parts[:i]);ancestors.append(path)
        try:
            result.attempted_directories+=1
            listing,_,hit=await client.tree(repo,sha,path);result.directories.append(path or '/');result.cache_hits.append(hit)
            child=next((e for e in listing['entries'] if e['name']==parts[i] and e['type']=='tree'),None)
            if listing.get('truncated'): result.notes.append(f'{path or "/"} 目录截断，前缀解析可能不完整。');result.gap(path or '/','directory')
            if not child:
                result.notes.append(f'未找到或无法确定目录 {prefix}。');result.gap(prefix,'directory');return result
        except GitHubError as exc:
            result.errors.append({'code':exc.code,'message':exc.message});result.notes.append(f'{path or "/"} 目录读取失败。');result.gap(path or '/','directory');return result
    queue=deque([prefix]);files=[]
    while queue:
        queue=deque(sorted(queue,key=lambda p:tuple(directory_priority({'name':part}) for part in p.split('/') if part)))
        path=queue.popleft()
        if result.attempted_directories>=MAX_DIRS:
            result.notes.append('目录数达到 24 上限，仍有目录未扫描。')
            for pending in [path,*queue]:result.gap(pending or '/','directory')
            break
        try:
            result.attempted_directories+=1
            listing,_,hit=await client.tree(repo,sha,path);result.directories.append(path or '/');result.cache_hits.append(hit)
        except GitHubError as exc:
            result.errors.append({'code':exc.code,'message':exc.message});result.notes.append(f'{path or "/"} 目录读取失败。');result.gap(path or '/','directory');continue
        if listing.get('truncated'):
            result.notes.append(f'{path or "/"} 目录截断；未列出的项目未扫描。');result.gap(path or '/','directory')
        for e in sorted(listing['entries'],key=directory_priority):
            name=e['name']; full=f'{path}/{name}' if path else name
            if e['type']=='tree':
                if name not in EXCLUDED: queue.append(full)
            elif e['type']=='blob' and e.get('mode') in ('100644','100755') and (name.lower().endswith(TEXT_SUFFIXES) or name.lower() in TEXT_NAMES): files.append((full,e.get('size')))
    files.sort(key=file_priority)
    for index,(path,size) in enumerate(files):
        if result.attempted_files>=MAX_FILES:
            result.notes.append('文本文件尝试次数达到 24 上限，仍有文件未扫描。')
            for rest,_ in files[index:]:result.gap(rest,'file')
            break
        if size is not None and size>MAX_FILE_BYTES:
            result.notes.append(f'{path} 超过 512 KiB，未读取。');result.gap(path,'file');continue
        remaining=MAX_BYTES-result.bytes_read
        if remaining<=0 or (size is not None and size>remaining) or (size is None and remaining<MAX_FILE_BYTES):
            result.notes.append(f'总读取预算 1 MiB 不足，未读取 {path}。');result.gap(path,'file');continue
        try:
            result.attempted_files+=1
            blob,fetched,hit=await client.file(repo,sha,path);size_actual=len(blob['text'].encode('utf-8'))
            result.bytes_read+=size_actual
            if size_actual>MAX_FILE_BYTES or size_actual>remaining:
                result.notes.append(f'{path} 实际大小超出剩余预算，未纳入扫描。');result.gap(path,'file');continue
            result.files.append({'path':path,'text':blob['text'],'sha256':blob['sha256'],'fetched_at':fetched});result.cache_hits.append(hit)
        except GitHubError as exc:
            result.errors.append({'code':exc.code,'message':exc.message});result.notes.append(f'{path} 未读取：{exc.message}');result.gap(path,'file')
    return result

# These labels identify review leads, not verified architecture or vulnerabilities.
def architecture_kind(name):
    n=name.lower()
    if any(x in n for x in ('router','route','fastapi','flask','add_api_route','app.get','app.post')): return 'entry_or_route'
    if any(x in n for x in ('run','execute','invoke','dispatch','loop','agent')): return 'execution_loop'
    if any(x in n for x in ('sqlite','database','session','persist','cache','save','load')): return 'state_persistence'
    if any(x in n for x in ('gather','create_task','retry','semaphore','thread','lock','sleep')): return 'concurrency_retry'
    if any(x in n for x in ('openai','anthropic','model','completion','tool_call','tool_result','tool_registry','tool_schema','tools.','responses','mcp')): return 'model_tool_protocol'
    return None

def security_kind(name,keywords=()):
    n=name.lower()
    if n in ('eval','exec','compile','builtins.eval','builtins.exec','os.system','os.popen','subprocess.run','subprocess.popen','subprocess.call','subprocess.check_output','subprocess.check_call','anyio.open_process','anyio.run_process','asyncio.create_subprocess_exec','asyncio.create_subprocess_shell','pickle.load','pickle.loads','yaml.unsafe_load','yaml.load') or ('subprocess.' in n and 'shell' in keywords): return 'exec_sinks'
    if n.startswith(('os.environ','os.getenv','httpx.','requests.','urllib.','aiohttp.')) or any(x in n for x in ('getenv','environ.get','urlopen','http.client')): return 'env_and_network'
    if any(x in n for x in ('prompt','system_message','user_message','instruction','tool_result')): return 'prompt_injection'
    return None

def python_signals(text,profile):
    tree,entries,calls,imports=python_index(text);signals=[]
    if profile=='arch_profile':
        for item in imports:
            kind=architecture_kind(item['target'])
            if kind: signals.append({'category':kind,'relation':'import','from':'module','to':item['target'],'start_line':item['start_line'],'end_line':item['end_line'],'signal':'import'})
    lines=text.splitlines()
    for c in calls:
        kind=architecture_kind(c['resolved']) if profile=='arch_profile' else security_kind(c['resolved'],c['keywords'])
        relation='call'
        if profile=='arch_profile':
            import re
            statement='\n'.join(lines[c['statement_start']-1:c['statement_end']]);name=c['resolved'].lower()
            if name=='open' or name.endswith(('.read','.read_text','.read_bytes')):
                kind='state_persistence';relation='write' if name=='open' and re.search(r"(?:\bmode\s*=\s*|,\s*)['\"][wax]",statement) else 'read'
            elif name.endswith(('.write','.write_text','.write_bytes')):
                kind='state_persistence';relation='write'
            elif name.endswith(('.execute','.executemany')):
                if re.search(r'\bSELECT\b',statement,re.I): kind='state_persistence';relation='read'
                elif re.search(r'\b(?:INSERT|UPDATE|DELETE|REPLACE)\b',statement,re.I): kind='state_persistence';relation='write'
        if not kind: continue
        enclosing=[x for x in entries if x['start_line']<=c['statement_start']<=x['end_line']]
        source=min(enclosing,key=lambda x:x['end_line']-x['start_line'])['title'] if enclosing else 'module'
        signals.append({'category':kind,'relation':relation,'from':source,'to':c['resolved'] or c['name'],'start_line':c['statement_start'],'end_line':c['statement_end'],'signal':'ast_call','keywords':c['keywords']})
    if profile=='security_scan':
        # Subscript and assignment uses such as os.environ["KEY"] are not calls.
        parents={child:parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not isinstance(node,(ast.Subscript,ast.Attribute)): continue
            name=dotted(node.value) if isinstance(node,ast.Subscript) else dotted(node)
            if resolve(name,aliases_for(tree)[0]) not in ('os.environ','environ'): continue
            stmt=node
            while stmt in parents and not isinstance(stmt,ast.stmt): stmt=parents[stmt]
            signals.append({'category':'env_and_network','relation':'access','from':'module','to':'os.environ','start_line':stmt.lineno,'end_line':stmt.end_lineno,'signal':'ast_access'})
    return signals

def rule_signals(path,text,profile):
    import re
    signals=[]
    if profile=='arch_profile':
        pattern=re.compile(r'\b(import|require|from|route|router|app\.(?:get|post)|retry|queue|model|tool|state|sqlite|persist|async|await)\b',re.I)
    else:
        pattern=re.compile(r'\b(eval|exec|spawn|execSync|child_process|subprocess|shell|process\.env|os\.environ|fetch|requests|prompt|instruction|tool.result)\b|https?://|ignore\s+(?:all|previous|prior|earlier).{0,80}\b(?:instructions?|constraints?|rules?)\b|忽略.{0,30}(?:指令|约束|规则)',re.I)
    for line_no,line in enumerate(text.splitlines(),1):
        if not pattern.search(line): continue
        if profile=='arch_profile': kind=architecture_kind(line)
        else:
            kind=('prompt_injection' if re.search(r'ignore\s+(?:all|previous|prior|earlier).{0,80}\b(?:instructions?|constraints?|rules?)\b|忽略.{0,30}(?:指令|约束|规则)|\b(prompt|instruction|tool.result)\b',line,re.I) else 'exec_sinks' if re.search(r'\b(eval|exec|spawn|execSync|child_process|subprocess|shell)\b',line,re.I) else 'env_and_network')
        if kind: signals.append({'category':kind,'relation':'rule_mention','from':'file','to':line.strip()[:200],'start_line':line_no,'end_line':line_no,'signal':'text_rule'})
    return signals
