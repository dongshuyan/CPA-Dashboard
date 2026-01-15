# CPA-Dashboard

CLIProxyAPI 控制面板 - 服务管理与账户监控 Web 界面。

## 功能

### 服务控制
- 启动 / 停止 / 重启 CLIProxyAPI 服务
- 实时查看服务运行状态（PID、运行目录等）
- 查看运行日志（支持语法高亮、自动刷新）
- 清除日志文件

### 账户管理
- 显示所有账户列表
- 显示账户类型（antigravity/gemini/claude/codex 等）
- 显示会员等级（ULTRA/PRO/FREE）
- 显示每个模型的配额百分比及重置倒计时
- 配额缓存持久化（重启后保留）
- 单个账户配额刷新
- 批量并行刷新所有账户配额（并行度 4）
- 按类型/会员等级筛选

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
# 在 CPA-Dashboard 目录下
./start.sh

# 或在 CLIProxyAPI/scripts 目录下
./start_webui.sh
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

## 注意

- 配额查询目前仅支持 Antigravity 类型账户
- 其他类型账户只显示基本信息
- 服务控制功能需要正确配置 `CPA_SERVICE_DIR`
