# codex-bootstrap

在 EC2 上通过实例角色配置 Codex CLI 与 Amazon Bedrock Runtime，不复制 API 密钥或静态 AWS 凭证。
仓库提供配置生成、完整模型目录和只读连接验证；Codex CLI 和 AWS CLI 需提前安装。

## 适用配置

- 平台：EC2，Linux ARM64。
- 默认区域：`us-west-2`；这是配置默认值，不是部署位置记录。
- Codex：`0.154.0`，用户级安装到 `~/.local`。
- 认证：EC2 实例角色，无需 API 密钥或静态 AK/SK。
- Runtime：`https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1`。
- 模型目录：`us.openai.gpt-6-astra`、`us.openai.gpt-5.6-sol`、`us.openai.gpt-5.6-terra`、`us.openai.gpt-5.6-luna`。

本项目面向 Linux CLI，不配置图形桌面。模型可用性及调用权限需在自己的环境中验证。

## 文件清单

### 仓库文件

| 文件 | 用途 |
| --- | --- |
| `bootstrap.py` | 生成用户配置和模型目录，拒绝覆盖已有文件 |
| `smoke.py` | 对一个指定模型执行有超时限制的只读验证 |
| `bedrock-models.json` | 四个已验证模型的完整元数据 |
| `config.example.toml` | 手动配置参考，使用前替换绝对路径占位符 |
| `README.md` | 安装、验证和排障说明 |
| `AGENTS.md` | 贡献者指南 |

`result-*.json`、`smoke-workspace/` 和 Python 缓存是本地产物，不纳入版本控制。
测试结果包含调用者 ARN，可能暴露 AWS 账号、角色和实例标识；分享前必须脱敏。
公有仓库不保存真实用户名、主机地址、账号标识、部署日志或凭证。

### 用户目录中的配置

| 文件 | 用途 | 是否必需 |
| --- | --- | --- |
| `~/.codex/config.toml` | 默认模型、Runtime 端点、region、权限和网页搜索设置 | 是 |
| `~/.codex/model-catalogs/bedrock-models.json` | 四模型目录及完整模型元数据 | 要复现当前四模型菜单时使用 |
| `~/.bashrc` | 确保 `~/.local/bin` 在 PATH 中 | 仅 PATH 缺失且未添加过脚本标记时修改 |
| `~/.codex/.env` | API 密钥模式的环境变量 | 实例角色模式不需要 |
| `~/.aws/credentials` | 静态 AWS 凭证文件 | 实例角色模式不需要，也不建议为此创建 |

不要直接复制其他机器的整个 `~/.codex/config.toml`。
其中的本地路径、通知程序、Computer Use 和 MCP 启动命令可能不适用于目标 Linux 环境。

## 1. 前置条件

1. 已安装 Node.js >= 16、npm、Python 3 和 AWS CLI。
2. EC2 已绑定允许调用目标模型及 US 跨区域推理的实例角色。
3. 能通过现有网络访问安装源、Bedrock Runtime HTTPS 端点和实例元数据服务。

先检查：

```bash
node --version
npm --version
python3 --version
aws sts get-caller-identity
```

`get-caller-identity` 应返回该实例角色的 assumed-role 身份，但 STS 成功本身不证明
具有模型调用权限，仍需执行第 4 步。不要将该命令的原始输出贴到公开 Issue 或日志中。
脚本不会修改 IAM；应单独评审最小权限，不要为运行本项目直接授予管理员权限。
本流程不需要新增任何公网入站端口。

## 2. 安装已验证的 Codex 版本

在 EC2 上执行：

```bash
npm install --global --prefix "$HOME/.local" --ignore-scripts --no-audit --no-fund @openai/codex@0.154.0
export PATH="$HOME/.local/bin:$PATH"
codex --version
```

这是用户级安装，不需要 `sudo npm install -g`。
固定 0.154.0 是为了复现本次验证结果，不代表必须永久停留在该版本。
以后更新 CLI 后，应重新执行四模型验证。

## 3. 写入配置

### 自动生成

将仓库克隆到 EC2，或将 `bootstrap.py`、`smoke.py` 和 `bedrock-models.json` 上传到同一目录。
然后在该目录执行：

```bash
python3 bootstrap.py
```

脚本会根据当前用户 HOME 生成绝对路径。它发现已有 `config.toml` 或同名模型目录文件时会拒绝覆盖。
有现存配置的机器应先备份并合并，不能直接重复运行此脚本覆盖用户设置。

如果 PATH 缺失，脚本会先备份 `.bashrc`，再添加 `~/.local/bin`；此时重新登录，
或在当前 shell 执行 `export PATH="$HOME/.local/bin:$PATH"`。

### 生成的 config.toml

以下为通用配置示例，同目录另附 `config.example.toml`。
手动配置时，必须将 `model_catalog_json` 的占位符替换为当前用户模型目录文件的绝对路径。
不要直接填入 `$HOME` 并假定 TOML 会展开环境变量；`bootstrap.py` 会自动生成正确路径。

