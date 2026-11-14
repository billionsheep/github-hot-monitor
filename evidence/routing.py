"""Conservative per-turn routing and source hints; no model calls."""
import re

MODES={'deploy_readiness','arch_research','sec_sentinel'}
PATH_RE=re.compile(r'(?<![\w/.-])(?:[\w.-]+/)*[\w.-]+\.(?:py|pyi|toml|ya?ml|json|cfg|ini|md|txt|sh)(?![\w.-])',re.I)
SYMBOL_RE=re.compile(r'(?<![\w])(?:[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)(?![\w])')

def source_hints(query):
    paths=list(dict.fromkeys(PATH_RE.findall(query)))[:12]
    symbol_text=PATH_RE.sub(' ',query)
    symbols=list(dict.fromkeys(SYMBOL_RE.findall(symbol_text)))[:16]
    for match in re.findall(r'[`“\"]([A-Za-z_][\w.]{1,99})[`”\"]',query):
        if match not in symbols and '/' not in match and not PATH_RE.fullmatch(match): symbols.append(match)
    return {'paths':paths,'symbols':symbols[:16]}

def scoped_source_hints(query,binding,bindings):
    hints=source_hints(query)
    if len(bindings)<2:return hints
    path_matches=list(PATH_RE.finditer(query));mentions=[]
    for candidate in bindings:
        owner,name=candidate['repo'].split('/',1)
        variants={candidate['repo'],owner,name,name.replace('-',' '),owner.split('-')[0],name.split('-')[0]}
        for label in variants:
            if len(label)<3:continue
            for found in re.finditer(r'(?<![A-Za-z0-9])'+re.escape(label)+r'(?![A-Za-z0-9])',query,re.I):
                if any(m.start()<=found.start()<m.end() for m in path_matches):continue
                mentions.append((found.start(),candidate['repo'].lower()))
    if not mentions:return hints
    assigned=[]
    for match in path_matches:
        preceding=[x for x in mentions if x[0]<match.start()]
        if preceding and max(preceding,key=lambda x:x[0])[1]==binding['repo'].lower():assigned.append(match.group())
    return {'paths':list(dict.fromkeys(assigned))[:12],'symbols':hints['symbols']}

def choose_route(query,bindings,workflow_mode,force_full=False):
    def full(reason): return {'route':'full','reason':reason}
    if force_full:return full('评测强制完整流程')
    if workflow_mode!='deploy_readiness':return full('架构与安全工作流使用完整流程')
    if len(bindings)!=1:return full('多仓比较使用完整流程')
    text=query.strip();lower=text.lower();hints=source_hints(text)
    if len(text)>300 or len(re.findall(r'[?？;；]',text))>1:return full('问题包含多个疑问或范围不明确')
    if len(hints['paths'])>1:return full('问题涉及多个文件，使用完整流程')
    if re.search(r'\b(?:docker|compose|kubernetes|k8s|ollama)\b|性能|架构|安全|漏洞|部署|兼容性实测',lower,re.I):return full('包含部署、架构、安全或性能约束')
    if re.search(r'并且|以及|同时|另外|还有|分别|对比|比较|\b(?:and|also|compare|versus)\b',lower):return full('包含多个约束或比较要求')
    versions=set(re.findall(r'(?i)python\s*(\d+\.\d+(?:\.\d+)?)',text))
    all_versions=set(re.findall(r'(?<![\d.])\d+\.\d+(?:\.\d+)?(?![\d.])',text))
    if len(versions)==1 and len(all_versions)==1 and not re.search(r'\b(?:license|mit|apache|gpl|protocol|base_url|endpoint)\b|协议|许可证',text,re.I):
        if re.search(r'(?i)支持|允许|包含|兼容|requires.python|版本范围|version|support|allow',text): return {'route':'fast','reason':'单仓单项 Python 版本声明'}
    licenses=set(re.findall(r'(?i)\b(?:mit|apache(?:-2\.0)?|(?:a?gpl)(?:-\d(?:\.\d)?)?|bsd(?:-\d-clause)?)\b',text))
    if len(licenses)==1 and not re.search(r'(?i)python|docker|模型|endpoint|base_url',text) and re.search(r'协议|许可|license|licence',text,re.I):return {'route':'fast','reason':'单仓单项协议声明'}
    if len(hints['paths'])==1 and len(hints['symbols'])==1 and re.search(r'配置|读取|声明|赋值|config|setting|value|environment|环境变量',text,re.I) and not re.search(r'(?i)python|docker|license|协议|性能|安全',text):
        return {'route':'fast','reason':'单仓指定文件的单项配置'}
    return full('问题范围不满足确定性单项条件')
