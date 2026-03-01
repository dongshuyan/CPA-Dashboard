# CPA-Dashboard

CLIProxyAPI 控制面板 - 服务管理与账户监控 Web 界面。

## 功能概览

### 服务控制
- 启动 / 停止 / 重启 CLIProxyAPI 服务
- 实时查看服务运行状态（PID、运行目录等）
- 查看运行日志（支持语法高亮、自动刷新）
- 清除日志文件

### 账户管理
- 显示所有账户列表（Antigravity、Gemini、Claude、Codex、Qwen、iFlow、Kimi、AI Studio、Vertex 等）
- 显示会员等级（ULTRA/PRO/FREE）及账户状态（活跃 / 需要重新登录）
- 显示每个模型的配额百分比及重置倒计时（Antigravity 实时配额）；其他类型显示静态支持的模型列表
- 配额缓存持久化（重启后保留）
- **刷新配额**：单个账户刷新 / 批量并行刷新所有账户（并行度 4）；刷新时会校验账号是否仍有效
- **Codex 鉴权**：刷新 Codex 账户时除 OAuth 刷新外，会请求 Codex Models API；若返回 401 则标记为「需要重新登录」，更准确
- **筛选**：
  - **类型**：全部、Antigravity、Gemini、Claude、Codex、ULTRA、PRO
  - **状态**：可勾选「仅显示需要重新登录的账户」，与类型组合（如：Codex + 仅显示需要重新登录 → 只显示需重新登录的 Codex 账户）
- **批量删除**：勾选「仅显示需要重新登录的账户」后，显示「批量删除需要重新登录的账户」按钮，带二次确认，可一键删除当前列表中的失效账户
- **添加账户**：通过 OAuth 登录添加新账户（支持 Antigravity / Gemini / Codex / Claude / Qwen / iFlow / Kimi）
- **删除账户**：删除指定账户（带确认对话框）

## 安装

```bash
pip install -r requirements.txt
```

## 使用

### 方式一：直接运行
```bash
python app.py
```

### 方式二：通过启动脚本
```bash
# macOS / 通用
./start.sh

# Linux（优先使用 $HOME/cliproxyapi，可设置 CLIPROXYAPI_DIR 覆盖）
./start-linux.sh
```

默认访问 http://127.0.0.1:5000

## 配置

程序会自动从环境变量或父目录查找 `config.yaml` 读取配置：
- `port` - CLIProxyAPI 端口
- `auth-dir` - 认证文件目录

环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CPA_CONFIG_PATH` | config.yaml 绝对路径 | 自动查找 |
| `CPA_SERVICE_DIR` | CLIProxyAPI 服务目录 | 从 config 路径推导 |
| `CPA_BINARY_NAME` | 可执行文件名 | `CLIProxyAPI` |
| `CPA_LOG_FILE` | 日志文件路径 | `cliproxyapi.log` |
| `CPA_MANAGEMENT_URL` | Management API 地址 | `http://127.0.0.1:{port}` |
| `CPA_MANAGEMENT_KEY` | Management API 密钥 | - |
| `WEBUI_HOST` | WebUI 监听地址 | `127.0.0.1` |
| `WEBUI_PORT` | WebUI 端口 | `5000` |

## 运行模式

1. **本地模式**（默认）：直接读取 auth 目录中的 JSON 文件
2. **API 模式**：设置 `CPA_MANAGEMENT_KEY` 后通过 Management API 获取数据

## 界面说明

### 基本界面

![基本界面](pics/基本界面.png)

顶部导航：**服务控制**、**账户管理**、**使用说明**。账户管理页包含统计概览、类型/状态筛选、账户卡片与操作按钮。

### 服务控制

![服务控制](pics/P1.png)

- **服务状态**：实时显示 CLIProxyAPI 运行状态（绿色=运行，红色=停止），含 PID、服务目录、日志路径
- **服务控制**：🟢 启动 / 🟠 停止 / 🔵 重启
- **运行日志**：自动刷新开关、手动刷新、跳转底部、清除日志

### 账户管理

![账户管理](pics/P2.png)

- **统计概览**：总账户数、Antigravity 数、ULTRA/PRO 会员数
- **类型筛选**：全部、Antigravity、Gemini、Claude、Codex、ULTRA、PRO
- **状态筛选**：勾选「⚠️ 仅显示需要重新登录的账户」可与类型组合；勾选后显示「批量删除需要重新登录的账户 (N)」按钮
- **账户卡片**：邮箱、类型标签、会员等级、状态（活跃 / 需要重新登录）、配额信息（或静态模型列表）、刷新 / 删除按钮

### 刷新配额与鉴别需要重新登录

![刷新配额以及鉴别需要重新登录账户](pics/刷新配额以及鉴别需要重新登录账户.png)

- 点击「刷新所有配额」会批量刷新并校验各账号 token；Codex 会额外请求 Models API，401 则标记为需要重新登录
- 勾选「仅显示需要重新登录的账户」可查看并批量删除失效账号（带二次确认）

### 添加账户（OAuth 登录）

![登录账户1](pics/登录账户1.png)

选择 Provider（共 7 个：Antigravity、Gemini CLI、Codex、Claude、Qwen、iFlow、Kimi）后启动 OAuth。认证链接会出现在「认证链接」框或命令行输出中，复制到浏览器打开即可；Qwen、Kimi 为设备码流程，链接会自动填入上方认证链接框。部分流程需在终端按提示输入（如项目 ID、回调 URL 等）。

![登录账户2](pics/登录账户2.png)

认证成功后账户会出现在列表中，可在此处刷新配额或删除。

### 添加账户支持的 Provider

| Provider | 说明 | 回调端口 |
|----------|------|----------|
| Antigravity | Google Antigravity 账户 | 51121 |
| Gemini CLI | Google Gemini CLI 账户 | 8085 |
| Codex | OpenAI Codex 账户 | 1455 |
| Claude | Anthropic Claude 账户 | 54545 |
| Qwen | 通义千问账户 | 设备码模式 |
| iFlow | iFlow 账户 | 55998 |
| Kimi | Moonshot Kimi 账户 | 设备码模式 |

**远程服务器**：需 SSH 端口转发后再在本地浏览器完成 OAuth，例如：

```bash
ssh -L 51121:localhost:51121 user@server
```

### 使用说明（API 示例）

![使用说明](pics/P3.png)

- **连接信息**：Base URL、API Key、可用 Keys 数量
- **所有 API Keys**：列表与复制
- **示例**：cURL、Python requests、OpenAI SDK、流式请求等，可直接复制使用

## 注意

- **配额**：仅 Antigravity 支持实时配额（模型别名与 CLIProxyAPI 一致）；其余类型（Gemini/Codex/Claude/Qwen/iFlow/Kimi/AI Studio/Vertex）显示静态模型列表，与 CLIProxyAPI `internal/registry/model_definitions_static_data.go` 同步
- **服务控制**：需正确配置 `CPA_SERVICE_DIR`（或通过 `start-linux.sh` / 环境变量指定）
