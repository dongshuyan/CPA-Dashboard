#!/bin/bash

# CPA-Dashboard 启动脚本
# 优先使用「一键安装」的 CLIProxyAPI（$HOME/cliproxyapi），
# 若不存在则回退到相邻的 CLIProxyAPI 源码目录。可通过 CLIPROXYAPI_DIR 覆盖安装目录。

# 设置代理（CPA-Dashboard 及由其启动的 CLIProxyAPI 均会继承）
export http_proxy="http://127.0.0.1:7897"
export https_proxy="http://127.0.0.1:7897"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_INSTALL_DIR="$HOME/cliproxyapi"
FALLBACK_CONFIG="$SCRIPT_DIR/../CLIProxyAPI/config.yaml"

if [ -n "$CLIPROXYAPI_DIR" ]; then
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
    # 从 config 路径推导服务目录（config.py 会做），仅设置二进制名供源码编译场景使用
    export CPA_BINARY_NAME="cli-proxy-api"
    if [ -f "$FALLBACK_CONFIG" ]; then
        echo "使用相邻 CLIProxyAPI 目录: $(dirname "$FALLBACK_CONFIG")"
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
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
fi

echo "访问: http://127.0.0.1:5000"
python3 app.py
