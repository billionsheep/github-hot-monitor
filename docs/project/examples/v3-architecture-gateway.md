# 仓库尽调报告

会话：d5eb2968848644bcb12b9f12200c0ec7
状态：COMPLETED

## 问题
比较两个框架的 OpenAI 模型接入架构和服务地址参数传递。Pydantic AI 重点查看 pydantic_ai_slim/pydantic_ai/providers/openai.py，Agno 重点查看 libs/agno/agno/models/openai/chat.py。请自行定位 base_url 的定义和传递调用，用完整语句证据说明接入组件及静态调用关系；分别核查自定义地址是否进入客户端配置，并标明尚需运行验证的部分。

## 结果

### pydantic/pydantic-ai @ e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a

- **C1 · UNVERIFIED**：当前证据只能确认 OpenAIProvider 中的一段静态调用：调用 self._create_openai_client，传入 base_url、api_key、http_client，并将返回值写入 self._client；尚不足以列全 OpenAI 模型接入组件及其调用关系 [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091]。
  - 依据：insufficient；需运行验证：False
  - 下一步：继续静态检查模型入口、provider 解析及 _create_openai_client 的定义与调用点，建立带文件行号的组件和调用关系图。
  - [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L225-L225)：`self._client = self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)`

- **C2 · UNVERIFIED**：已确认 base_url 以同名关键字传入 self._create_openai_client，结果存入 self._client [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091]；另有读取 self.client.base_url 并转换为字符串的代码 [ev_0d4801e3c637e775a4147b53c47dd708a4ee2fbc8a5519949d7ab7fea1a282f0]。这些静态片段尚不能证明自定义地址最终进入 OpenAI SDK 客户端配置。
  - 依据：insufficient；需运行验证：True
  - 下一步：读取 OpenAIProvider 构造签名、_create_openai_client 实现及 SDK 构造调用，确认 base_url 是否原样传入；随后以自定义地址构造客户端并用模拟传输验证请求目标。
  - [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L225-L225)：`self._client = self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)`
  - [ev_0d4801e3c637e775a4147b53c47dd708a4ee2fbc8a5519949d7ab7fea1a282f0](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L66-L66)：`return str(self.client.base_url)`

### agno-agi/agno @ 878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1

- **C1 · UNVERIFIED**：已确认 chat.py 中的部分静态调用关系：调用 self._get_client_params() 获取配置，可加入 httpx.Client 实例，随后将配置展开传给 OpenAIClient 并缓存到 self.client。[ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2] 现有证据不足以完整列出仓库的 OpenAI 接入组件、导入关系和请求调用链。
  - 依据：static_config；需运行验证：False
  - 下一步：读取 chat.py 的导入、类声明、同步及异步请求方法，并追踪上游模型调用方；分别记录导入、直接调用和客户端状态写入。
  - [ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L146-L157)：`client_params: Dict[str, Any] = self._get_client_params()
        if self.http_client:
            if isinstance(self.http_client, httpx.Client):
                client_params["http_client"] = self.http_client`
  - [ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L146-L157)：`self.client = OpenAIClient(**client_params)`

- **C2 · PASS**：静态证据确认：libs/agno/agno/models/openai/chat.py 第81行定义 base_url，类型为可选字符串或 httpx.URL，默认 None。[ev_97ae85358ab105eb4e896b0bedcee571d724b7ca27c2fb40c3933e803af3b7e5] self.base_url 被放入 base_params，过滤 None 后合并 self.client_params，因此后者可覆盖同名配置。[ev_ceaa40d4dc1ede8ae364a97900c9f43d001c5fe35041b3e2ab5bd3e8cf96dd5d] 客户端构造路径调用 self._get_client_params()，再通过 OpenAIClient(**client_params) 传入配置，证明非 None 的自定义地址能够进入该客户端构造参数；这不是实际网络访问验证。[ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2]
  - 依据：static_config；需运行验证：False
  - 下一步：本项静态配置传递已获支持；若需确认真实请求目的地址，可另行使用受控服务测试，且应单独核查异步客户端路径，不将此结论外推到所有接入实现。
  - [ev_97ae85358ab105eb4e896b0bedcee571d724b7ca27c2fb40c3933e803af3b7e5](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L81-L81)：`base_url: Optional[Union[str, httpx.URL]] = None`
  - [ev_ceaa40d4dc1ede8ae364a97900c9f43d001c5fe35041b3e2ab5bd3e8cf96dd5d](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L116-L132)：`"base_url": self.base_url,`
  - [ev_ceaa40d4dc1ede8ae364a97900c9f43d001c5fe35041b3e2ab5bd3e8cf96dd5d](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L116-L132)：`client_params = {k: v for k, v in base_params.items() if v is not None}

        # Add additional client params if provided
        if self.client_params:
            client_params.update(self.client_params)
        return client_params`
  - [ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L146-L157)：`client_params: Dict[str, Any] = self._get_client_params()`
  - [ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L146-L157)：`self.client = OpenAIClient(**client_params)`

