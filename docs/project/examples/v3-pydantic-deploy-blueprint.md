# 仓库尽调报告

会话：d4c99beacbd8443d9b9fbe7cf091ae58
状态：COMPLETED

## 问题
核查 Python 3.11 版本声明和自定义 OpenAI 模型网关地址配置。查看 pyproject.toml 与 pydantic_ai_slim/pydantic_ai/providers/openai.py，给出带证据的约束矩阵、可复制的最小适配配置示例，以及安装和连接仍需运行验证的步骤。

## 结果

### pydantic/pydantic-ai @ e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a

- **C1 · PASS**：pyproject.toml 声明 requires-python 为 >=3.11，包含 Python 3.11；此结论仅针对版本声明。[ev_27c3f8c9463db202c4afa5bd0e491b9070970071a583fe9ded2aac28396733c2]
  - 依据：declaration；需运行验证：False
  - 下一步：声明核查已完成，无需运行验证。
  - [ev_27c3f8c9463db202c4afa5bd0e491b9070970071a583fe9ded2aac28396733c2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pyproject.toml#L48-L48)：`requires-python = ">=3.11"`

- **C2 · PASS**：OpenAIProvider.__init__ 支持通过 base_url 配置自定义网关，也声明支持 OPENAI_BASE_URL 环境变量；api_key 可显式传入或取自 OPENAI_API_KEY。自定义地址且未提供密钥时，实现会补入占位密钥，但实际网关可能仍要求有效凭据。传入 openai_client 时不得同时指定 base_url、api_key 或 http_client。以上为静态实现核查，未验证网关联通性。[ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2]
  - 依据：static_config；需运行验证：True
  - 下一步：设置实际网关地址和凭据，构造 OpenAIProvider 后执行一次最小模型请求，验证路由、认证及协议兼容性。
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        openai_client: AsyncOpenAI | None = None,
        http_client: _OpenAIHTTPClient | None = None,
    ) -> None:`
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`base_url: The base url for the OpenAI requests. If not provided, the `OPENAI_BASE_URL` environment variable
                will be used if available. Otherwise, defaults to OpenAI's base url.
            api_key: The API key to use for authentication, if not provided, the `OPENAI_API_KEY` environment variable
                will be used if available.`
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`api_key = 'api-key-not-set'`
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`if openai_client is not None:
            assert base_url is None, 'Cannot provide both `openai_client` and `base_url`'
            assert http_client is None, 'Cannot provide both `openai_client` and `http_client`'
            assert api_key is None, 'Cannot provide both `openai_client` and `api_key`'
            self._client = openai_client
        else:
            self._client = self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)`

pydantic/pydantic-ai 的两项核查均通过：pyproject.toml 声明 requires-python = ">=3.11"，包含 Python 3.11，但此结论仅限版本声明。pydantic_ai_slim/pydantic_ai/providers/openai.py 中的 OpenAIProvider 支持通过 base_url 或 OPENAI_BASE_URL 配置自定义 OpenAI 网关，认证密钥可通过 api_key 或 OPENAI_API_KEY 提供；自定义地址未提供密钥时实现会填入占位密钥，实际网关仍可能要求有效凭据。也可传入 openai_client，但不得同时指定 base_url、api_key 或 http_client。网关支持结论来自静态实现核查，实际连通性、认证及协议兼容性仍需使用真实网关执行最小模型请求验证。
## 问题
把已确认的版本声明与模型地址参数整理为使用前检查清单，指出示例中的用户自填项。

## 结果

### pydantic/pydantic-ai @ e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a

- **C1 · PASS**：pyproject.toml 声明 requires-python = ">=3.11"，范围包含 Python 3.11。本结论仅确认版本声明，不代表依赖安装或运行已验证。[ev_27c3f8c9463db202c4afa5bd0e491b9070970071a583fe9ded2aac28396733c2]
  - 依据：declaration；需运行验证：True
  - 下一步：在 Python 3.11 隔离环境中安装该固定提交及所需 OpenAI 依赖，检查依赖解析、导入和最小调用；这些运行结果不属于本次声明核查。
  - [ev_27c3f8c9463db202c4afa5bd0e491b9070970071a583fe9ded2aac28396733c2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pyproject.toml#L48-L48)：`requires-python = ">=3.11"`

- **C2 · PASS**：OpenAIProvider 支持显式 base_url、api_key，也声明未显式提供时分别使用 OPENAI_BASE_URL、OPENAI_API_KEY；地址均未配置时默认使用 OpenAI 地址。未提供 api_key、环境中不存在 OPENAI_API_KEY 且未传入 openai_client 时：若地址及其环境变量也未配置则抛出缺少密钥错误，否则补入 'api-key-not-set'，这不代表能通过网关认证。传入 openai_client 时，base_url、api_key、http_client 必须均为 None，实现以 assert 检查，随后直接采用该客户端。环境变量条件检查的是是否存在，而不是值是否非空。以上为静态实现与接口声明，未验证网关兼容性。[ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2]
  - 依据：static_config；需运行验证：True
  - 下一步：用户须填写网关实际基础地址和网关支持的模型名称；需要认证时填写有效密钥。模型名称应在模型构造接口中指定，不是此 Provider 的参数。运行验证依赖安装、DNS/TLS、地址路径、认证和最小模型请求；无需认证的网关应另测占位密钥是否被接受。
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`base_url: The base url for the OpenAI requests. If not provided, the `OPENAI_BASE_URL` environment variable
                will be used if available. Otherwise, defaults to OpenAI's base url.
            api_key: The API key to use for authentication, if not provided, the `OPENAI_API_KEY` environment variable
                will be used if available.`
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`if api_key is None and 'OPENAI_API_KEY' not in os.environ and openai_client is None:
            if base_url is None and 'OPENAI_BASE_URL' not in os.environ:
                # When talking to OpenAI directly, a missing key would otherwise surface as a raw
                # `openai.OpenAIError`; raise our own `UserError` instead so the message is consistent with
                # other providers and points newcomers to the keyless test model.
                raise missing_api_key_error(
                    'Set the `OPENAI_API_KEY` environment variable or pass it via '
                    f'`{type(self).__name__}(api_key=...)` to use the OpenAI provider.'
                )
            else:
                # This is a workaround for the OpenAI client requiring an API key, whilst locally served,
                # openai compatible models do not always need an API key, but a placeholder (non-empty) key is required.
                api_key = 'api-key-not-set'`
  - [ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`if openai_client is not None:
            assert base_url is None, 'Cannot provide both `openai_client` and `base_url`'
            assert http_client is None, 'Cannot provide both `openai_client` and `http_client`'
            assert api_key is None, 'Cannot provide both `openai_client` and `api_key`'
            self._client = openai_client
        else:
            self._client = self._create_openai_client(base_url=base_url, api_key=api_key, http_client=http_client)`

pydantic/pydantic-ai（提交 e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a）两项核查均通过。C1：pyproject.toml 声明 requires-python = ">=3.11"，包含 Python 3.11，但尚未验证安装及运行。C2：依据 pydantic_ai_slim/pydantic_ai/providers/openai.py，OpenAIProvider 支持自定义网关：可显式传入 base_url、api_key，未提供时分别读取 OPENAI_BASE_URL、OPENAI_API_KEY；地址均未配置时默认使用 OpenAI 地址。未传入 openai_client、未提供 api_key 且 OPENAI_API_KEY 不存在时，若地址也未配置则抛出缺少密钥错误，否则自动使用占位密钥 'api-key-not-set'，不保证通过网关认证。环境变量判断依据是是否存在，而非是否为空。注入 openai_client 时，base_url、api_key、http_client 必须均为 None，由 assert 检查。环境变量配置示例：OPENAI_BASE_URL="<用户填写：网关实际基础地址>"；需要认证时设置 OPENAI_API_KEY="<用户填写：有效认证密钥>"，无需认证时应删除该变量而非设为空字符串。用户还须在应用的模型构造配置中填写网关支持的模型名称，该名称不是 Provider 参数。上述示例仅配置环境变量；实际安装、网关路径、TLS、认证及最小模型请求仍需运行验证。

### 配置示例 · pydantic/pydantic-ai
依据范围：pydantic/pydantic-ai @ e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a
模型提出的适用条件（待核验）：用于未显式传入 base_url、api_key 且未注入 openai_client 的配置路径。若网关无需认证，可不设置 OPENAI_API_KEY；须确保该变量确实不存在，而非设为空字符串。模型名称仍须由用户填写到应用的模型配置中；本示例仅配置 Provider 环境变量，不是完整请求程序。

```env
OPENAI_BASE_URL="<用户填写：网关实际基础地址>"
OPENAI_API_KEY="<用户填写：网关要求的有效认证密钥>"
```

- 替换网关地址占位符，并依据网关要求保留或删除密钥变量。
- 在 Python 3.11 隔离环境中验证固定提交的安装和导入。
- 在应用模型配置中填写网关实际支持的模型名称。
- 发起最小请求，验证路径、TLS、认证及 OpenAI 接口兼容性；不得将占位密钥视为有效认证凭据。
- 配置依据：[ev_c903e5c3963ac33824c0f873678f2e57ac5897ad80ccfd673db269a7afda01b2](https://github.com/pydantic/pydantic-ai/blob/e65f5e9ac8ca01ffd1ad8c91d6f5a006d10d250a/pydantic_ai_slim/pydantic_ai/providers/openai.py#L170-L225)：`base_url: The base url for the OpenAI requests. If not provided, the `OPENAI_BASE_URL` environment variable
                will be used if available. Otherwise, defaults to OpenAI's base url.
            api_key: The API key to use for authentication, if not provided, the `OPENAI_API_KEY` environment variable
                will be used if available.`
