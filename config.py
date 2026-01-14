"""
配置文件 - 自动从项目 config.yaml 读取配置
"""
import os
import yaml
from pathlib import Path


def find_config_yaml():
    """查找项目根目录的 config.yaml"""
    # 优先使用环境变量指定的路径
    env_path = os.environ.get("CPA_CONFIG_PATH")
    if env_path:
        config_path = Path(env_path)
        if config_path.exists():
            return config_path
        print(f"警告: 环境变量 CPA_CONFIG_PATH 指定的文件不存在: {env_path}")
    
    # 从当前脚本位置向上查找
    current = Path(__file__).resolve().parent
    for _ in range(5):  # 最多向上查找5层
        config_path = current / "config.yaml"
        if config_path.exists():
            return config_path
        current = current.parent
    return None


def load_project_config():
    """加载项目配置"""
    config_path = find_config_yaml()
    if not config_path:
        print("警告: 未找到 config.yaml，使用默认配置")
        return {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"警告: 读取 config.yaml 失败: {e}")
        return {}


# 加载项目配置
_project_config = load_project_config()

# 从 config.yaml 获取端口
_port = _project_config.get("port", 8317)
_host = _project_config.get("host", "") or "127.0.0.1"

# CLIProxyAPI Management API 配置
MANAGEMENT_API_URL = os.environ.get("CPA_MANAGEMENT_URL", f"http://127.0.0.1:{_port}")

# 尝试从环境变量或 config.yaml 获取管理密钥
# 注意：config.yaml 中存储的是 bcrypt hash，不能直接用
# 需要用户提供明文密钥
MANAGEMENT_API_KEY = os.environ.get("CPA_MANAGEMENT_KEY", "")

# WebUI 服务配置
WEBUI_HOST = os.environ.get("WEBUI_HOST", "127.0.0.1")
WEBUI_PORT = int(os.environ.get("WEBUI_PORT", "5000"))
WEBUI_DEBUG = os.environ.get("WEBUI_DEBUG", "false").lower() == "true"

# 认证目录 - 从 config.yaml 读取
_auth_dir = _project_config.get("auth-dir", "~/.cli-proxy-api")
AUTH_DIR = os.path.expanduser(_auth_dir)

# CLIProxyAPI 服务目录和日志配置
# 从环境变量 CPA_CONFIG_PATH 推导服务目录，或使用 CPA_SERVICE_DIR 环境变量
_config_path = find_config_yaml()
if _config_path:
    CPA_SERVICE_DIR = os.environ.get("CPA_SERVICE_DIR", str(_config_path.parent))
else:
    CPA_SERVICE_DIR = os.environ.get("CPA_SERVICE_DIR", "")

CPA_BINARY_NAME = os.environ.get("CPA_BINARY_NAME", "CLIProxyAPI")
CPA_LOG_FILE = os.environ.get("CPA_LOG_FILE", os.path.join(CPA_SERVICE_DIR, "cliproxyapi.log") if CPA_SERVICE_DIR else "")

# Google Cloud Code API (用于获取 Antigravity 配额)
CLOUD_CODE_API_URL = "https://cloudcode-pa.googleapis.com"
ANTIGRAVITY_USER_AGENT = "antigravity/1.11.3 Darwin/arm64"

# OAuth 配置 (用于刷新 token)
ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
ANTIGRAVITY_CLIENT_SECRET = "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"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# API Keys (从 config.yaml 读取，用于显示使用示例)
API_KEYS = _project_config.get("api-keys", [])
API_PORT = _port
API_HOST = _host or "127.0.0.1"

# 打印配置信息
if __name__ == "__main__":
    print(f"Management API URL: {MANAGEMENT_API_URL}")
    print(f"Auth Dir: {AUTH_DIR}")
    print(f"API Key: {'已配置' if MANAGEMENT_API_KEY else '未配置'}")
    print(f"API Keys Count: {len(API_KEYS)}")