pydantic/pydantic-ai：现有证据仅确认 OpenAIProvider 调用 self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)，并将返回值保存到 self._client；另有将 self.client.base_url 转为字符串的代码。尚未确认完整接入组件与调用链、base_url 的定义和默认值，也不能证明自定义地址最终进入 OpenAI SDK 客户端配置。

agno-agi/agno：已确认 libs/agno/agno/models/openai/chat.py 的局部调用链为 self._get_client_params() → 可加入 httpx.Client → OpenAIClient(**client_params) → self.client。该文件第81行定义 base_url: Optional[Union[str, httpx.URL]] = None；self.base_url 进入 base_params，过滤 None 后再合并 self.client_params，后者可覆盖同名配置，最终作为客户端构造参数传入。因此，该路径已静态确认支持自定义服务地址进入客户端配置，但未验证实际网络请求目标，亦未覆盖异步路径。

比较：两仓库的完整 OpenAI 接入架构均未获充分证据支持；base_url 方面，pydantic-ai 仅确认传到客户端工厂，agno 则已确认从字段定义、配置合并到客户端构造的静态传递链。

### 架构线索 · pydantic/pydantic-ai
- anyio.Lock —call→ anyio.Lock · [pydantic_ai_slim/pydantic_ai/providers/__init__.py:86-86](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/__init__.py#L66-L106)
- self.model_profile —call→ self.model_profile · [pydantic_ai_slim/pydantic_ai/providers/__init__.py:185-185](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/__init__.py#L165-L205)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py:53-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py#L33-L74)
- model_name.removeprefix —call→ model_name.removeprefix · [pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py:54-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py#L34-L74)
- anyio.sleep —call→ anyio.sleep · [pydantic_ai_slim/pydantic_ai/providers/_github_copilot_oauth.py:109-109](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_github_copilot_oauth.py#L89-L129)
- self.wfile.write —write→ self.wfile.write · [pydantic_ai_slim/pydantic_ai/providers/_oauth.py:112-112](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth.py#L92-L132)
- cancelled —call→ threading.Event · [pydantic_ai_slim/pydantic_ai/providers/_oauth.py:117-117](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth.py#L97-L137)
- claims.validate_python —call→ json.loads · [pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py:128-128](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py#L108-L148)
- self._client —call→ openai.AsyncOpenAI · [pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py:326-331](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py#L306-L351)
- AsyncOpenAI —call→ openai.AsyncOpenAI · [pydantic_ai_slim/pydantic_ai/providers/_openai_compatible.py:51-56](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_openai_compatible.py#L31-L64)
- base_profile —call→ pydantic_ai.profiles.qwen.qwen_model_profile · [pydantic_ai_slim/pydantic_ai/providers/alibaba.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/alibaba.py#L23-L63)
- openai_profile —call→ pydantic_ai.profiles.openai.OpenAIModelProfile · [pydantic_ai_slim/pydantic_ai/providers/alibaba.py:48-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/alibaba.py#L28-L74)
- bedrock_provider —call→ pydantic_ai.providers._bedrock_model_names.split_bedrock_model_id · [pydantic_ai_slim/pydantic_ai/providers/anthropic.py:154-154](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/anthropic.py#L134-L174)
- profile —call→ pydantic_ai.profiles.anthropic.anthropic_model_profile · [pydantic_ai_slim/pydantic_ai/providers/anthropic.py:157-157](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/anthropic.py#L137-L177)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/azure.py:122-122](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/azure.py#L102-L142)
- route_profile —call→ pydantic_ai.profiles._special_tokens.special_token_route_profile · [pydantic_ai_slim/pydantic_ai/providers/azure.py:137-137](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/azure.py#L117-L157)
- downstream —call→ pydantic_ai.profiles.anthropic.anthropic_model_profile · [pydantic_ai_slim/pydantic_ai/providers/bedrock.py:370-370](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock.py#L350-L390)
- profile —call→ BedrockModelProfile · [pydantic_ai_slim/pydantic_ai/providers/bedrock.py:375-398](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock.py#L355-L418)
- provider —call→ pydantic_ai.providers._bedrock_model_names.split_bedrock_model_id · [pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py#L23-L63)
- base_model_name.startswith —call→ base_model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py:49-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py#L29-L74)
- model_name_lower —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/cerebras.py:64-64](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cerebras.py#L44-L84)
- model_name_lower.startswith —call→ model_name_lower.startswith · [pydantic_ai_slim/pydantic_ai/providers/cerebras.py:66-68](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cerebras.py#L46-L88)
- profile —call→ pydantic_ai.profiles.cohere.cohere_model_profile · [pydantic_ai_slim/pydantic_ai/providers/cohere.py:48-48](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cohere.py#L28-L68)
- profile —call→ pydantic_ai.ModelProfile · [pydantic_ai_slim/pydantic_ai/providers/cohere.py:48-48](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cohere.py#L28-L68)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/crusoe.py:64-64](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/crusoe.py#L44-L84)
- vendor —call→ model_name.split · [pydantic_ai_slim/pydantic_ai/providers/crusoe.py:66-66](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/crusoe.py#L46-L86)
- profile —call→ pydantic_ai.profiles.deepseek.deepseek_model_profile · [pydantic_ai_slim/pydantic_ai/providers/deepseek.py:49-49](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/deepseek.py#L29-L69)
- is_flash_or_v4 —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/deepseek.py:50-50](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/deepseek.py#L30-L70)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/fireworks.py:52-52](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/fireworks.py#L32-L72)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/fireworks.py:65-70](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/fireworks.py#L45-L90)
- route —call→ _gateway_route · [pydantic_ai_slim/pydantic_ai/providers/gateway.py:165-165](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/gateway.py#L145-L185)
- _build_gateway_provider —call→ .openai.OpenAIProvider · [pydantic_ai_slim/pydantic_ai/providers/gateway.py:185-191](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/gateway.py#L165-L211)
- openai_model_profile —call→ pydantic_ai.profiles.openai.openai_model_profile · [pydantic_ai_slim/pydantic_ai/providers/github.py:73-73](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github.py#L53-L93)
- provider —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/github.py:75-75](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github.py#L55-L95)
- overlay —call→ pydantic_ai.profiles.openai.OpenAIModelProfile · [pydantic_ai_slim/pydantic_ai/providers/github_copilot.py:81-89](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github_copilot.py#L61-L109)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/github_copilot.py:91-116](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github_copilot.py#L71-L136)
- google_model_profile —call→ pydantic_ai.profiles.google.google_model_profile · [pydantic_ai_slim/pydantic_ai/providers/google.py:80-80](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/google.py#L60-L100)
- google_realtime_model_profile —call→ pydantic_ai.profiles.google.google_realtime_model_profile · [pydantic_ai_slim/pydantic_ai/providers/google.py:84-84](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/google.py#L64-L104)
- merge_profile —call→ pydantic_ai.ModelProfile · [pydantic_ai_slim/pydantic_ai/providers/groq.py:37-40](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/groq.py#L17-L60)
- zai_model_profile —call→ pydantic_ai.profiles.zai.zai_model_profile · [pydantic_ai_slim/pydantic_ai/providers/heroku.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/heroku.py#L23-L63)

### 架构线索 · pydantic/pydantic-ai
- token —call→ _AGENT_GRAPH_SLEEP.set · [pydantic_ai_slim/pydantic_ai/_agent_graph.py:255-255](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L235-L275)
- _AGENT_GRAPH_SLEEP.reset —call→ _AGENT_GRAPH_SLEEP.reset · [pydantic_ai_slim/pydantic_ai/_agent_graph.py:259-259](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L239-L279)
- sleep_func —call→ _AGENT_GRAPH_SLEEP.get · [pydantic_ai_slim/pydantic_ai/_agent_graph.py:264-264](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L244-L284)
- sleep_func —call→ sleep_func · [pydantic_ai_slim/pydantic_ai/_agent_graph.py:266-266](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_agent_graph.py#L246-L286)
- self._lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_cache_health.py:110-110](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L90-L130)
- _expected_cache_retention —call→ .profiles._expected_cache_retention · [pydantic_ai_slim/pydantic_ai/_cache_health.py:243-247](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L223-L267)
- _expected_cache_retention —call→ model.resolve_cache_retention · [pydantic_ai_slim/pydantic_ai/_cache_health.py:243-247](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L223-L267)
- input_tokens —call→ request_context.model._caching_not_enabled · [pydantic_ai_slim/pydantic_ai/_cache_health.py:255-266](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cache_health.py#L235-L286)
- self._lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_cancel.py:63-63](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cancel.py#L43-L83)
- self._lock —call→ threading.RLock · [pydantic_ai_slim/pydantic_ai/_cancel.py:136-136](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cancel.py#L116-L156)
- self._loop —call→ task.get_loop · [pydantic_ai_slim/pydantic_ai/_cancel.py:176-176](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cancel.py#L156-L196)
- running_loop —call→ asyncio.get_running_loop · [pydantic_ai_slim/pydantic_ai/_cancel.py:207-207](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_cancel.py#L187-L227)
- _parse_loaded_capabilities —call→ _parse_loaded_capabilities · [pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py:141-141](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py#L121-L161)
- parse_loaded_capabilities —call→ parse_loaded_capabilities · [pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py:157-157](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py#L137-L177)
- exchanges —call→ LoadExchanges · [pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py:162-162](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py#L142-L182)
- capability_id —call→ exchanges.loads · [pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py:163-163](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_deferred_capabilities.py#L143-L183)
- _banner_lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_display.py:24-24](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_display.py#L4-L44)
- _banner_lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_display.py:36-36](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_display.py#L16-L56)
- is_terminal —call→ detect_coding_agent · [pydantic_ai_slim/pydantic_ai/_display.py:182-182](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_display.py#L162-L202)
- any —call→ _agent_signal_matches · [pydantic_ai_slim/pydantic_ai/_display.py:198-199](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_display.py#L178-L219)
- messages.append —call→ .messages.ModelRequest · [pydantic_ai_slim/pydantic_ai/_enqueue.py:108-108](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_enqueue.py#L88-L128)
- self._lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_enqueue.py:224-224](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_enqueue.py#L204-L244)
- self._capability_loads.extend —call→ self._capability_loads.extend · [pydantic_ai_slim/pydantic_ai/_enqueue.py:273-273](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_enqueue.py#L253-L293)
- self._capability_loads.clear —call→ self._capability_loads.clear · [pydantic_ai_slim/pydantic_ai/_enqueue.py:291-291](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_enqueue.py#L271-L311)
- guarded —call→ functools.wraps · [pydantic_ai_slim/pydantic_ai/_event_registry.py:166-171](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_event_registry.py#L146-L191)
- unknown_schema —call→ _gather_unknown_payload · [pydantic_ai_slim/pydantic_ai/_event_registry.py:255-259](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_event_registry.py#L235-L279)
- self.attempts.extend —call→ ._model_request_attempts.carried_attempts · [pydantic_ai_slim/pydantic_ai/_fallback.py:281-281](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_fallback.py#L261-L301)
- attempt —call→ ._model_request_attempts.failed_attempt · [pydantic_ai_slim/pydantic_ai/_fallback.py:282-282](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_fallback.py#L262-L302)
- ._model_request_attempts.record_attempt_span —call→ ._model_request_attempts.record_attempt_span · [pydantic_ai_slim/pydantic_ai/_fallback.py:285-293](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_fallback.py#L265-L313)
- self.rejected_responses.append —call→ self.rejected_responses.append · [pydantic_ai_slim/pydantic_ai/_fallback.py:329-329](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_fallback.py#L309-L349)
- MODEL_VISIBLE_NAME.fullmatch —call→ MODEL_VISIBLE_NAME.fullmatch · [pydantic_ai_slim/pydantic_ai/_framing.py:172-173](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_framing.py#L152-L193)
- _registration_lock —call→ threading.Lock · [pydantic_ai_slim/pydantic_ai/_framing.py:186-186](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_framing.py#L166-L206)
- model_visible_name_error —call→ model_visible_name_error · [pydantic_ai_slim/pydantic_ai/_framing.py:225-226](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_framing.py#L205-L246)
- model_visible_name_error —call→ model_visible_name_error · [pydantic_ai_slim/pydantic_ai/_framing.py:289-290](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_framing.py#L269-L310)
- await_maybe —call→ ._utils.run_in_executor · [pydantic_ai_slim/pydantic_ai/_function_schema.py:96-96](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_function_schema.py#L76-L116)
- metadata —call→ ._utils.is_model_like · [pydantic_ai_slim/pydantic_ai/_function_schema.py:333-333](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_function_schema.py#L313-L353)
- takes_run_context —call→ ._utils.takes_run_context · [pydantic_ai_slim/pydantic_ai/_function_schema.py:361-361](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_function_schema.py#L341-L381)
- name —call→ functools.partial · [pydantic_ai_slim/pydantic_ai/_function_schema.py:400-408](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_function_schema.py#L380-L428)
- ._utils.is_str_dict —call→ block.get · [pydantic_ai_slim/pydantic_ai/_gateway_cost.py:27-28](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_gateway_cost.py#L7-L48)
- _ —call→ find_provider_model · [pydantic_ai_slim/pydantic_ai/_genai_prices.py:77-79](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/_genai_prices.py#L57-L99)

### 架构线索 · agno-agi/agno
- agno.exceptions.ModelAuthenticationError —call→ agno.exceptions.ModelAuthenticationError · [libs/agno/agno/models/openai/chat.py:110-113](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L90-L133)
- self.client —call→ openai.OpenAI · [libs/agno/agno/models/openai/chat.py:157-157](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L137-L177)
- self.async_client —call→ openai.AsyncOpenAI · [libs/agno/agno/models/openai/chat.py:185-185](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L165-L205)
- schema —call→ agno.utils.models.schema_utils.get_response_schema_for_provider · [libs/agno/agno/models/openai/chat.py:233-233](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L213-L253)
- model_dict.update —call→ model_dict.update · [libs/agno/agno/models/openai/chat.py:279-303](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L259-L323)
- cleaned_dict —call→ model_dict.items · [libs/agno/agno/models/openai/chat.py:304-304](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L284-L324)
- extend —call→ agno.utils.openai.images_to_message · [libs/agno/agno/models/openai/chat.py:346-346](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L326-L366)
- extend —call→ agno.utils.openai.audio_to_message · [libs/agno/agno/models/openai/chat.py:349-349](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L329-L369)
- file_part —call→ agno.utils.openai._format_file_for_message · [libs/agno/agno/models/openai/chat.py:372-372](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L352-L392)
- normalized —call→ agno.utils.message.reformat_tool_call_ids · [libs/agno/agno/models/openai/chat.py:389-389](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L369-L409)
- provider_response —call→ chat.completions.create · [libs/agno/agno/models/openai/chat.py:419-425](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L399-L445)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:444-449](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L424-L469)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:452-452](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L432-L472)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:470-475](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L450-L495)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:481-481](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L461-L501)
- response —call→ chat.completions.create · [libs/agno/agno/models/openai/chat.py:509-515](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L489-L535)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:534-539](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L514-L559)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:542-542](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L522-L562)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:560-565](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L540-L585)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:571-571](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L551-L591)
- Model.get_provider —call→ agno.models.base.Model.get_provider · [libs/agno/agno/models/openai/like.py:31-31](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/like.py#L11-L31)
- message —call→ message.model_copy · [libs/agno/agno/models/openai/responses.py:156-156](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L136-L176)
- agno.exceptions.ModelAuthenticationError —call→ agno.exceptions.ModelAuthenticationError · [libs/agno/agno/models/openai/responses.py:211-214](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L191-L234)
- self.client —call→ openai.OpenAI · [libs/agno/agno/models/openai/responses.py:253-253](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L233-L273)
- self.async_client —call→ openai.AsyncOpenAI · [libs/agno/agno/models/openai/responses.py:273-273](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L253-L293)
- response —call→ client.responses.retrieve · [libs/agno/agno/models/openai/responses.py:284-284](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L264-L304)
- client.responses.cancel —call→ client.responses.cancel · [libs/agno/agno/models/openai/responses.py:293-293](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L273-L313)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/responses.py:296-300](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L276-L320)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:301-301](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L281-L321)
- response —call→ client.responses.retrieve · [libs/agno/agno/models/openai/responses.py:311-311](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L291-L331)
- client.responses.cancel —call→ client.responses.cancel · [libs/agno/agno/models/openai/responses.py:320-320](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L300-L340)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/responses.py:323-327](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L303-L347)
- asyncio.sleep —call→ asyncio.sleep · [libs/agno/agno/models/openai/responses.py:328-328](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L308-L348)
- schema —call→ agno.utils.models.schema_utils.get_response_schema_for_provider · [libs/agno/agno/models/openai/responses.py:385-385](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L365-L405)
- tools.insert —call→ tools.insert · [libs/agno/agno/models/openai/responses.py:430-430](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L410-L450)
- self._using_reasoning_model —call→ self._using_reasoning_model · [libs/agno/agno/models/openai/responses.py:440-465](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L420-L485)
- self._chains_responses —call→ self._chains_responses · [libs/agno/agno/models/openai/responses.py:443-465](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L423-L485)
- file_content —read→ file_path.read_bytes · [libs/agno/agno/models/openai/responses.py:561-561](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L541-L581)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:585-585](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L565-L605)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:598-598](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L578-L618)

### 扫描范围 · pydantic/pydantic-ai
文件 24，覆盖完整：False；缺口：文本文件尝试次数达到 24 上限，仍有文件未扫描。；线索超过 40 项，仅保留前 40 项，其他线索未展开。

### 扫描范围 · pydantic/pydantic-ai
文件 24，覆盖完整：False；缺口：目录数达到 24 上限，仍有目录未扫描。；文本文件尝试次数达到 24 上限，仍有文件未扫描。；线索超过 40 项，仅保留前 40 项，其他线索未展开。

### 扫描范围 · agno-agi/agno
文件 6，覆盖完整：False；缺口：线索超过 40 项，仅保留前 40 项，其他线索未展开。
## 问题
继续沿用固定提交，聚焦文件内直接参数转交：Pydantic AI 的 pydantic_ai_slim/pydantic_ai/providers/openai.py 是否把 base_url 传给客户端创建函数；Agno 的 libs/agno/agno/models/openai/chat.py 是否把 base_url 放入参数字典，并由 OpenAIClient 取得该字典。请自动定位并引用源码，不延伸判断外部 SDK 或远端服务的运行行为。

## 结果

### pydantic/pydantic-ai @ e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a

- **C1 · PASS**：指定文件 pydantic_ai_slim/pydantic_ai/providers/openai.py 第 225 行将 base_url 以同名关键字直接传给客户端创建函数 self._create_openai_client，并将返回值赋给 self._client，满足文件内参数转交要求；不据此推断外部 SDK 或远端服务行为 [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091]。
  - 依据：static_config；需运行验证：False
  - 下一步：本项仅核查静态参数转交，无需运行验证；若另需确认实际请求地址，再单独开展 SDK 与网络行为验证。
  - [ev_9d10ea444f3e89954564790d7e45e5b9650a8dadb5654010ddd35bad4dd2e091](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L225-L225)：`self._client = self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)`

### agno-agi/agno @ 878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1

- **C1 · PASS**：指定文件内存在参数字典转交路径：self.base_url 放入 base_params，过滤 None 后生成 client_params，并允许 self.client_params 覆盖同名值。[ev_ceaa40d4dc1ede8ae364a97900c9f43d001c5fe35041b3e2ab5bd3e8cf96dd5d] 创建客户端时调用 self._get_client_params()，再以 OpenAIClient(**client_params) 接收参数。因此非 None 且未被覆盖的 base_url 会进入该构造调用；此判断仅涉及静态参数转交。[ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2]
  - 依据：static_config；需运行验证：False
  - 下一步：本项静态参数转交核查已完成，无需运行验证；外部 SDK 如何处理地址以及远端请求行为不在本项结论范围内。
  - [ev_ceaa40d4dc1ede8ae364a97900c9f43d001c5fe35041b3e2ab5bd3e8cf96dd5d](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L116-L132)：`base_params = {
            "api_key": self.api_key,
            "organization": self.organization,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "default_headers": self.default_headers,
            "default_query": self.default_query,
        }

        # Create client_params dict with non-None values
        client_params = {k: v for k, v in base_params.items() if v is not None}

        # Add additional client params if provided
        if self.client_params:
            client_params.update(self.client_params)
        return client_params`
  - [ev_d089e5cdcc12e0e8a3173bbf2abc4f701e573daa1aa8a5998f4086b9a35e53c2](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L146-L157)：`client_params: Dict[str, Any] = self._get_client_params()
        if self.http_client:
            if isinstance(self.http_client, httpx.Client):
                client_params["http_client"] = self.http_client
            else:
                log_warning("http_client is not an instance of httpx.Client. Ignoring and using OpenAI SDK default.")
        # When no custom http_client is provided, let the OpenAI SDK use its own default client.
        # The SDK defaults to HTTP/1.1 which avoids transient 400 errors caused by HTTP/2
        # protocol edge cases with OpenAI's infrastructure.

        # Create and cache the client
        self.client = OpenAIClient(**client_params)`

在各自固定提交及指定 OpenAI 接入文件内，两仓库均通过 C1 静态参数转交核查。pydantic/pydantic-ai 将 base_url 以同名关键字直接传给 self._create_openai_client；agno-agi/agno 则将 self.base_url 放入参数字典，过滤 None 并合并可覆盖同名值的 self.client_params 后，通过 OpenAIClient(**client_params) 转交。因此，前者为直接传参，后者为字典转交，且原 base_url 的保留受非 None 和未被覆盖条件限制。结论仅涉及文件内参数转交，不推断外部 SDK 或远端服务的运行行为。

### 架构线索 · pydantic/pydantic-ai
- anyio.Lock —call→ anyio.Lock · [pydantic_ai_slim/pydantic_ai/providers/__init__.py:86-86](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/__init__.py#L66-L106)
- self.model_profile —call→ self.model_profile · [pydantic_ai_slim/pydantic_ai/providers/__init__.py:185-185](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/__init__.py#L165-L205)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py:53-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py#L33-L74)
- model_name.removeprefix —call→ model_name.removeprefix · [pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py:54-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_bedrock_model_names.py#L34-L74)
- anyio.sleep —call→ anyio.sleep · [pydantic_ai_slim/pydantic_ai/providers/_github_copilot_oauth.py:109-109](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_github_copilot_oauth.py#L89-L129)
- self.wfile.write —write→ self.wfile.write · [pydantic_ai_slim/pydantic_ai/providers/_oauth.py:112-112](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth.py#L92-L132)
- cancelled —call→ threading.Event · [pydantic_ai_slim/pydantic_ai/providers/_oauth.py:117-117](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth.py#L97-L137)
- claims.validate_python —call→ json.loads · [pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py:128-128](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py#L108-L148)
- self._client —call→ openai.AsyncOpenAI · [pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py:326-331](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_oauth_provider.py#L306-L351)
- AsyncOpenAI —call→ openai.AsyncOpenAI · [pydantic_ai_slim/pydantic_ai/providers/_openai_compatible.py:51-56](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/_openai_compatible.py#L31-L64)
- base_profile —call→ pydantic_ai.profiles.qwen.qwen_model_profile · [pydantic_ai_slim/pydantic_ai/providers/alibaba.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/alibaba.py#L23-L63)
- openai_profile —call→ pydantic_ai.profiles.openai.OpenAIModelProfile · [pydantic_ai_slim/pydantic_ai/providers/alibaba.py:48-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/alibaba.py#L28-L74)
- bedrock_provider —call→ pydantic_ai.providers._bedrock_model_names.split_bedrock_model_id · [pydantic_ai_slim/pydantic_ai/providers/anthropic.py:154-154](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/anthropic.py#L134-L174)
- profile —call→ pydantic_ai.profiles.anthropic.anthropic_model_profile · [pydantic_ai_slim/pydantic_ai/providers/anthropic.py:157-157](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/anthropic.py#L137-L177)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/azure.py:122-122](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/azure.py#L102-L142)
- route_profile —call→ pydantic_ai.profiles._special_tokens.special_token_route_profile · [pydantic_ai_slim/pydantic_ai/providers/azure.py:137-137](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/azure.py#L117-L157)
- downstream —call→ pydantic_ai.profiles.anthropic.anthropic_model_profile · [pydantic_ai_slim/pydantic_ai/providers/bedrock.py:370-370](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock.py#L350-L390)
- profile —call→ BedrockModelProfile · [pydantic_ai_slim/pydantic_ai/providers/bedrock.py:375-398](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock.py#L355-L418)
- provider —call→ pydantic_ai.providers._bedrock_model_names.split_bedrock_model_id · [pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py#L23-L63)
- base_model_name.startswith —call→ base_model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py:49-54](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/bedrock_mantle.py#L29-L74)
- model_name_lower —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/cerebras.py:64-64](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cerebras.py#L44-L84)
- model_name_lower.startswith —call→ model_name_lower.startswith · [pydantic_ai_slim/pydantic_ai/providers/cerebras.py:66-68](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cerebras.py#L46-L88)
- profile —call→ pydantic_ai.profiles.cohere.cohere_model_profile · [pydantic_ai_slim/pydantic_ai/providers/cohere.py:48-48](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cohere.py#L28-L68)
- profile —call→ pydantic_ai.ModelProfile · [pydantic_ai_slim/pydantic_ai/providers/cohere.py:48-48](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/cohere.py#L28-L68)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/crusoe.py:64-64](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/crusoe.py#L44-L84)
- vendor —call→ model_name.split · [pydantic_ai_slim/pydantic_ai/providers/crusoe.py:66-66](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/crusoe.py#L46-L86)
- profile —call→ pydantic_ai.profiles.deepseek.deepseek_model_profile · [pydantic_ai_slim/pydantic_ai/providers/deepseek.py:49-49](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/deepseek.py#L29-L69)
- is_flash_or_v4 —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/deepseek.py:50-50](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/deepseek.py#L30-L70)
- model_name —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/fireworks.py:52-52](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/fireworks.py#L32-L72)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/fireworks.py:65-70](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/fireworks.py#L45-L90)
- route —call→ _gateway_route · [pydantic_ai_slim/pydantic_ai/providers/gateway.py:165-165](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/gateway.py#L145-L185)
- _build_gateway_provider —call→ .openai.OpenAIProvider · [pydantic_ai_slim/pydantic_ai/providers/gateway.py:185-191](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/gateway.py#L165-L211)
- openai_model_profile —call→ pydantic_ai.profiles.openai.openai_model_profile · [pydantic_ai_slim/pydantic_ai/providers/github.py:73-73](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github.py#L53-L93)
- provider —call→ model_name.lower · [pydantic_ai_slim/pydantic_ai/providers/github.py:75-75](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github.py#L55-L95)
- overlay —call→ pydantic_ai.profiles.openai.OpenAIModelProfile · [pydantic_ai_slim/pydantic_ai/providers/github_copilot.py:81-89](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github_copilot.py#L61-L109)
- model_name.startswith —call→ model_name.startswith · [pydantic_ai_slim/pydantic_ai/providers/github_copilot.py:91-116](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/github_copilot.py#L71-L136)
- google_model_profile —call→ pydantic_ai.profiles.google.google_model_profile · [pydantic_ai_slim/pydantic_ai/providers/google.py:80-80](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/google.py#L60-L100)
- google_realtime_model_profile —call→ pydantic_ai.profiles.google.google_realtime_model_profile · [pydantic_ai_slim/pydantic_ai/providers/google.py:84-84](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/google.py#L64-L104)
- merge_profile —call→ pydantic_ai.ModelProfile · [pydantic_ai_slim/pydantic_ai/providers/groq.py:37-40](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/groq.py#L17-L60)
- zai_model_profile —call→ pydantic_ai.profiles.zai.zai_model_profile · [pydantic_ai_slim/pydantic_ai/providers/heroku.py:43-43](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/heroku.py#L23-L63)

### 架构线索 · agno-agi/agno
- agno.exceptions.ModelAuthenticationError —call→ agno.exceptions.ModelAuthenticationError · [libs/agno/agno/models/openai/chat.py:110-113](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L90-L133)
- self.client —call→ openai.OpenAI · [libs/agno/agno/models/openai/chat.py:157-157](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L137-L177)
- self.async_client —call→ openai.AsyncOpenAI · [libs/agno/agno/models/openai/chat.py:185-185](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L165-L205)
- schema —call→ agno.utils.models.schema_utils.get_response_schema_for_provider · [libs/agno/agno/models/openai/chat.py:233-233](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L213-L253)
- model_dict.update —call→ model_dict.update · [libs/agno/agno/models/openai/chat.py:279-303](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L259-L323)
- cleaned_dict —call→ model_dict.items · [libs/agno/agno/models/openai/chat.py:304-304](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L284-L324)
- extend —call→ agno.utils.openai.images_to_message · [libs/agno/agno/models/openai/chat.py:346-346](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L326-L366)
- extend —call→ agno.utils.openai.audio_to_message · [libs/agno/agno/models/openai/chat.py:349-349](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L329-L369)
- file_part —call→ agno.utils.openai._format_file_for_message · [libs/agno/agno/models/openai/chat.py:372-372](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L352-L392)
- normalized —call→ agno.utils.message.reformat_tool_call_ids · [libs/agno/agno/models/openai/chat.py:389-389](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L369-L409)
- provider_response —call→ chat.completions.create · [libs/agno/agno/models/openai/chat.py:419-425](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L399-L445)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:444-449](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L424-L469)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:452-452](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L432-L472)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:470-475](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L450-L495)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:481-481](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L461-L501)
- response —call→ chat.completions.create · [libs/agno/agno/models/openai/chat.py:509-515](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L489-L535)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:534-539](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L514-L559)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:542-542](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L522-L562)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:560-565](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L540-L585)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/chat.py:571-571](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/chat.py#L551-L591)
- Model.get_provider —call→ agno.models.base.Model.get_provider · [libs/agno/agno/models/openai/like.py:31-31](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/like.py#L11-L31)
- message —call→ message.model_copy · [libs/agno/agno/models/openai/responses.py:156-156](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L136-L176)
- agno.exceptions.ModelAuthenticationError —call→ agno.exceptions.ModelAuthenticationError · [libs/agno/agno/models/openai/responses.py:211-214](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L191-L234)
- self.client —call→ openai.OpenAI · [libs/agno/agno/models/openai/responses.py:253-253](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L233-L273)
- self.async_client —call→ openai.AsyncOpenAI · [libs/agno/agno/models/openai/responses.py:273-273](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L253-L293)
- response —call→ client.responses.retrieve · [libs/agno/agno/models/openai/responses.py:284-284](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L264-L304)
- client.responses.cancel —call→ client.responses.cancel · [libs/agno/agno/models/openai/responses.py:293-293](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L273-L313)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/responses.py:296-300](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L276-L320)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:301-301](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L281-L321)
- response —call→ client.responses.retrieve · [libs/agno/agno/models/openai/responses.py:311-311](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L291-L331)
- client.responses.cancel —call→ client.responses.cancel · [libs/agno/agno/models/openai/responses.py:320-320](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L300-L340)
- agno.exceptions.ModelProviderError —call→ agno.exceptions.ModelProviderError · [libs/agno/agno/models/openai/responses.py:323-327](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L303-L347)
- asyncio.sleep —call→ asyncio.sleep · [libs/agno/agno/models/openai/responses.py:328-328](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L308-L348)
- schema —call→ agno.utils.models.schema_utils.get_response_schema_for_provider · [libs/agno/agno/models/openai/responses.py:385-385](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L365-L405)
- tools.insert —call→ tools.insert · [libs/agno/agno/models/openai/responses.py:430-430](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L410-L450)
- self._using_reasoning_model —call→ self._using_reasoning_model · [libs/agno/agno/models/openai/responses.py:440-465](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L420-L485)
- self._chains_responses —call→ self._chains_responses · [libs/agno/agno/models/openai/responses.py:443-465](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L423-L485)
- file_content —read→ file_path.read_bytes · [libs/agno/agno/models/openai/responses.py:561-561](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L541-L581)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:585-585](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L565-L605)
- time.sleep —call→ time.sleep · [libs/agno/agno/models/openai/responses.py:598-598](https://github.com/agno-agi/agno/blob/878151ba85c7bec6f0df7edfa1bbc0e025fdd5c1/libs/agno/agno/models/openai/responses.py#L578-L618)

### 扫描范围 · pydantic/pydantic-ai
文件 24，覆盖完整：False；缺口：文本文件尝试次数达到 24 上限，仍有文件未扫描。；线索超过 40 项，仅保留前 40 项，其他线索未展开。

### 扫描范围 · agno-agi/agno
文件 6，覆盖完整：False；缺口：线索超过 40 项，仅保留前 40 项，其他线索未展开。
