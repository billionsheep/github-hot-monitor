# 仓库尽调报告

会话：6baee84db13f4c4bb2e4fc5d7723f8f3
状态：COMPLETED

## 问题
对 src/mcp/client 目录做安全线索审计，重点追查 src/mcp/client/stdio.py 的子进程启动与环境变量传递。把规则命中和上下文复核分开，给出对应调用、控制条件和覆盖范围；正常的进程启动或环境变量读取不能直接判为漏洞。

## 结果

### modelcontextprotocol/python-sdk @ 77001c96f9507be0f4d009b83210a384a5e08bda

- **C1 · UNVERIFIED**：已复核的 POSIX 启动分支以参数列表启动进程，未见 shell 拼接，不能将该正常启动调用判为漏洞；Windows 分支委托其他函数。现有证据不足以确认实际安全风险，也不足以覆盖整个目录。[ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7]
  - 依据：static_config；需运行验证：True
  - 下一步：补查 stdio_client、命令解析及 create_windows_process 的实现和调用来源，确认不可信输入能否影响可执行文件与参数；按平台进行受控验证。
  - [ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7](https://github.com/modelcontextprotocol/python-sdk/blob/77001c96f9507be0f4d009b83210a384a5e08bda/src/mcp/client/stdio.py#L323-L355)：`if sys.platform == "win32":  # pragma: no cover
        return await create_windows_process(command, args, env, errlog, cwd)
    else:  # pragma: lax no cover
        return await anyio.open_process(
            [command, *args],
            env=env,
            stderr=errlog,
            cwd=cwd,
            start_new_session=True,
        )`

- **C2 · UNVERIFIED**：默认环境构造仅遍历指定变量集合，并跳过缺失值和以 () 开头的值；启动函数将 env 传给子进程。这些行为本身不能证明敏感信息泄露或环境注入，尚不足以确认实际风险。[ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc] [ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7]
  - 依据：static_config；需运行验证：True
  - 下一步：补查 DEFAULT_INHERITED_ENV_VARS、stdio_client 的环境合并逻辑和 Windows 分支，以哨兵变量验证继承、过滤及覆盖行为。
  - [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc](https://github.com/modelcontextprotocol/python-sdk/blob/77001c96f9507be0f4d009b83210a384a5e08bda/src/mcp/client/stdio.py#L61-L101)：`for key in DEFAULT_INHERITED_ENV_VARS:
        value = os.environ.get(key)
        if value is None:  # pragma: lax no cover
            continue

        if value.startswith("()"):  # pragma: no cover
            # Skip functions, which are a security risk
            continue  # pragma: no cover

        env[key] = value

    return env`
  - [ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7](https://github.com/modelcontextprotocol/python-sdk/blob/77001c96f9507be0f4d009b83210a384a5e08bda/src/mcp/client/stdio.py#L323-L355)：`return await anyio.open_process(
            [command, *args],
            env=env,
            stderr=errlog,
            cwd=cwd,
            start_new_session=True,
        )`

modelcontextprotocol/python-sdk（77001c9）中，两项核查均未确认实际安全风险，状态为 UNVERIFIED。子进程启动方面，stdio.py 的 POSIX 分支以 [command, *args] 参数列表调用 anyio.open_process，未见 shell 拼接，不能将规则命中直接认定为命令注入；Windows 实现、上游参数信任边界及完整调用链尚未核实。环境传递方面，默认环境仅读取指定变量集合，跳过缺失值及以 () 开头的值，并通过 env 传给子进程，这些行为本身不足以证明泄露或注入；变量集合内容、显式环境合并覆盖逻辑及 Windows 处理仍待核查。现有证据仅覆盖部分静态上下文，不能据此认定整个 src/mcp/client 目录存在漏洞或整体安全，需补查相关实现并进行受控验证。

### 安全线索 · modelcontextprotocol/python-sdk
- rule_hit · env_and_network · src/mcp/client/__main__.py:51-59 [ev_96843a965de3fe9ba6bbadc3a837812eb127da2ea568ddec3325e8cdc10e1698]
- rule_hit · env_and_network · src/mcp/client/_input_required.py:123-124 [ev_037cce577d974ac7c41f974955dd439c3e9883aaa5d63bbdbfbabefc3ede2db3]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/client_credentials.py:37-38 [ev_582491e9d4ecf334034b748d08d9bb6fe19ae5e85fa53d4d1fc1f5631abbeb58]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:55-55 [ev_0eb8b1436bd0f278c7d816f2ff1a166ec47205e0cccd5366ea02eb4c305ee794]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:155-155 [ev_3e084943434a00897e3080e8820ef5ffe65ef21db1a4a56b558455299119b6f8]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:156-156 [ev_aec35b5a985f21e905769ce5d0605dd388c3f575610a286f45eb1d213ccd3973]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:179-179 [ev_434d0275ca85595002956c88a8e8de46cbabe4d3134e079e86c6c04915921a7e]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:263-263 [ev_fd10a09c6b68d4dcb07351966b777a0ac602da16ba31182da8be203418c413fa]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:264-264 [ev_10601f057b2746dd834a7fdf5e04a27defc47c8e06eddfafff6fe67200b6de0c]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:288-288 [ev_0ce7cab766c1fd10105a6db47858e3a930c1b0499fbda2e2cf51e1390592dfea]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:398-398 [ev_de4d12555adcd8cec001c43fb20ace1a7cc14aa08abf25a0270f5ea95289030a]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:428-428 [ev_975ae4f87c4bf7b00fd41940add71b2acfcc9dea41b3ec776d9591d1689edaa3]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:450-450 [ev_ede13040cf9cc1c77497b616ee071edadf9cc056515fd2ed5bc1510943b9fe11]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:86-86 [ev_5c53f37c459d1efa4efc4ee274da60ed594bfaf50784a32729a15e4eb1a69e36]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:91-91 [ev_537619a9cfa593b6c7617c00371e86da4f01ee2bc8f2feffb78a6528cfa99bfa]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:95-95 [ev_87d1ed942286e93dca1ef83a7654bc3f3463922e57f7aa1bfc69083d760a971b]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:170-170 [ev_7a76b98f64f8b0389c926e64625f8dbec9490fe20c34d9f28bfdd57ee0a18778]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:174-174 [ev_97e5372196d2409a3f0885fb9e73908b5d3317b095b5ea55bf83a81556419358]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:180-180 [ev_329aaf392bf2dd67d2467cd570f838fb615383ea8649330d6020478cdc751e0a]
- rule_hit · prompt_injection · src/mcp/client/client.py:866-866 [ev_4253805766dfa99fd272eae9a3c1428286cd413790ac814fd01a23c249d896b8]
- rule_hit · prompt_injection · src/mcp/client/client.py:877-883 [ev_161fbb3ad8a89b6866427b77fa07c20122e8f6be4110e196d8f6cc4ba7dfef30]
- rule_hit · prompt_injection · src/mcp/client/client.py:920-922 [ev_db1414cf87fe770674dc1f0bcd59da26c733953bbba942827a56543f9e584fb1]
- rule_hit · prompt_injection · src/mcp/client/session.py:1102-1102 [ev_be340ca3d3ba035afbed9b8a2ef8ba3d8c9c319e0e92b4f3ba608a8b5e26c89d]
- rule_hit · prompt_injection · src/mcp/client/session.py:1191-1191 [ev_965427577ace2de005da748f8f02d468dae832d057ae0ffc44df171a1a7b675a]
- rule_hit · prompt_injection · src/mcp/client/session.py:1240-1251 [ev_062d93c6aade9ba575514fc495abfebb02d176fd1a2de8bfd8a73e62752a4196]
- rule_hit · prompt_injection · src/mcp/client/session.py:1240-1251 [ev_062d93c6aade9ba575514fc495abfebb02d176fd1a2de8bfd8a73e62752a4196]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:391-391 [ev_b43a53843be72113fbc0eb55bb6173944b9d7726e48062eda44c0d860ab7d6af]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:395-395 [ev_f94c7ac474db479d1eb0739ea263f806e05f6c62d983f4799d1dafa7131051b7]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:426-426 [ev_1130e603b1df688c841209c40a974d962e85239fc92b58c9f11bcfad8151b902]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:426-426 [ev_1130e603b1df688c841209c40a974d962e85239fc92b58c9f11bcfad8151b902]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:444-444 [ev_2262a1e6c09a6e0d185c29bc850609066c9e084d0f7a897f23b64df9b75cdbfa]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:83-83 [ev_6fdf5acb3dc799f3db011474a7b6049816c9125d0b37dcbff8d7ca3a48c2fe7f]
- rule_hit · env_and_network · src/mcp/client/sse.py:86-86 [ev_7f6a9182d677d3b743bcc2d4e25c0aeb871f2bd9bc470292bf0ccca636f0a611]
- context_reviewed · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]
- context_reviewed · exec_sinks · src/mcp/client/stdio.py:343-349 [ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7]
- context_reviewed · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]

### 安全线索 · modelcontextprotocol/python-sdk

### 扫描范围 · modelcontextprotocol/python-sdk
文件 24，覆盖完整：False；缺口：文本文件尝试次数达到 24 上限，仍有文件未扫描。；线索超过 40 项，仅保留前 40 项，其他线索未展开。

### 扫描范围 · modelcontextprotocol/python-sdk
文件 0，覆盖完整：False；缺口：未找到或无法确定目录 src/mcp/client/stdio.py。
## 问题
结合 src/mcp/client/stdio.py 原文复核：哪些环境变量会传给子进程？仅有该行为能否确认凭据泄露，仍缺哪些调用方或目的地证据？

## 结果

### modelcontextprotocol/python-sdk @ 77001c96f9507be0f4d009b83210a384a5e08bda

- **C1 · UNVERIFIED**：当前仅重新取得文件结构索引，未取得环境变量构造、合并和进程启动调用的代码原文。历史报告的证据索引不能替代本次原文核查，因此无法确认默认继承名单、平台差异、过滤条件、显式 env 的覆盖规则及最终传递路径。
  - 依据：insufficient；需运行验证：True
  - 下一步：读取上述代码原文，逐项列明平台名单、缺失值及函数形式值的过滤条件、显式 env 是否另受过滤和覆盖优先级；继续追踪各平台最终进程创建函数，必要时用受控子进程验证实际接收环境。

- **C2 · UNVERIFIED**：当前证据不足以确认凭据泄露，也不足以排除特定调用场景的风险。尚未核实调用方是否实际提供敏感凭据、凭据来源及传入条件，亦未确认接收子进程或后续目的地的身份、可信性与授权边界；不能将正常环境变量传递直接判为泄露。
  - 依据：insufficient；需运行验证：True
  - 下一步：在绑定仓库内追踪 StdioServerParameters 和 stdio_client 的具体调用，核实 env 的条件与来源、可执行程序身份和授权关系；若目的地实现或部署配置不在仓库内，明确保留该证据缺口，使用非真实凭据的受控标记验证传递路径。

modelcontextprotocol/python-sdk（提交 77001c96f9507be0f4d009b83210a384a5e08bda）的两项核查均未验证：目前仅取得文件结构索引，缺少 src/mcp/client/stdio.py 环境构造、参数合并及进程启动代码原文，Windows 委托实现亦未复核，因此无法确认默认继承变量名单、平台差异、过滤条件、显式 env 的合并与覆盖规则及最终传递路径。凭据泄露同样证据不足：尚缺具体调用方实际传入敏感凭据的条件与来源、command/args 配置及控制者、接收子进程和后续目的地的身份、可信性与授权边界，以及后续传输证据。不能将正常环境变量传递直接判为泄露，也不能据此排除特定调用场景的风险；仍需追踪相关代码、配置和目的地，必要时使用非真实凭据的受控标记验证。

### 安全线索 · modelcontextprotocol/python-sdk
- rule_hit · env_and_network · src/mcp/client/__main__.py:51-59 [ev_96843a965de3fe9ba6bbadc3a837812eb127da2ea568ddec3325e8cdc10e1698]
- rule_hit · env_and_network · src/mcp/client/_input_required.py:123-124 [ev_037cce577d974ac7c41f974955dd439c3e9883aaa5d63bbdbfbabefc3ede2db3]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/client_credentials.py:37-38 [ev_582491e9d4ecf334034b748d08d9bb6fe19ae5e85fa53d4d1fc1f5631abbeb58]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:55-55 [ev_0eb8b1436bd0f278c7d816f2ff1a166ec47205e0cccd5366ea02eb4c305ee794]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:155-155 [ev_3e084943434a00897e3080e8820ef5ffe65ef21db1a4a56b558455299119b6f8]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:156-156 [ev_aec35b5a985f21e905769ce5d0605dd388c3f575610a286f45eb1d213ccd3973]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:179-179 [ev_434d0275ca85595002956c88a8e8de46cbabe4d3134e079e86c6c04915921a7e]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:263-263 [ev_fd10a09c6b68d4dcb07351966b777a0ac602da16ba31182da8be203418c413fa]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:264-264 [ev_10601f057b2746dd834a7fdf5e04a27defc47c8e06eddfafff6fe67200b6de0c]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:288-288 [ev_0ce7cab766c1fd10105a6db47858e3a930c1b0499fbda2e2cf51e1390592dfea]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:398-398 [ev_de4d12555adcd8cec001c43fb20ace1a7cc14aa08abf25a0270f5ea95289030a]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:428-428 [ev_975ae4f87c4bf7b00fd41940add71b2acfcc9dea41b3ec776d9591d1689edaa3]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:450-450 [ev_ede13040cf9cc1c77497b616ee071edadf9cc056515fd2ed5bc1510943b9fe11]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:86-86 [ev_5c53f37c459d1efa4efc4ee274da60ed594bfaf50784a32729a15e4eb1a69e36]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:91-91 [ev_537619a9cfa593b6c7617c00371e86da4f01ee2bc8f2feffb78a6528cfa99bfa]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:95-95 [ev_87d1ed942286e93dca1ef83a7654bc3f3463922e57f7aa1bfc69083d760a971b]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:170-170 [ev_7a76b98f64f8b0389c926e64625f8dbec9490fe20c34d9f28bfdd57ee0a18778]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:174-174 [ev_97e5372196d2409a3f0885fb9e73908b5d3317b095b5ea55bf83a81556419358]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:180-180 [ev_329aaf392bf2dd67d2467cd570f838fb615383ea8649330d6020478cdc751e0a]
- rule_hit · prompt_injection · src/mcp/client/client.py:866-866 [ev_4253805766dfa99fd272eae9a3c1428286cd413790ac814fd01a23c249d896b8]
- rule_hit · prompt_injection · src/mcp/client/client.py:877-883 [ev_161fbb3ad8a89b6866427b77fa07c20122e8f6be4110e196d8f6cc4ba7dfef30]
- rule_hit · prompt_injection · src/mcp/client/client.py:920-922 [ev_db1414cf87fe770674dc1f0bcd59da26c733953bbba942827a56543f9e584fb1]
- rule_hit · prompt_injection · src/mcp/client/session.py:1102-1102 [ev_be340ca3d3ba035afbed9b8a2ef8ba3d8c9c319e0e92b4f3ba608a8b5e26c89d]
- rule_hit · prompt_injection · src/mcp/client/session.py:1191-1191 [ev_965427577ace2de005da748f8f02d468dae832d057ae0ffc44df171a1a7b675a]
- rule_hit · prompt_injection · src/mcp/client/session.py:1240-1251 [ev_062d93c6aade9ba575514fc495abfebb02d176fd1a2de8bfd8a73e62752a4196]
- rule_hit · prompt_injection · src/mcp/client/session.py:1240-1251 [ev_062d93c6aade9ba575514fc495abfebb02d176fd1a2de8bfd8a73e62752a4196]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:391-391 [ev_b43a53843be72113fbc0eb55bb6173944b9d7726e48062eda44c0d860ab7d6af]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:395-395 [ev_f94c7ac474db479d1eb0739ea263f806e05f6c62d983f4799d1dafa7131051b7]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:426-426 [ev_1130e603b1df688c841209c40a974d962e85239fc92b58c9f11bcfad8151b902]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:426-426 [ev_1130e603b1df688c841209c40a974d962e85239fc92b58c9f11bcfad8151b902]
- rule_hit · prompt_injection · src/mcp/client/session_group.py:444-444 [ev_2262a1e6c09a6e0d185c29bc850609066c9e084d0f7a897f23b64df9b75cdbfa]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:83-83 [ev_6fdf5acb3dc799f3db011474a7b6049816c9125d0b37dcbff8d7ca3a48c2fe7f]
- rule_hit · env_and_network · src/mcp/client/sse.py:86-86 [ev_7f6a9182d677d3b743bcc2d4e25c0aeb871f2bd9bc470292bf0ccca636f0a611]
- rule_hit · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]
- rule_hit · exec_sinks · src/mcp/client/stdio.py:343-349 [ev_4cffd1147ee1dcba8355f68acc154d992854aad24a979b406f9eb894b976e6a7]
- rule_hit · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]

### 安全线索 · modelcontextprotocol/python-sdk
- rule_hit · env_and_network · src/mcp/client/__main__.py:51-59 [ev_96843a965de3fe9ba6bbadc3a837812eb127da2ea568ddec3325e8cdc10e1698]
- rule_hit · env_and_network · src/mcp/client/_input_required.py:123-124 [ev_037cce577d974ac7c41f974955dd439c3e9883aaa5d63bbdbfbabefc3ede2db3]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/client_credentials.py:37-38 [ev_582491e9d4ecf334034b748d08d9bb6fe19ae5e85fa53d4d1fc1f5631abbeb58]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:55-55 [ev_0eb8b1436bd0f278c7d816f2ff1a166ec47205e0cccd5366ea02eb4c305ee794]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:155-155 [ev_3e084943434a00897e3080e8820ef5ffe65ef21db1a4a56b558455299119b6f8]
- rule_hit · env_and_network · src/mcp/client/auth/extensions/identity_assertion.py:156-156 [ev_aec35b5a985f21e905769ce5d0605dd388c3f575610a286f45eb1d213ccd3973]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:179-179 [ev_434d0275ca85595002956c88a8e8de46cbabe4d3134e079e86c6c04915921a7e]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:263-263 [ev_fd10a09c6b68d4dcb07351966b777a0ac602da16ba31182da8be203418c413fa]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:264-264 [ev_10601f057b2746dd834a7fdf5e04a27defc47c8e06eddfafff6fe67200b6de0c]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:288-288 [ev_0ce7cab766c1fd10105a6db47858e3a930c1b0499fbda2e2cf51e1390592dfea]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:398-398 [ev_de4d12555adcd8cec001c43fb20ace1a7cc14aa08abf25a0270f5ea95289030a]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:428-428 [ev_975ae4f87c4bf7b00fd41940add71b2acfcc9dea41b3ec776d9591d1689edaa3]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:450-450 [ev_ede13040cf9cc1c77497b616ee071edadf9cc056515fd2ed5bc1510943b9fe11]
- rule_hit · env_and_network · src/mcp/client/auth/oauth2.py:515-515 [ev_1a9b87577583a4e2f200789500cd5a620ca7246ec909da68a7f106ce24d479b7]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:86-86 [ev_5c53f37c459d1efa4efc4ee274da60ed594bfaf50784a32729a15e4eb1a69e36]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:91-91 [ev_537619a9cfa593b6c7617c00371e86da4f01ee2bc8f2feffb78a6528cfa99bfa]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:95-95 [ev_87d1ed942286e93dca1ef83a7654bc3f3463922e57f7aa1bfc69083d760a971b]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:170-170 [ev_7a76b98f64f8b0389c926e64625f8dbec9490fe20c34d9f28bfdd57ee0a18778]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:174-174 [ev_97e5372196d2409a3f0885fb9e73908b5d3317b095b5ea55bf83a81556419358]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:180-180 [ev_329aaf392bf2dd67d2467cd570f838fb615383ea8649330d6020478cdc751e0a]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:185-185 [ev_644b70a42e13c17a098456966b14ed5dfacff141b9fb8a018a92e09c217efdf7]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:189-189 [ev_6a971402fb397a0af0a7da395d437c0b28d47ed6ee734fd6963a2e30d88c6ecb]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:193-193 [ev_28fd40446d80a05aa30858c1e88fe6d13a0b30399c27f45bb360cdeec9c0a186]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:197-197 [ev_e301e8af0cb02a0f33a7feda0b476577f92e32432d357e1c439fd19cbb23b633]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:290-290 [ev_543d1e49886f475a1c5d05af81130b64394dc8c222ecddf1ab3e85efe5930759]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:334-334 [ev_c086ed56edcc77c974f36f6068ac987e1b313848252b6b52cfe8cf3e5e490e0c]
- rule_hit · env_and_network · src/mcp/client/auth/utils.py:368-368 [ev_7242acf74a9eda2b19dbf584f20ad9ba445a401f48b62790161ebc71ecd8a397]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:27-27 [ev_8f1e62a36cbed7ed1de9947740e57cdd217314bdb813a60ca2b6d95aea96aa01]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:31-31 [ev_8462c7c643882ccbbef38ac05864bda5466c816854d28f4730a6434c25b2a214]
- rule_hit · env_and_network · src/mcp/client/sse.py:83-83 [ev_6fdf5acb3dc799f3db011474a7b6049816c9125d0b37dcbff8d7ca3a48c2fe7f]
- rule_hit · env_and_network · src/mcp/client/sse.py:86-86 [ev_7f6a9182d677d3b743bcc2d4e25c0aeb871f2bd9bc470292bf0ccca636f0a611]
- rule_hit · env_and_network · src/mcp/client/sse.py:87-87 [ev_bf4155c95d19af268d68076f752c7dde1fac717c3071b220445bc96b2a88d486]
- rule_hit · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]
- rule_hit · env_and_network · src/mcp/client/stdio.py:81-81 [ev_4033e32ea664a43bd844568a09078ca7e13137b7e36c15c968f4c4bd766ee4dc]

### 扫描范围 · modelcontextprotocol/python-sdk
文件 24，覆盖完整：False；缺口：文本文件尝试次数达到 24 上限，仍有文件未扫描。；线索超过 40 项，仅保留前 40 项，其他线索未展开。

### 扫描范围 · modelcontextprotocol/python-sdk
文件 24，覆盖完整：False；缺口：文本文件尝试次数达到 24 上限，仍有文件未扫描。
