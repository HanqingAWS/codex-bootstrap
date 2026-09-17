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
| `bootstrap.py` | 安装独立 Bedrock 配置，备份并更新 Bash 启动设置 |
| `smoke.py` | 自动选用独立配置，对指定模型执行有超时限制的只读验证 |
| `bedrock-models.json` | 四个已验证模型的完整元数据 |
| `config.example.toml` | 手动配置参考，使用前替换绝对路径占位符 |
| `README.md` | 安装、验证和排障说明 |
| `AGENTS.md` | 贡献者指南 |
| `test_bootstrap.py`、`test_smoke.py` | 标准库 unittest 离线回归测试 |

`result-*.json`、`smoke-workspace/` 和 Python 缓存是本地产物，不纳入版本控制。
测试结果不再主动输出调用者 ARN，但错误详情仍可能包含身份信息；分享前必须脱敏。
公有仓库不保存真实用户名、主机地址、账号标识、部署日志或凭证。

### 用户目录中的配置

| 文件 | 用途 | 是否必需 |
| --- | --- | --- |
| `~/.codex-bedrock/.codex/config.toml` | 独立的 Bedrock 配置，默认区域 `us-west-2` | 是 |
| `~/.codex-bedrock/.codex/model-catalogs/bedrock-models.json` | 四模型目录及完整模型元数据 | 是 |
| `~/.bashrc` | 设置 `CODEX_HOME`，确保 `~/.local/bin` 在 PATH 中 | 自动追加管理块；已有文件先备份 |
| `~/.codex/` | 原有 Codex 配置、认证和历史 | 保留，不迁移、不覆盖 |
| `~/.codex-bedrock/.codex/.env` | API 密钥模式的环境变量 | 不创建；实例角色模式不需要 |
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

脚本根据当前用户 HOME，在 `~/.codex-bedrock/.codex` 安装独立配置。
不受旧 `CODEX_HOME` 环境变量影响，也不改动原来的 `~/.codex`。
区域、Runtime 端点和模型目录一起配置，无需手动指定区域或复制配置文件。

无论 PATH 是否已经包含 Codex，脚本都会在真实用户的 `~/.bashrc` 中确保存在：

```bash
export CODEX_HOME="$HOME/.codex-bedrock/.codex"
```

原有 `.bashrc` 会先备份为权限 `600` 的 `.bashrc.backup-codex-*`。
重复执行会复用内容一致的配置，不重复追加 shell 设置；如果目标配置、模型目录或管理块被修改，
脚本会拒绝覆盖，需先人工检查差异。此前按独立 HOME 方式生成的相同配置可以直接复用。

Python 子进程不能改变父终端的环境变量。配置完成后，`smoke.py` 可立即运行，不需要手动 export；
普通 `codex` 在读取 `~/.bashrc` 的新 Bash 终端中自动生效。要继续使用当前终端，只需加载一次：

```bash
source ~/.bashrc
```

如果自定义 Bash 登录配置没有加载 `.bashrc`，需要在自己的 shell 启动流程中加载它。

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
model_catalog_json = "/absolute/path/to/.codex-bedrock/.codex/model-catalogs/bedrock-models.json"

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
- EC2 所在区域可以不同；此配置明确请求 `us-west-2`，无需修改 AWS CLI 的全局默认区域。
- 模型 ID 使用 `us.` 前缀。模型列表是目录，不会授予模型访问权限。
- `web_search = "disabled"` 是此 Runtime 配置的默认值，不是对所有 provider 的通用要求。
- 不需要 `codex login` 获取 OpenAI API key；本方案通过 AWS 实例角色访问 Bedrock。
- 不在 `.env`、shell 配置或命令行参数中保存长期 AK/SK。
- `bedrock-models.json` 保留完整元数据，不要随意简化成只有模型名称的 JSON 数组。

权限检查：

```bash
chmod 700 "$HOME/.codex-bedrock" "$HOME/.codex-bedrock/.codex"
chmod 700 "$HOME/.codex-bedrock/.codex/model-catalogs"
chmod 600 "$HOME/.codex-bedrock/.codex/config.toml"
chmod 600 "$HOME/.codex-bedrock/.codex/model-catalogs/bedrock-models.json"
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

检查每个 `result-<model-id>.json` 的字段；验证失败或超时也会返回非零进程退出码。

脚本显式设置子进程的 `CODEX_HOME` 为独立 Bedrock 目录，不会沿用旧终端指向的其他配置。
它会去掉进程中的静态凭证、OpenAI API 密钥、OpenAI 端点和 region 环境变量，
并要求没有 `~/.aws/credentials`、`~/.codex/.env` 与独立配置目录中的 `.env`。
若机器采用其他合法认证方式，不要删除它们来满足脚本检查，应另行修改测试方式。
测试暂时使用低推理强度和只读沙箱，不改变默认高推理配置。
`aws_identity_checked` 只表示 AWS STS 身份检查成功，不证明模型权限；以实际模型调用结果为准。

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

- **请求发到 `api.openai.com`，报 `invalid_api_key`**：通常是普通 `codex` 仍读取旧配置。
  运行 `python3 bootstrap.py` 后重新打开 Bash 终端，或执行 `source ~/.bashrc`；
  启动时应显示 `provider: amazon-bedrock-runtime`，不需要更换 OpenAI API key。
- **提示已有文件不同**：脚本不会覆盖用户修改。检查独立目录的配置与模型目录，不要直接删除旧配置重试。
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

脚本和测试仅依赖 Python 标准库，无构建步骤，无覆盖率门槛。
在仓库根目录执行：

```bash
python3 -m py_compile bootstrap.py smoke.py test_bootstrap.py test_smoke.py
python3 -m json.tool bedrock-models.json > /dev/null
python3 -m unittest -v
HOME="$(mktemp -d)" python3 bootstrap.py
```

最后一条命令只在临时 HOME 中生成配置，不修改真实用户配置。
使用同一个临时 HOME 再次执行应复用相同配置，改动目标文件后应拒绝覆盖；
配置文件和模型目录 JSON 应为 `600`，新建目录应为 `700`。
离线测试覆盖旧配置保留、重复执行、shell 备份与导出、符号链接拒绝，以及测试失败退出码。
模型、配置或 CLI 版本变更后，应重新执行第 4 节的四模型实测。

## 验证记录和来源

- 运行 `smoke.py` 后，同目录会生成 `result-us.openai.*.json`，仅保留在本地，不随仓库发布。
- OpenAI 配置参考：https://developers.openai.com/codex/config-reference/
- OpenAI CLI 文档：https://developers.openai.com/codex/cli/
- npm 包：https://www.npmjs.com/package/@openai/codex

这里的 Runtime provider、模型 ID 和实例角色组合以 Codex 0.154.0 验证配置为依据；
公开配置文档对 Runtime 的细节不完整，不能只依赖文档字段表或模型目录来判断可用性。
