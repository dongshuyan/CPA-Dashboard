#!/bin/bash

# CPA-Dashboard 启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 设置 config.yaml 的路径（相对于 CPA-Dashboard 的 CLIProxyAPI 目录）
export CPA_CONFIG_PATH="$SCRIPT_DIR/../CLIProxyAPI/config.yaml"

# 进入 CPA-Dashboard 目录
cd "$SCRIPT_DIR"

# 检查虚拟环境是否存在，不存在则创建
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 检查依赖是否安装
if ! python3 -c "import flask" 2>/dev/null; then
    echo "安装依赖..."
    pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
fi

# 启动应用
python3 app.py
