#!/bin/bash

# CPA-Dashboard 启动脚本

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 设置 config.yaml 的路径（相对于 CPA-Dashboard 的 CLIProxyAPI 目录）
export CPA_CONFIG_PATH="$SCRIPT_DIR/../CLIProxyAPI/config.yaml"

# 进入 CPA-Dashboard 目录
cd "$SCRIPT_DIR"

python3 app.py
