"""
CLIProxyAPI 账户管理 WebUI
显示账户列表、会员等级、配额信息，支持配额刷新

支持两种模式：
1. 通过 Management API 获取账户信息（需要 API Key）
2. 直接读取 auth 目录中的文件（本地模式）

新增功能：
- CLIProxyAPI 服务启动/停止控制
- 日志查看和清除
"""
import json
import os
import time
import subprocess
import signal
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import requests

from config import (
    MANAGEMENT_API_URL,
    MANAGEMENT_API_KEY,
    AUTH_DIR,
    WEBUI_HOST,
    WEBUI_PORT,
    WEBUI_DEBUG,
    CPA_SERVICE_DIR,
    CPA_BINARY_NAME,
    CPA_LOG_FILE,
    API_KEYS,
    API_PORT,
    API_HOST
)
from quota_service import get_quota_for_account, refresh_access_token, fetch_project_and_tier

app = Flask(__name__)

# 配额缓存文件路径
QUOTA_CACHE_FILE = Path(__file__).parent / "quota_cache.json"

# 禁用代理
NO_PROXY = {"http": None, "https": None}


def load_quota_cache() -> dict:
    """从文件加载配额缓存"""
    if QUOTA_CACHE_FILE.exists():
        try:
            with open(QUOTA_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载配额缓存失败: {e}")
    return {}


def save_quota_cache(cache: dict):
    """保存配额缓存到文件"""
    try:
        with open(QUOTA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存配额缓存失败: {e}")


# 内存缓存配额数据（启动时从文件加载）
quota_cache = load_quota_cache()


def get_management_headers():
    """获取管理 API 请求头"""
    headers = {"Content-Type": "application/json"}
    if MANAGEMENT_API_KEY:
        headers["Authorization"] = f"Bearer {MANAGEMENT_API_KEY}"
    return headers


def fetch_auth_files_from_api():
    """从 Management API 获取认证文件列表"""
    try:
        resp = requests.get(
            f"{MANAGEMENT_API_URL}/v0/management/auth-files",
            headers=get_management_headers(),
            timeout=10,
            proxies=NO_PROXY
        )
        if resp.status_code == 200:
            return resp.json().get("files", [])
        print(f"Management API 返回错误: {resp.status_code} - {resp.text}")
        return None
    except Exception as e:
        print(f"请求 Management API 失败: {e}")
        return None


def fetch_auth_files_from_disk():
    """直接从磁盘读取认证文件"""
    files = []
    auth_path = Path(AUTH_DIR)
    
    if not auth_path.exists():
        print(f"认证目录不存在: {AUTH_DIR}")
        return files
    
    for file_path in auth_path.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            file_info = {
                "id": file_path.stem,
                "name": file_path.name,
                "type": data.get("type", "unknown"),
                "email": data.get("email", ""),
                "status": "active",
                "source": "file",
                "modtime": os.path.getmtime(file_path),
                "_raw_data": data  # 保存原始数据供配额查询使用
            }
            
            # 提取更多信息
            if "project_id" in data:
                file_info["project_id"] = data["project_id"]
            if "access_token" in data:
                file_info["has_access_token"] = True
            if "refresh_token" in data:
                file_info["has_refresh_token"] = True
                
            files.append(file_info)
        except Exception as e:
            print(f"读取文件 {file_path} 失败: {e}")
    
    return files


def fetch_auth_files():
    """获取认证文件列表（优先使用 API，失败则读磁盘）"""
    if MANAGEMENT_API_KEY:
        api_files = fetch_auth_files_from_api()
        if api_files is not None:
            return api_files
        print("Management API 请求失败，回退到本地模式")
    
    return fetch_auth_files_from_disk()


def download_auth_file_from_api(name: str) -> dict:
    """从 Management API 下载单个认证文件内容"""
    try:
        resp = requests.get(
            f"{MANAGEMENT_API_URL}/v0/management/auth-files/download",
            params={"name": name},
            headers=get_management_headers(),
            timeout=10,
            proxies=NO_PROXY
        )
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception:
        return {}


def download_auth_file_from_disk(name: str) -> dict:
    """从磁盘读取单个认证文件内容"""
    file_path = Path(AUTH_DIR) / name
    if not file_path.exists():
        # 尝试添加 .json 后缀
        file_path = Path(AUTH_DIR) / f"{name}.json"
    
    if not file_path.exists():
        return {}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def download_auth_file(name: str) -> dict:
    """下载单个认证文件内容"""
    if MANAGEMENT_API_KEY:
        data = download_auth_file_from_api(name)
        if data:
            return data
    
    return download_auth_file_from_disk(name)


def get_tier_display(tier: str) -> dict:
    """获取订阅等级的显示信息"""
    tier_lower = (tier or "").lower()
    
    if "ultra" in tier_lower:
        return {"name": "ULTRA", "color": "purple", "badge_class": "tier-ultra"}
    elif "pro" in tier_lower:
        return {"name": "PRO", "color": "blue", "badge_class": "tier-pro"}
    elif tier:
        return {"name": tier.upper(), "color": "gray", "badge_class": "tier-free"}
    return {"name": "未知", "color": "gray", "badge_class": "tier-unknown"}


@app.route("/")
def index():
    """主页面"""
    return render_template("index.html")


@app.route("/api/accounts")
def api_accounts():
    """获取账户列表"""
    auth_files = fetch_auth_files()
    accounts = []
    
    for file in auth_files:
        account = {
            "id": file.get("id") or file.get("name", ""),
            "name": file.get("name", ""),
            "email": file.get("email", ""),
            "type": file.get("type", "unknown"),
            "provider": file.get("provider", file.get("type", "unknown")),
            "status": file.get("status", "unknown"),
            "status_message": file.get("status_message", ""),
            "disabled": file.get("disabled", False),
            "account_type": file.get("account_type", ""),
            "account": file.get("account", ""),
            "created_at": file.get("created_at", ""),
            "modtime": file.get("modtime", ""),
            "last_refresh": file.get("last_refresh", ""),
            "runtime_only": file.get("runtime_only", False),
            "source": file.get("source", "file"),
        }
        
        # 如果有原始数据，保存引用
        if "_raw_data" in file:
            account["_raw_data"] = file["_raw_data"]
        
        # 从缓存获取配额信息
        cache_key = account["id"]
        if cache_key in quota_cache:
            cached = quota_cache[cache_key]
            account["quota"] = cached.get("quota")
            account["subscription_tier"] = cached.get("subscription_tier")
        
        accounts.append(account)
    
    return jsonify({"accounts": accounts, "auth_dir": AUTH_DIR, "mode": "api" if MANAGEMENT_API_KEY else "local"})


# 支持配额查询的 provider 类型（与 quota_service 保持一致）
# 注意：只有 Antigravity 可以使用 fetchAvailableModels API
SUPPORTED_QUOTA_PROVIDERS = ["antigravity"]
# 支持静态模型列表的 provider 类型（Gemini CLI 也是静态列表）
STATIC_MODELS_PROVIDERS = ["gemini", "codex", "claude", "qwen", "iflow", "aistudio", "vertex"]
# 所有支持模型信息查询的 provider
ALL_SUPPORTED_PROVIDERS = SUPPORTED_QUOTA_PROVIDERS + STATIC_MODELS_PROVIDERS


@app.route("/api/accounts/<account_id>/quota", methods=["POST"])
def api_refresh_account_quota(account_id: str):
    """刷新单个账户的配额"""
    # 获取账户信息
    auth_files = fetch_auth_files()
    auth_file = None
    
    for f in auth_files:
        if f.get("id") == account_id or f.get("name") == account_id:
            auth_file = f
            break
    
    if not auth_file:
        return jsonify({"error": "账户不存在"}), 404
    
    provider = auth_file.get("type", "").lower()
    
    if provider not in ALL_SUPPORTED_PROVIDERS:
        return jsonify({
            "error": f"暂不支持 {provider} 类型账户的配额查询",
            "account_id": account_id
        }), 400
    
    # 获取认证数据
    if "_raw_data" in auth_file:
        auth_data = auth_file["_raw_data"]
    else:
        auth_data = download_auth_file(auth_file.get("name", ""))
    
    if not auth_data:
        return jsonify({"error": "无法获取认证数据"}), 500
    
    # 获取配额
    quota = get_quota_for_account(auth_data)
    
    # 更新缓存
    quota_cache[account_id] = {
        "quota": quota,
        "subscription_tier": quota.get("subscription_tier"),
        "fetched_at": time.time()
    }
    save_quota_cache(quota_cache)
    
    return jsonify({
        "account_id": account_id,
        "quota": quota,
        "subscription_tier": quota.get("subscription_tier"),
        "tier_display": get_tier_display(quota.get("subscription_tier"))
    })


@app.route("/api/accounts/quota/refresh-all", methods=["POST"])
def api_refresh_all_quotas():
    """刷新所有账户的配额"""
    auth_files = fetch_auth_files()
    results = []
    success_count = 0
    failed_count = 0
    skipped_count = 0
    static_count = 0
    
    for auth_file in auth_files:
        account_id = auth_file.get("id") or auth_file.get("name", "")
        provider = auth_file.get("type", "").lower()
        
        if provider not in ALL_SUPPORTED_PROVIDERS:
            skipped_count += 1
            results.append({
                "account_id": account_id,
                "email": auth_file.get("email", ""),
                "status": "skipped",
                "message": f"不支持 {provider} 类型"
            })
            continue
        
        # 对于静态模型列表的 provider，直接获取静态列表
        if provider in STATIC_MODELS_PROVIDERS:
            static_count += 1
            
            # 获取认证数据
            if "_raw_data" in auth_file:
                auth_data = auth_file["_raw_data"]
            else:
                auth_data = download_auth_file(auth_file.get("name", ""))
            
            if not auth_data:
                auth_data = {"type": provider}
            
            quota = get_quota_for_account(auth_data)
            
            # 更新缓存
            quota_cache[account_id] = {
                "quota": quota,
                "subscription_tier": quota.get("subscription_tier"),
                "fetched_at": time.time()
            }
            
            results.append({
                "account_id": account_id,
                "email": auth_file.get("email", ""),
                "status": "static",
                "message": "静态模型列表",
                "models_count": len(quota.get("models", []))
            })
            continue
        
        try:
            if "_raw_data" in auth_file:
                auth_data = auth_file["_raw_data"]
            else:
                auth_data = download_auth_file(auth_file.get("name", ""))
            
            if not auth_data:
                failed_count += 1
                results.append({
                    "account_id": account_id,
                    "email": auth_file.get("email", ""),
                    "status": "error",
                    "message": "无法获取认证数据"
                })
                continue
            
            quota = get_quota_for_account(auth_data)
            
            # 更新缓存
            quota_cache[account_id] = {
                "quota": quota,
                "subscription_tier": quota.get("subscription_tier"),
                "fetched_at": time.time()
            }
            
            success_count += 1
            results.append({
                "account_id": account_id,
                "email": auth_file.get("email", ""),
                "status": "success",
                "subscription_tier": quota.get("subscription_tier"),
                "models_count": len(quota.get("models", []))
            })
        except Exception as e:
            failed_count += 1
            results.append({
                "account_id": account_id,
                "email": auth_file.get("email", ""),
                "status": "error",
                "message": str(e)
            })
    
    # 批量刷新完成后保存缓存
    save_quota_cache(quota_cache)
    
    return jsonify({
        "total": len(auth_files),
        "success": success_count,
        "static": static_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results
    })


@app.route("/api/config")
def api_config():
    """获取配置信息"""
    return jsonify({
        "management_api_url": MANAGEMENT_API_URL,
        "has_api_key": bool(MANAGEMENT_API_KEY),
        "auth_dir": AUTH_DIR,
        "mode": "api" if MANAGEMENT_API_KEY else "local"
    })


# ==================== 账户管理 API ====================

# 支持的 OAuth Provider 及其对应的命令行参数
OAUTH_PROVIDERS = {
    "antigravity": {"flag": "-antigravity-login", "port": 51121},
    "gemini": {"flag": "-login", "port": 8085},
    "codex": {"flag": "-codex-login", "port": 1455},
    "claude": {"flag": "-claude-login", "port": 54545},
    "qwen": {"flag": "-qwen-login", "port": 0},  # Qwen 使用设备码模式，无端口
    "iflow": {"flag": "-iflow-login", "port": 55998},
}

# 存储正在进行的 OAuth 登录状态
oauth_sessions = {}
oauth_sessions_lock = __import__('threading').Lock()


@app.route("/api/accounts/<account_name>", methods=["DELETE"])
def api_delete_account(account_name: str):
    """删除账户"""
    if not account_name:
        return jsonify({"error": "账户名称不能为空"}), 400
    
    # 优先通过 Management API 删除
    try:
        resp = requests.delete(
            f"{MANAGEMENT_API_URL}/v0/management/auth-files",
            params={"name": account_name},
            headers=get_management_headers(),
            timeout=10,
            proxies=NO_PROXY
        )
        if resp.status_code == 200:
            return jsonify({"success": True, "message": "账户已删除"})
        elif resp.status_code == 404:
            # Management API 返回 404 可能是文件不存在或 API 被禁用
            pass  # 继续尝试本地删除
        elif resp.status_code == 401:
            return jsonify({"error": "需要配置 Management API Key (在 config.yaml 中设置 remote-management.secret-key)"}), 401
        else:
            return jsonify({"error": f"删除失败: {resp.text}"}), resp.status_code
    except requests.exceptions.ConnectionError:
        pass  # CLIProxyAPI 未运行，尝试本地删除
    except Exception as e:
        print(f"Management API 删除失败，尝试本地删除: {e}")
    
    # 本地模式：直接删除文件
    file_path = Path(AUTH_DIR) / account_name
    if not file_path.exists():
        # 尝试添加 .json 后缀
        file_path = Path(AUTH_DIR) / f"{account_name}.json"
    
    if not file_path.exists():
        return jsonify({"error": "账户不存在"}), 404
    
    try:
        file_path.unlink()
        return jsonify({"success": True, "message": "账户已删除"})
    except Exception as e:
        return jsonify({"error": f"删除失败: {str(e)}"}), 500


@app.route("/api/accounts/auth/<provider>", methods=["POST"])
def api_start_oauth(provider: str):
    """发起 OAuth 认证 (通过命令行方式)"""
    import threading
    import re
    import uuid
    
    provider = provider.lower()
    
    if provider not in OAUTH_PROVIDERS:
        return jsonify({
            "error": f"不支持的 Provider: {provider}",
            "supported": list(OAUTH_PROVIDERS.keys())
        }), 400
    
    provider_config = OAUTH_PROVIDERS[provider]
    flag = provider_config["flag"]
    callback_port = provider_config["port"]
    
    # 检查 CLIProxyAPI 可执行文件
    binary_path = os.path.join(CPA_SERVICE_DIR, CPA_BINARY_NAME)
    if not os.path.exists(binary_path):
        return jsonify({"error": f"CLIProxyAPI 可执行文件不存在: {binary_path}"}), 400
    
    # 生成会话 ID
    session_id = str(uuid.uuid4())[:8]
    
    # 构建命令
    cmd = [binary_path, flag, "-no-browser"]
    
    # 初始化会话状态
    with oauth_sessions_lock:
        oauth_sessions[session_id] = {
            "status": "starting",
            "provider": provider,
            "url": None,
            "error": None,
            "process": None,
            "output": ""
        }
    
    def run_oauth_command():
        try:
            # 启动进程
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=CPA_SERVICE_DIR
            )
            
            with oauth_sessions_lock:
                if session_id in oauth_sessions:
                    oauth_sessions[session_id]["process"] = process
                    oauth_sessions[session_id]["status"] = "waiting_url"
            
            url_pattern = re.compile(r'(https?://[^\s]+)')
            auth_url = None
            output_lines = []
            
            # 读取输出，寻找认证 URL
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                output_lines.append(line)
                
                # 更新输出
                with oauth_sessions_lock:
                    if session_id in oauth_sessions:
                        oauth_sessions[session_id]["output"] += line
                
                # 检查是否包含认证 URL
                if auth_url is None:
                    match = url_pattern.search(line)
                    if match:
                        potential_url = match.group(1)
                        # 确保是 OAuth URL
                        if "accounts.google.com" in potential_url or \
                           "console.anthropic.com" in potential_url or \
                           "auth.openai.com" in potential_url or \
                           "oauth" in potential_url.lower():
                            auth_url = potential_url.rstrip(')')
                            with oauth_sessions_lock:
                                if session_id in oauth_sessions:
                                    oauth_sessions[session_id]["url"] = auth_url
                                    oauth_sessions[session_id]["status"] = "waiting_callback"
                
                # 检查是否完成
                if "successful" in line.lower() or "authentication saved" in line.lower():
                    with oauth_sessions_lock:
                        if session_id in oauth_sessions:
                            oauth_sessions[session_id]["status"] = "ok"
                    break
                
                if "failed" in line.lower() or "error" in line.lower():
                    # 可能是错误，但继续读取
                    pass
            
            # 等待进程完成
            process.wait()
            
            with oauth_sessions_lock:
                if session_id in oauth_sessions:
                    session = oauth_sessions[session_id]
                    if process.returncode == 0:
                        if session["status"] != "ok":
                            session["status"] = "ok"
                    else:
                        if session["status"] not in ["ok", "error"]:
                            session["status"] = "error"
                            session["error"] = f"进程退出码: {process.returncode}"
                    
        except Exception as e:
            with oauth_sessions_lock:
                if session_id in oauth_sessions:
                    oauth_sessions[session_id]["status"] = "error"
                    oauth_sessions[session_id]["error"] = str(e)
    
    # 在后台线程中启动 OAuth 流程
    thread = threading.Thread(target=run_oauth_command, daemon=True)
    thread.start()
    
    # 等待一小段时间，让进程启动并输出 URL
    time.sleep(2)
    
    with oauth_sessions_lock:
        session = oauth_sessions.get(session_id, {})
        auth_url = session.get("url")
        status = session.get("status", "unknown")
    
    if auth_url:
        return jsonify({
            "success": True,
            "url": auth_url,
            "state": session_id,
            "provider": provider,
            "callback_port": callback_port,
            "hint": f"请在浏览器中打开上述链接完成认证。如果是远程服务器，请确保端口 {callback_port} 可访问（可使用 SSH 端口转发: ssh -L {callback_port}:localhost:{callback_port} user@server）"
        })
    else:
        # 再等待一下
        time.sleep(1)
        with oauth_sessions_lock:
            session = oauth_sessions.get(session_id, {})
            auth_url = session.get("url")
            output = session.get("output", "")
        
        if auth_url:
            return jsonify({
                "success": True,
                "url": auth_url,
                "state": session_id,
                "provider": provider,
                "callback_port": callback_port
            })
        
        return jsonify({
            "error": "未能获取认证 URL，请检查 CLIProxyAPI 日志",
            "output": output[-500:] if output else "",
            "state": session_id
        }), 500


@app.route("/api/accounts/auth/status")
def api_oauth_status():
    """查询 OAuth 认证状态"""
    state = request.args.get("state", "")
    
    if not state:
        return jsonify({"error": "缺少 state 参数"}), 400
    
    with oauth_sessions_lock:
        session = oauth_sessions.get(state)
        if not session:
            return jsonify({"status": "unknown", "error": "会话不存在"}), 404
        
        status = session.get("status", "unknown")
        error = session.get("error")
        output = session.get("output", "")[-200:]  # 最后 200 字符
    
    if status == "ok":
        # 清理会话
        with oauth_sessions_lock:
            oauth_sessions.pop(state, None)
        return jsonify({"status": "ok"})
    elif status == "error":
        return jsonify({"status": "error", "error": error or "认证失败"})
    elif status in ["waiting_url", "waiting_callback"]:
        return jsonify({"status": "wait", "detail": output})
    else:
        return jsonify({"status": "wait", "detail": status})


@app.route("/api/accounts/auth/cancel", methods=["POST"])
def api_cancel_oauth():
    """取消 OAuth 认证"""
    state = request.args.get("state", "") or (request.json or {}).get("state", "")
    
    if not state:
        return jsonify({"error": "缺少 state 参数"}), 400
    
    with oauth_sessions_lock:
        session = oauth_sessions.pop(state, None)
        if session and session.get("process"):
            try:
                session["process"].terminate()
            except Exception:
                pass
    
    return jsonify({"success": True, "message": "会话已取消"})


# ==================== 服务控制 API ====================

def get_service_status():
    """获取 CLIProxyAPI 服务状态"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", CPA_BINARY_NAME],
            capture_output=True,
            text=True
        )
        pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
        
        if pids:
            # 获取进程详细信息
            processes = []
            for pid in pids:
                try:
                    ps_result = subprocess.run(
                        ["ps", "-p", pid, "-o", "pid,ppid,%cpu,%mem,etime,command"],
                        capture_output=True,
                        text=True
                    )
                    lines = ps_result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        processes.append({
                            "pid": pid,
                            "info": lines[1].strip()
                        })
                except Exception:
                    processes.append({"pid": pid, "info": ""})
            
            return {
                "running": True,
                "pids": pids,
                "processes": processes,
                "count": len(pids)
            }
        return {"running": False, "pids": [], "processes": [], "count": 0}
    except Exception as e:
        return {"running": False, "error": str(e), "pids": [], "processes": [], "count": 0}


@app.route("/api/service/status")
def api_service_status():
    """获取服务状态"""
    status = get_service_status()
    status["service_dir"] = CPA_SERVICE_DIR
    status["binary_name"] = CPA_BINARY_NAME
    status["log_file"] = CPA_LOG_FILE
    status["configured"] = bool(CPA_SERVICE_DIR and os.path.exists(CPA_SERVICE_DIR))
    return jsonify(status)


@app.route("/api/service/start", methods=["POST"])
def api_service_start():
    """启动 CLIProxyAPI 服务"""
    if not CPA_SERVICE_DIR or not os.path.exists(CPA_SERVICE_DIR):
        return jsonify({"error": "服务目录未配置或不存在", "service_dir": CPA_SERVICE_DIR}), 400
    
    binary_path = os.path.join(CPA_SERVICE_DIR, CPA_BINARY_NAME)
    if not os.path.exists(binary_path):
        return jsonify({"error": f"可执行文件不存在: {binary_path}"}), 400
    
    # 检查是否已经在运行
    status = get_service_status()
    if status["running"]:
        return jsonify({
            "success": False,
            "message": "服务已在运行",
            "pids": status["pids"]
        })
    
    try:
        # 使用 nohup 启动服务
        log_file = CPA_LOG_FILE or os.path.join(CPA_SERVICE_DIR, "cliproxyapi.log")
        
        # 创建启动命令
        cmd = f"cd {CPA_SERVICE_DIR} && nohup ./{CPA_BINARY_NAME} > {log_file} 2>&1 &"
        
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=CPA_SERVICE_DIR
        )
        
        # 等待一小段时间让进程启动
        time.sleep(1)
        
        # 检查启动结果
        new_status = get_service_status()
        if new_status["running"]:
            return jsonify({
                "success": True,
                "message": "服务启动成功",
                "pids": new_status["pids"]
            })
        else:
            return jsonify({
                "success": False,
                "message": "服务启动失败，请检查日志"
            }), 500
            
    except Exception as e:
        return jsonify({"error": f"启动服务失败: {str(e)}"}), 500


@app.route("/api/service/stop", methods=["POST"])
def api_service_stop():
    """停止 CLIProxyAPI 服务"""
    status = get_service_status()
    if not status["running"]:
        return jsonify({
            "success": True,
            "message": "服务未在运行"
        })
    
    try:
        # 使用 pkill 停止服务
        result = subprocess.run(
            ["pkill", "-f", CPA_BINARY_NAME],
            capture_output=True,
            text=True
        )
        
        # 等待进程退出
        time.sleep(0.5)
        
        # 检查停止结果
        new_status = get_service_status()
        if not new_status["running"]:
            return jsonify({
                "success": True,
                "message": "服务已停止",
                "killed_pids": status["pids"]
            })
        else:
            # 强制杀死
            subprocess.run(
                ["pkill", "-9", "-f", CPA_BINARY_NAME],
                capture_output=True,
                text=True
            )
            time.sleep(0.3)
            final_status = get_service_status()
            return jsonify({
                "success": not final_status["running"],
                "message": "服务已强制停止" if not final_status["running"] else "停止服务失败",
                "remaining_pids": final_status["pids"]
            })
            
    except Exception as e:
        return jsonify({"error": f"停止服务失败: {str(e)}"}), 500


@app.route("/api/service/restart", methods=["POST"])
def api_service_restart():
    """重启 CLIProxyAPI 服务"""
    # 先停止
    stop_result = api_service_stop()
    stop_data = stop_result.get_json() if hasattr(stop_result, 'get_json') else {}
    
    time.sleep(0.5)
    
    # 再启动
    start_result = api_service_start()
    start_data = start_result.get_json() if hasattr(start_result, 'get_json') else {}
    
    return jsonify({
        "stop": stop_data,
        "start": start_data,
        "success": start_data.get("success", False)
    })


# ==================== 日志 API ====================

@app.route("/api/logs")
def api_logs():
    """获取日志内容"""
    if not CPA_LOG_FILE:
        return jsonify({"error": "日志文件未配置"}), 400
    
    if not os.path.exists(CPA_LOG_FILE):
        return jsonify({
            "content": "",
            "lines": 0,
            "size": 0,
            "exists": False,
            "path": CPA_LOG_FILE
        })
    
    # 获取参数
    lines = request.args.get("lines", 200, type=int)
    offset = request.args.get("offset", 0, type=int)
    
    try:
        file_size = os.path.getsize(CPA_LOG_FILE)
        
        with open(CPA_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # 如果请求尾部日志（默认行为）
        if offset == 0:
            content_lines = all_lines[-lines:] if lines < total_lines else all_lines
        else:
            content_lines = all_lines[offset:offset + lines]
        
        return jsonify({
            "content": "".join(content_lines),
            "lines": len(content_lines),
            "total_lines": total_lines,
            "size": file_size,
            "size_human": format_file_size(file_size),
            "exists": True,
            "path": CPA_LOG_FILE
        })
        
    except Exception as e:
        return jsonify({"error": f"读取日志失败: {str(e)}"}), 500


@app.route("/api/logs/tail")
def api_logs_tail():
    """获取日志尾部（用于实时刷新）"""
    if not CPA_LOG_FILE or not os.path.exists(CPA_LOG_FILE):
        return jsonify({"content": "", "lines": 0})
    
    lines = request.args.get("lines", 50, type=int)
    
    try:
        # 使用 tail 命令高效读取尾部
        result = subprocess.run(
            ["tail", f"-{lines}", CPA_LOG_FILE],
            capture_output=True,
            text=True
        )
        return jsonify({
            "content": result.stdout,
            "lines": lines
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    """清除日志文件"""
    if not CPA_LOG_FILE:
        return jsonify({"error": "日志文件未配置"}), 400
    
    if not os.path.exists(CPA_LOG_FILE):
        return jsonify({"success": True, "message": "日志文件不存在"})
    
    try:
        # 备份选项
        backup = request.json.get("backup", False) if request.json else False
        
        if backup:
            backup_path = f"{CPA_LOG_FILE}.{int(time.time())}.bak"
            os.rename(CPA_LOG_FILE, backup_path)
            # 创建新的空日志文件
            open(CPA_LOG_FILE, "w").close()
            return jsonify({
                "success": True,
                "message": f"日志已备份至 {backup_path}",
                "backup_path": backup_path
            })
        else:
            # 直接清空
            open(CPA_LOG_FILE, "w").close()
            return jsonify({
                "success": True,
                "message": "日志已清除"
            })
            
    except Exception as e:
        return jsonify({"error": f"清除日志失败: {str(e)}"}), 500


def format_file_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ==================== API 使用说明 ====================

@app.route("/api/usage-guide")
def api_usage_guide():
    """获取 API 使用说明，包含示例代码"""
    # 获取第一个可用的 API key
    api_key = API_KEYS[0] if API_KEYS else "YOUR_API_KEY"
    base_url = f"http://{API_HOST}:{API_PORT}"
    
    # 生成 curl 示例
    curl_example = f'''curl {base_url}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {api_key}" \\
  -d '{{
    "model": "gemini-2.5-flash",
    "messages": [
      {{"role": "user", "content": "Hello, how are you?"}}
    ]
  }}'
'''

    # 生成 Python 示例
    python_example = f'''import requests

url = "{base_url}/v1/chat/completions"
headers = {{
    "Content-Type": "application/json",
    "Authorization": "Bearer {api_key}"
}}
data = {{
    "model": "gemini-2.5-flash",
    "messages": [
        {{"role": "user", "content": "Hello, how are you?"}}
    ]
}}

response = requests.post(url, headers=headers, json=data)
print(response.json())
'''

    # 生成 Python (OpenAI SDK) 示例
    python_openai_example = f'''from openai import OpenAI

client = OpenAI(
    api_key="{api_key}",
    base_url="{base_url}/v1"
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[
        {{"role": "user", "content": "Hello, how are you?"}}
    ]
)

print(response.choices[0].message.content)
'''

    # 生成流式响应示例
    curl_stream_example = f'''curl {base_url}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {api_key}" \\
  -d '{{
    "model": "gemini-2.5-flash",
    "messages": [
      {{"role": "user", "content": "Write a short poem"}}
    ],
    "stream": true
  }}'
'''

    python_stream_example = f'''from openai import OpenAI

client = OpenAI(
    api_key="{api_key}",
    base_url="{base_url}/v1"
)

stream = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[
        {{"role": "user", "content": "Write a short poem"}}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
'''

    return jsonify({
        "base_url": base_url,
        "api_key": api_key,
        "api_keys_count": len(API_KEYS),
        "all_api_keys": API_KEYS,
        "examples": {
            "curl": curl_example,
            "curl_stream": curl_stream_example,
            "python_requests": python_example,
            "python_openai": python_openai_example,
            "python_stream": python_stream_example
        }
    })


if __name__ == "__main__":
    mode = "Management API" if MANAGEMENT_API_KEY else "本地文件"
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║          CLIProxyAPI 账户管理 WebUI                          ║
╠══════════════════════════════════════════════════════════════╣
║  服务地址: http://{WEBUI_HOST}:{WEBUI_PORT}
║  运行模式: {mode}
║  认证目录: {AUTH_DIR}
╚══════════════════════════════════════════════════════════════╝
    """)
    app.run(host=WEBUI_HOST, port=WEBUI_PORT, debug=WEBUI_DEBUG)
