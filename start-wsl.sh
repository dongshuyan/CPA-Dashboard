#!/bin/bash

# CPA-Dashboard 启动脚本（Windows/WSL 专用）
# 目标：在 WSL 中启动，保留完整 Linux 功能（pty/pgrep/pkill/tail）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INSTALL_DIR="$HOME/cliproxyapi"
FALLBACK_CONFIG="$SCRIPT_DIR/../CLIProxyAPI/config.yaml"

if [ -n "$CLIPROXYAPI_DIR" ] && [ -f "$CLIPROXYAPI_DIR/config.yaml" ]; then
    INSTALL_DIR="$CLIPROXYAPI_DIR"
elif [ -f "$DEFAULT_INSTALL_DIR/config.yaml" ]; then
    INSTALL_DIR="$DEFAULT_INSTALL_DIR"
else
    INSTALL_DIR=""
fi

if [ -n "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/config.yaml" ]; then
    export CPA_CONFIG_PATH="$INSTALL_DIR/config.yaml"
    export CPA_SERVICE_DIR="$INSTALL_DIR"
    export CPA_BINARY_NAME="cli-proxy-api"
    echo "使用 CLIProxyAPI 安装目录: $INSTALL_DIR"
else
    export CPA_CONFIG_PATH="$FALLBACK_CONFIG"
    export CPA_BINARY_NAME="cli-proxy-api"
    if [ -f "$FALLBACK_CONFIG" ]; then
        export CPA_SERVICE_DIR="$(dirname "$FALLBACK_CONFIG")"
        echo "使用相邻 CLIProxyAPI 目录: $CPA_SERVICE_DIR"
    else
        echo "未找到 config.yaml，将使用默认配置。可设置 CLIPROXYAPI_DIR 指向安装目录。"
    fi
fi

cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

if ! python3 -c "import flask" 2>/dev/null; then
    echo "安装依赖..."
    python3 -m pip install -r requirements.txt
fi

echo "访问: http://127.0.0.1:5000"
python3 app.py