```toml
model = "us.openai.gpt-6-astra"
model_provider = "amazon-bedrock-runtime"
model_reasoning_effort = "high"
web_search = "disabled"
approval_policy = "on-request"
sandbox_mode = "workspace-write"
model_catalog_json = "/absolute/path/to/.codex/model-catalogs/bedrock-models.json"

[model_providers.amazon-bedrock-runtime]
base_url = "https://bedrock-runtime.us-west-2.amazonaws.com/openai/v1"
wire_api = "responses"

[model_providers.amazon-bedrock-runtime.aws]
region = "us-west-2"

[model_providers.amazon-bedrock.aws]
region = "us-west-2"
```

注意：

- 实际选中的 provider 是 `amazon-bedrock-runtime`；补充 `amazon-bedrock.aws.region`
  是为了兼容仍会读取原 provider region 的客户端，不代表调用切回 Mantle。
- Endpoint 中的 region 与这两处 region 保持一致。
- 模型 ID 使用 `us.` 前缀。模型列表是目录，不会授予模型访问权限。
- `web_search = "disabled"` 是此 Runtime 配置的默认值，不是对所有 provider 的通用要求。
- 不需要 `codex login` 获取 OpenAI API key；本方案通过 AWS 实例角色访问 Bedrock。
- 不在 `.env`、shell 配置或命令行参数中保存长期 AK/SK。
- `bedrock-models.json` 保留完整元数据，不要随意简化成只有模型名称的 JSON 数组。

权限检查：

```bash
chmod 700 "$HOME/.codex"
chmod 600 "$HOME/.codex/config.toml"
chmod 600 "$HOME/.codex/model-catalogs/bedrock-models.json"
```

## 4. 实际验证四个模型

使用同目录中的验证脚本：

```bash
for model in us.openai.gpt-6-astra us.openai.gpt-5.6-sol us.openai.gpt-5.6-terra us.openai.gpt-5.6-luna; do
  python3 smoke.py --model "$model"
done
```

每个结果应包含：

```json
{"ok": true, "response": "OK", "exit_code": 0}
```

务必检查每个 `result-<model-id>.json` 的字段；当前脚本的进程退出码不能可靠表示模型调用失败。

该脚本故意去掉进程中的静态凭证、API 密钥和 region 环境变量，
并要求没有 `.aws/credentials` 与 `.codex/.env`，以验证实例角色和文件中的 region。
若机器采用其他合法认证方式，不要删除它们来满足脚本断言，应另行修改测试方式。
测试暂时使用低推理强度和只读沙箱，不改变默认高推理配置。

普通使用：

```bash
cd /path/to/your/project
codex
```

指定模型：

```bash
codex -m us.openai.gpt-5.6-sol
codex -m us.openai.gpt-5.6-terra
codex -m us.openai.gpt-5.6-luna
codex -m us.openai.gpt-6-astra
```

## 5. 常见问题

- **提示缺少 Bedrock region**：检查 TOML 节层级、原 provider 的 region、
  Runtime region 和端点是否一致。不要只改 URL。
- **AccessDenied**：检查实例角色、SCP、权限边界和跨区域推理目标权限；
  不要通过修改 region 掩盖授权问题。
- **模型不存在 / on-demand 不支持**：检查源区域、模型 ID 和 `us.` 推理配置是否可用。
- **修改后调用了不同 provider**：检查项目 `.codex/config.toml`、命令行 `-c` / `-m`
  和 profile 的覆盖。验证工作目录应保持没有项目级配置。
- **command not found**：重新登录，或将 `~/.local/bin` 加入 PATH。
- **从 Mac 复制配置后 MCP 启动失败**：Linux 必须使用 Linux 上实际存在的可执行文件和路径。

## 开发验证

脚本仅依赖 Python 标准库，无构建步骤，也未配置独立单元测试框架或覆盖率门槛。
在仓库根目录执行：

```bash
python3 -m py_compile bootstrap.py smoke.py
python3 -m json.tool bedrock-models.json > /dev/null
HOME="$(mktemp -d)" python3 bootstrap.py
```

最后一条命令只在临时 HOME 中生成配置，不修改真实用户配置。
使用同一个临时 HOME 再次执行应拒绝覆盖；配置文件和模型目录 JSON 应为 `600`，新建目录应为 `700`。
模型、配置或 CLI 版本变更后，应重新执行第 4 节的四模型实测。

## 验证记录和来源

- 运行 `smoke.py` 后，同目录会生成 `result-us.openai.*.json`，仅保留在本地，不随仓库发布。
- OpenAI 配置参考：https://developers.openai.com/codex/config-reference/
- OpenAI CLI 文档：https://developers.openai.com/codex/cli/
- npm 包：https://www.npmjs.com/package/@openai/codex

这里的 Runtime provider、模型 ID 和实例角色组合以 Codex 0.154.0 验证配置为依据；
公开配置文档对 Runtime 的细节不完整，不能只依赖文档字段表或模型目录来判断可用性。
