"""Bounded async GitHub client; never follows redirects or accepts arbitrary hosts."""
import asyncio
import base64
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote
import httpx
from evidence.config import Settings
from evidence.db import AuditDB

class GitHubError(Exception):
    def __init__(self, code, message): self.code, self.message = code, message; super().__init__(message)

def timestamp(): return datetime.now(timezone.utc).isoformat()

def valid_repo(repo):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}', repo) or repo.split('/')[1] in ('.','..'):
        raise GitHubError('invalid_repository','仓库名无效。')
    return repo

def valid_path(path, allow_empty=False):
    if path == '' and allow_empty: return path
    if not path or len(path)>500 or path.startswith('/') or '\\' in path or any(p in ('','.','..') for p in path.split('/')) or any(ord(c)<32 for c in path):
        raise GitHubError('invalid_path','路径必须是仓库内相对路径。')
    return path

class GitHubClient:
    def __init__(self, db=None, settings=None, transport=None):
        self.settings = settings or Settings()
        self.db = db or AuditDB(self.settings)
        headers={'Accept':'application/vnd.github+json','User-Agent':'repoaudit-phase1','X-GitHub-Api-Version':'2022-11-28'}
        if os.environ.get('GITHUB_TOKEN'): headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
        self.http=httpx.AsyncClient(base_url='https://api.github.com',headers=headers,timeout=self.settings.timeout_seconds,follow_redirects=False,transport=transport)
    async def close(self): await self.http.aclose()
    async def request(self,path,params=None):
        if not path.startswith('/') or path.startswith('//'): raise GitHubError('invalid_url','无效请求路径。')
        for attempt in range(self.settings.attempts):
            try:
                response=await self.http.get(path,params=params)
            except (httpx.TimeoutException,httpx.NetworkError):
                if attempt+1<self.settings.attempts: await asyncio.sleep(0.2*(attempt+1)); continue
                raise GitHubError('timeout','GitHub 网络异常或超时。') from None
            if response.status_code==429 or (response.status_code==403 and (response.headers.get('x-ratelimit-remaining')=='0' or response.headers.get('retry-after'))):
                raise GitHubError('rate_limited','GitHub 请求受限，请稍后重试。')
            if response.status_code==404: raise GitHubError('not_found','GitHub 对象不存在或不可公开访问。')
            if response.status_code>=500 and attempt+1<self.settings.attempts:
                await asyncio.sleep(0.2*(attempt+1)); continue
            if response.status_code!=200: raise GitHubError('github_error',f'GitHub 请求失败（HTTP {response.status_code}）。')
            try: return response.json(), response.headers
            except ValueError: raise GitHubError('invalid_response','GitHub 返回无效 JSON。') from None
    async def create_snapshot(self,repo):
        valid_repo(repo)
        meta,_=await self.request(f'/repos/{repo}')
        if meta.get('private') is not False: raise GitHubError('private_repository','只允许公开仓库。')
        canonical=valid_repo(meta['full_name'])
        commit,_=await self.request(f"/repos/{canonical}/commits/{quote(meta['default_branch'],safe='')}")
        sha=commit.get('sha','')
        if not re.fullmatch('[0-9a-f]{40}',sha): raise GitHubError('invalid_response','提交标识无效。')
        snap={'id':uuid.uuid4().hex,'repo':canonical,'sha':sha,'created_at':timestamp()}
        await asyncio.to_thread(self.db.put_snapshot,snap)
        return snap
    async def metadata(self,repo):
        valid_repo(repo)
        data,_=await self.request(f'/repos/{repo}')
        if data.get('private') is not False: raise GitHubError('private_repository','只允许公开仓库。')
        result={k:data.get(k) for k in ('full_name','description','stargazers_count','forks_count','language','pushed_at','open_issues_count','default_branch')}
        result['license_spdx']=(data.get('license') or {}).get('spdx_id')
        return result, timestamp()
    async def tree(self,repo,sha,path=''):
        valid_repo(repo); valid_path(path,True)
        if not re.fullmatch('[0-9a-f]{40}',sha): raise GitHubError('invalid_commit','提交标识无效。')
        async def fetch_tree(tree_sha):
            data,_=await self.request(f'/repos/{repo}/git/trees/{tree_sha}')
            return {'entries':[{'name':e['path'],'type':e['type'],'sha':e['sha'],'size':e.get('size'),'mode':e.get('mode')} for e in data.get('tree',[])], 'truncated':bool(data.get('truncated'))}
        cached=await asyncio.to_thread(self.db.get_cache,repo,sha,'tree',path)
        if cached: return cached[0],cached[1],True
        tree_sha=sha
        if path:
            parent,_,name=path.rpartition('/')
            listing,_,_=await self.tree(repo,sha,parent)
            entry=next((e for e in listing['entries'] if e['name']==name and e['type']=='tree'),None)
            if not entry: raise GitHubError('tree_incomplete' if listing['truncated'] else 'not_found','上级目录不完整，无法判断。' if listing['truncated'] else '目录不存在。')
            tree_sha=entry['sha']
        data=await fetch_tree(tree_sha); fetched=timestamp()
        await asyncio.to_thread(self.db.put_cache,repo,sha,'tree',path,data,fetched)
        return data,fetched,False
    async def file(self,repo,sha,path):
        valid_path(path); parent,_,name=path.rpartition('/')
        listing,_,_=await self.tree(repo,sha,parent)
        entry=next((x for x in listing['entries'] if x['name']==name),None)
        if not entry: raise GitHubError('tree_incomplete' if listing['truncated'] else 'not_found','目录不完整，文件状态未知。' if listing['truncated'] else '文件不存在。')
        if entry['type']!='blob' or entry.get('mode') not in ('100644','100755'): raise GitHubError('not_regular_file','只读取普通文本文件。')
        if (entry.get('size') or 0)>self.settings.max_file_bytes: raise GitHubError('file_too_large','文件超过 512 KiB。')
        cached=await asyncio.to_thread(self.db.get_cache,repo,sha,'blob',path)
        if cached:
            try:
                raw=cached[0]['text'].encode('utf-8')
                if len(raw)>self.settings.max_file_bytes or b'\x00' in raw or hashlib.sha256(raw).hexdigest()!=cached[0]['sha256']:
                    raise ValueError()
            except (KeyError,AttributeError,ValueError):
                raise GitHubError('cache_corrupt','缓存文件校验失败。') from None
            return cached[0],cached[1],True
        blob,_=await self.request(f"/repos/{repo}/git/blobs/{entry['sha']}")
        if blob.get('size',0)>self.settings.max_file_bytes: raise GitHubError('file_too_large','文件超过 512 KiB。')
        try:
            raw=base64.b64decode(blob['content']); text=raw.decode('utf-8')
            if len(raw)>self.settings.max_file_bytes: raise GitHubError('file_too_large','文件超过 512 KiB。')
            if '\x00' in text: raise ValueError()
        except (KeyError,ValueError,UnicodeDecodeError): raise GitHubError('binary_file','文件不是 UTF-8 文本。') from None
        data={'text':text,'sha256':hashlib.sha256(raw).hexdigest()}; fetched=timestamp()
        await asyncio.to_thread(self.db.put_cache,repo,sha,'blob',path,data,fetched)
        return data,fetched,False
    async def issues(self,repo,query,state):
        valid_repo(repo)
        # A keyword string is not a GitHub search expression.
        terms=query.split()
        if not terms or len(terms)>8 or any(not re.fullmatch(r'[\w.-]{1,40}', word, re.UNICODE) or word.upper() in ('OR','AND','NOT') for word in terms):
            raise GitHubError('invalid_keywords','请输入普通关键词，不支持搜索限定符。')
        query=' '.join(terms)
        data,headers=await self.request('/search/issues',{'q':f'repo:{repo} is:issue is:{state} {query}' if state!='all' else f'repo:{repo} is:issue {query}','per_page':self.settings.max_issues,'page':1})
        return data, bool(data.get('incomplete_results') or data.get('total_count',0)>len(data.get('items',[])) or 'rel="next"' in headers.get('link','')), timestamp()
    async def comments(self,repo,number):
        data,headers=await self.request(f'/repos/{repo}/issues/{number}/comments',{'per_page':self.settings.max_comments,'page':1})
        return data, 'rel="next"' in headers.get('link',''), timestamp()
