"""
配额服务 - 负责获取账户配额信息
支持 Antigravity 和 Gemini CLI 类型账户
"""
import requests
import time
from typing import Optional
from config import (
    CLOUD_CODE_API_URL,
    ANTIGRAVITY_USER_AGENT,
    ANTIGRAVITY_CLIENT_ID,
    ANTIGRAVITY_CLIENT_SECRET,
    GEMINI_CLI_USER_AGENT,
    GOOGLE_TOKEN_URL
)

# 支持配额查询的 provider 类型（可获取实时配额信息）
# 注意：只有 Antigravity 可以使用 fetchAvailableModels API
# Gemini CLI 使用个人 Google 账户，没有 fetchAvailableModels 权限
SUPPORTED_QUOTA_PROVIDERS = ["antigravity"]

# Antigravity API 返回的模型名称到 CLIProxyAPI 使用的别名映射
# 参考 CLIProxyAPI/internal/runtime/executor/antigravity_executor.go 的 modelName2Alias 函数
ANTIGRAVITY_MODEL_NAME_TO_ALIAS = {
    "rev19-uic3-1p": "gemini-2.5-computer-use-preview-10-2025",
    "gemini-3-pro-image": "gemini-3-pro-image-preview",
    "gemini-3-pro-high": "gemini-3-pro-preview",
    "gemini-3-flash": "gemini-3-flash-preview",
    "claude-sonnet-4-5": "gemini-claude-sonnet-4-5",
    "claude-sonnet-4-5-thinking": "gemini-claude-sonnet-4-5-thinking",
    "claude-opus-4-5-thinking": "gemini-claude-opus-4-5-thinking",
}

# 需要跳过的模型（CLIProxyAPI 中 modelName2Alias 返回空字符串的模型）
ANTIGRAVITY_SKIP_MODELS = {
    "chat_20706", "chat_23310", "gemini-2.5-flash-thinking", 
    "gemini-3-pro-low", "gemini-2.5-pro"
}


def antigravity_model_name_to_alias(model_name: str) -> Optional[str]:
    """
    将 Antigravity API 返回的模型名称转换为 CLIProxyAPI 使用的别名
    
    Args:
        model_name: Antigravity API 返回的原始模型名称
        
    Returns:
        CLIProxyAPI 使用的模型别名，如果模型应该跳过则返回 None
    """
    if model_name in ANTIGRAVITY_SKIP_MODELS:
        return None
    return ANTIGRAVITY_MODEL_NAME_TO_ALIAS.get(model_name, model_name)

# 支持显示静态模型列表的 provider 类型（无法获取实时配额，但可以显示支持的模型）
# Gemini CLI 也使用静态列表
STATIC_MODELS_PROVIDERS = ["gemini", "codex", "claude", "qwen", "iflow", "aistudio", "vertex"]

# 静态模型列表（从 CLIProxyAPI/internal/registry/model_definitions.go 提取）
STATIC_MODEL_LISTS = {
    # GetGeminiCLIModels() - 第 293-371 行
    "gemini": [
        {"name": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "description": "Stable release (June 17th, 2025) of Gemini 2.5 Pro"},
        {"name": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "description": "Stable version of Gemini 2.5 Flash, up to 1M tokens"},
        {"name": "gemini-2.5-flash-lite", "display_name": "Gemini 2.5 Flash Lite", "description": "Our smallest and most cost effective model"},
        {"name": "gemini-3-pro-preview", "display_name": "Gemini 3 Pro Preview", "description": "Our most intelligent model with SOTA reasoning"},
        {"name": "gemini-3-flash-preview", "display_name": "Gemini 3 Flash Preview", "description": "Our most intelligent model built for speed"},
    ],
    # GetOpenAIModels() - 第 531-660 行
    "codex": [
        {"name": "gpt-5", "display_name": "GPT 5", "description": "Stable version of GPT 5"},
        {"name": "gpt-5-codex", "display_name": "GPT 5 Codex", "description": "Stable version of GPT 5 Codex"},
        {"name": "gpt-5-codex-mini", "display_name": "GPT 5 Codex Mini", "description": "Cheaper, faster, but less capable version"},
        {"name": "gpt-5.1", "display_name": "GPT 5.1", "description": "Stable version of GPT 5.1"},
        {"name": "gpt-5.1-codex", "display_name": "GPT 5.1 Codex", "description": "Stable version of GPT 5.1 Codex"},
        {"name": "gpt-5.1-codex-mini", "display_name": "GPT 5.1 Codex Mini", "description": "Cheaper, faster, but less capable version"},
        {"name": "gpt-5.1-codex-max", "display_name": "GPT 5.1 Codex Max", "description": "Stable version of GPT 5.1 Codex Max"},
        {"name": "gpt-5.2", "display_name": "GPT 5.2", "description": "Stable version of GPT 5.2"},
        {"name": "gpt-5.2-codex", "display_name": "GPT 5.2 Codex", "description": "Stable version of GPT 5.2 Codex"},
    ],
    # GetClaudeModels() - 第 7-100 行
    "claude": [
        {"name": "claude-haiku-4-5-20251001", "display_name": "Claude 4.5 Haiku", "description": "Fast and efficient model"},
        {"name": "claude-sonnet-4-5-20250929", "display_name": "Claude 4.5 Sonnet", "description": "Balanced performance model"},
        {"name": "claude-opus-4-5-20251101", "display_name": "Claude 4.5 Opus", "description": "Premium model combining maximum intelligence"},
        {"name": "claude-opus-4-1-20250805", "display_name": "Claude 4.1 Opus", "description": "Claude 4.1 Opus"},
        {"name": "claude-opus-4-20250514", "display_name": "Claude 4 Opus", "description": "Claude 4 Opus"},
        {"name": "claude-sonnet-4-20250514", "display_name": "Claude 4 Sonnet", "description": "Claude 4 Sonnet"},
        {"name": "claude-3-7-sonnet-20250219", "display_name": "Claude 3.7 Sonnet", "description": "Claude 3.7 Sonnet"},
        {"name": "claude-3-5-haiku-20241022", "display_name": "Claude 3.5 Haiku", "description": "Claude 3.5 Haiku"},
    ],
    # GetQwenModels() - 第 663-705 行
    "qwen": [
        {"name": "qwen3-coder-plus", "display_name": "Qwen3 Coder Plus", "description": "Advanced code generation and understanding model"},
        {"name": "qwen3-coder-flash", "display_name": "Qwen3 Coder Flash", "description": "Fast code generation model"},
        {"name": "vision-model", "display_name": "Qwen3 Vision Model", "description": "Vision model"},
    ],
    # GetIFlowModels() - 第 715-760 行
    "iflow": [
        {"name": "tstars2.0", "display_name": "TStars-2.0", "description": "iFlow TStars-2.0 multimodal assistant"},
        {"name": "qwen3-coder-plus", "display_name": "Qwen3-Coder-Plus", "description": "Qwen3 Coder Plus code generation"},
        {"name": "qwen3-max", "display_name": "Qwen3-Max", "description": "Qwen3 flagship model"},
        {"name": "qwen3-vl-plus", "display_name": "Qwen3-VL-Plus", "description": "Qwen3 multimodal vision-language"},
        {"name": "qwen3-max-preview", "display_name": "Qwen3-Max-Preview", "description": "Qwen3 Max preview build"},
        {"name": "kimi-k2-0905", "display_name": "Kimi-K2-Instruct-0905", "description": "Moonshot Kimi K2 instruct 0905"},
        {"name": "glm-4.6", "display_name": "GLM-4.6", "description": "Zhipu GLM 4.6 general model"},
        {"name": "glm-4.7", "display_name": "GLM-4.7", "description": "Zhipu GLM 4.7 general model"},
        {"name": "kimi-k2", "display_name": "Kimi-K2", "description": "Moonshot Kimi K2 general model"},
        {"name": "kimi-k2-thinking", "display_name": "Kimi-K2-Thinking", "description": "Moonshot Kimi K2 thinking model"},
        {"name": "deepseek-v3.2-chat", "display_name": "DeepSeek-V3.2-Chat", "description": "DeepSeek V3.2 Chat"},
        {"name": "deepseek-v3.2-reasoner", "display_name": "DeepSeek-V3.2-Reasoner", "description": "DeepSeek V3.2 Reasoner"},
        {"name": "deepseek-v3.2", "display_name": "DeepSeek-V3.2-Exp", "description": "DeepSeek V3.2 experimental"},
        {"name": "deepseek-v3.1", "display_name": "DeepSeek-V3.1-Terminus", "description": "DeepSeek V3.1 Terminus"},
        {"name": "deepseek-r1", "display_name": "DeepSeek-R1", "description": "DeepSeek reasoning model R1"},
        {"name": "deepseek-v3", "display_name": "DeepSeek-V3-671B", "description": "DeepSeek V3 671B"},
        {"name": "qwen3-32b", "display_name": "Qwen3-32B", "description": "Qwen3 32B"},
        {"name": "qwen3-235b-a22b-thinking-2507", "display_name": "Qwen3-235B-A22B-Thinking", "description": "Qwen3 235B A22B Thinking (2507)"},
        {"name": "qwen3-235b-a22b-instruct", "display_name": "Qwen3-235B-A22B-Instruct", "description": "Qwen3 235B A22B Instruct"},
        {"name": "qwen3-235b", "display_name": "Qwen3-235B-A22B", "description": "Qwen3 235B A22B"},
        {"name": "minimax-m2", "display_name": "MiniMax-M2", "description": "MiniMax M2"},
        {"name": "minimax-m2.1", "display_name": "MiniMax-M2.1", "description": "MiniMax M2.1"},
    ],
    # GetAIStudioModels() - 第 375-529 行
    "aistudio": [
        {"name": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "description": "Stable release (June 17th, 2025) of Gemini 2.5 Pro"},
        {"name": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "description": "Stable version of Gemini 2.5 Flash"},
        {"name": "gemini-2.5-flash-lite", "display_name": "Gemini 2.5 Flash Lite", "description": "Our smallest and most cost effective model"},
        {"name": "gemini-3-pro-preview", "display_name": "Gemini 3 Pro Preview", "description": "Gemini 3 Pro Preview"},
        {"name": "gemini-3-flash-preview", "display_name": "Gemini 3 Flash Preview", "description": "Our most intelligent model built for speed"},
    ],
    # GetGeminiVertexModels() - 第 198-291 行
    "vertex": [
        {"name": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "description": "Stable release (June 17th, 2025) of Gemini 2.5 Pro"},
        {"name": "gemini-2.5-flash", "display_name": "Gemini 2.5 Flash", "description": "Stable version of Gemini 2.5 Flash"},
        {"name": "gemini-2.5-flash-lite", "display_name": "Gemini 2.5 Flash Lite", "description": "Our smallest and most cost effective model"},
        {"name": "gemini-3-pro-preview", "display_name": "Gemini 3 Pro Preview", "description": "Gemini 3 Pro Preview"},
        {"name": "gemini-3-flash-preview", "display_name": "Gemini 3 Flash Preview", "description": "Our most intelligent model built for speed"},
        {"name": "gemini-3-pro-image-preview", "display_name": "Gemini 3 Pro Image Preview", "description": "Gemini 3 Pro Image Preview"},
    ],
}


def get_static_models_for_provider(provider: str) -> dict:
    """
    获取不支持实时配额查询的 provider 的静态模型列表
    
    Args:
        provider: 账户类型
        
    返回: 包含静态模型列表的配额信息字典
    """
    provider = provider.lower()
    
    if provider not in STATIC_MODELS_PROVIDERS:
        return None
    
    models = STATIC_MODEL_LISTS.get(provider, [])
    
    return {
        "models": [
            {
                "name": m["name"],
                "display_name": m.get("display_name", m["name"]),
                "description": m.get("description", ""),
                "percentage": None,  # 无配额信息
                "reset_time": None,  # 无重置时间
            }
            for m in models
        ],
        "last_updated": int(time.time()),
        "is_forbidden": False,
        "subscription_tier": None,
        "static_list": True,  # 标记为静态列表
        "note": f"此 {provider} 账户暂不支持实时配额查询，仅显示支持的模型列表"
    }


# 禁用代理
NO_PROXY = {"http": None, "https": None}


def refresh_access_token(refresh_token: str, provider: str = "antigravity") -> Optional[dict]:
    """
    使用 refresh_token 刷新 access_token
    
    注意：目前只有 Antigravity 支持实时配额查询，其他服务使用静态模型列表
    
    Args:
        refresh_token: OAuth refresh token
        provider: 账户类型（目前仅支持 "antigravity"）
    """
    # 目前只支持 Antigravity 的实时配额查询
    client_id = ANTIGRAVITY_CLIENT_ID
    client_secret = ANTIGRAVITY_CLIENT_SECRET
    
    try:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            },
            timeout=15,
            proxies=NO_PROXY
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"Token 刷新失败 ({provider}): {resp.status_code} - {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Token 刷新异常 ({provider}): {e}")
        return None


def _get_gemini_cli_headers(access_token: str) -> dict:
    """获取 Gemini CLI 请求需要的 headers"""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": GEMINI_CLI_USER_AGENT,
        "X-Goog-Api-Client": "gl-node/22.17.0",
        "Client-Metadata": "ideType=IDE_UNSPECIFIED,platform=PLATFORM_UNSPECIFIED,pluginType=GEMINI"
    }


def _get_antigravity_headers(access_token: str) -> dict:
    """获取 Antigravity 请求需要的 headers"""
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": ANTIGRAVITY_USER_AGENT
    }


def fetch_project_and_tier(access_token: str, provider: str = "antigravity") -> tuple[Optional[str], Optional[str]]:
    """
    获取项目 ID 和订阅类型
    
    Args:
        access_token: OAuth access token
        provider: 账户类型 ("antigravity" 或 "gemini")
        
    返回: (project_id, subscription_tier)
    """
    # 根据 provider 选择正确的 headers 和 metadata
    if provider == "gemini":
        headers = _get_gemini_cli_headers(access_token)
        metadata = {"ideType": "IDE_UNSPECIFIED"}
    else:
        headers = _get_antigravity_headers(access_token)
        metadata = {"ideType": "ANTIGRAVITY"}
    
    try:
        resp = requests.post(
            f"{CLOUD_CODE_API_URL}/v1internal:loadCodeAssist",
            headers=headers,
            json={"metadata": metadata},
            timeout=15,
            proxies=NO_PROXY
        )
        
        if resp.status_code == 200:
            data = resp.json()
            project_id = data.get("cloudaicompanionProject")
            
            # 优先从 paid_tier 获取订阅等级
            subscription_tier = None
            paid_tier = data.get("paidTier")
            if paid_tier and paid_tier.get("id"):
                subscription_tier = paid_tier["id"]
            else:
                current_tier = data.get("currentTier")
                if current_tier and current_tier.get("id"):
                    subscription_tier = current_tier["id"]
            
            return project_id, subscription_tier
        return None, None
    except Exception as e:
        print(f"获取项目信息失败 ({provider}): {e}")
        return None, None


def fetch_quota_with_token(access_token: str, project_id: Optional[str] = None, provider: str = "antigravity") -> tuple[dict, bool]:
    """
    使用指定 token 获取配额信息
    
    Args:
        access_token: OAuth access token
        project_id: Google Cloud 项目 ID（可选）
        provider: 账户类型 ("antigravity" 或 "gemini")
        
    返回: (配额数据, 是否成功)
    """
    result = {
        "models": [],
        "last_updated": int(time.time()),
        "is_forbidden": False,
        "subscription_tier": None
    }
    
    # 根据 provider 选择正确的 headers
    if provider == "gemini":
        headers = _get_gemini_cli_headers(access_token)
    else:
        headers = _get_antigravity_headers(access_token)
    
    # 获取项目 ID 和订阅等级
    fetched_project_id, subscription_tier = fetch_project_and_tier(access_token, provider)
    result["subscription_tier"] = subscription_tier
    
    final_project_id = project_id or fetched_project_id or "bamboo-precept-lgxtn"
    
    try:
        resp = requests.post(
            f"{CLOUD_CODE_API_URL}/v1internal:fetchAvailableModels",
            headers=headers,
            json={"project": final_project_id},
            timeout=15,
            proxies=NO_PROXY
        )
        
        if resp.status_code == 403:
            result["is_forbidden"] = True
            return result, True  # 403 也算"成功"获取到状态
        
        if resp.status_code == 401:
            # Token 过期，需要刷新
            return result, False
        
        if resp.status_code != 200:
            print(f"配额 API 错误 ({provider}): {resp.status_code} - {resp.text[:200]}")
            return result, False
        
        data = resp.json()
        models = data.get("models", {})
        
        for name, info in models.items():
            # 只保留 gemini 和 claude 相关模型
            if "gemini" not in name.lower() and "claude" not in name.lower():
                continue
            
            # 将 Antigravity API 返回的模型名称转换为 CLIProxyAPI 使用的别名
            alias_name = antigravity_model_name_to_alias(name)
            if alias_name is None:
                # 跳过不支持的模型
                continue
            
            quota_info = info.get("quotaInfo", {})
            remaining_fraction = quota_info.get("remainingFraction", 0)
            percentage = int(remaining_fraction * 100)
            reset_time = quota_info.get("resetTime", "")
            
            result["models"].append({
                "name": alias_name,  # 使用转换后的别名
                "original_name": name,  # 保留原始名称以便调试
                "percentage": percentage,
                "reset_time": reset_time
            })
        
        # 按模型名称排序
        result["models"].sort(key=lambda x: x["name"])
        
        return result, True
        
    except Exception as e:
        print(f"获取配额失败 ({provider}): {e}")
        return result, False


def _extract_tokens_from_auth_data(auth_data: dict, provider: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从认证数据中提取 token 信息
    
    Antigravity 数据结构:
        {"access_token": "...", "refresh_token": "...", "project_id": "..."}
    
    Gemini CLI 数据结构:
        {"token": {"access_token": "...", "refresh_token": "..."}, "project_id": "..."}
    
    返回: (access_token, refresh_token, project_id)
    """
    project_id = auth_data.get("project_id")
    
    if provider == "gemini":
        # Gemini CLI 的 token 在嵌套的 "token" 对象中
        token_data = auth_data.get("token", {})
        if isinstance(token_data, dict):
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
        else:
            access_token = None
            refresh_token = None
    else:
        # Antigravity 的 token 在顶层
        access_token = auth_data.get("access_token")
        refresh_token = auth_data.get("refresh_token")
    
    return access_token, refresh_token, project_id


def get_quota_for_account(auth_data: dict) -> dict:
    """
    为账户获取配额信息
    auth_data 包含账户认证信息（从 auth file 或 management API 获取）
    
    支持的账户类型:
    - antigravity: Antigravity/Google Cloud Code 账户（实时配额）
    - gemini: Gemini CLI 账户（实时配额）
    - codex, claude, qwen, iflow, aistudio, vertex: 静态模型列表（无配额信息）
    """
    provider = auth_data.get("type", "").lower()
    
    # 检查是否支持实时配额查询
    if provider not in SUPPORTED_QUOTA_PROVIDERS:
        # 检查是否支持静态模型列表
        static_result = get_static_models_for_provider(provider)
        if static_result:
            return static_result
        
        # 既不支持实时配额也不支持静态列表
        return {
            "models": [],
            "last_updated": int(time.time()),
            "is_forbidden": False,
            "subscription_tier": None,
            "error": f"配额查询暂不支持 {provider} 类型账号"
        }
    
    # 提取 token 信息
    access_token, refresh_token, project_id = _extract_tokens_from_auth_data(auth_data, provider)
    
    if not access_token and not refresh_token:
        return {
            "models": [],
            "last_updated": int(time.time()),
            "is_forbidden": False,
            "subscription_tier": None,
            "token_status": "missing",
            "error": "缺少 access_token 和 refresh_token"
        }
    
    token_refreshed = False
    original_token = access_token
    
    # 如果有 refresh_token，先刷新 token（因为 access_token 可能已过期）
    if refresh_token:
        new_token_data = refresh_access_token(refresh_token, provider)
        if new_token_data and new_token_data.get("access_token"):
            access_token = new_token_data["access_token"]
            token_refreshed = (access_token != original_token)
    
    if not access_token:
        return {
            "models": [],
            "last_updated": int(time.time()),
            "is_forbidden": False,
            "subscription_tier": None,
            "token_status": "refresh_failed",
            "error": "无法获取有效的 access_token"
        }
    
    # 获取配额
    quota, success = fetch_quota_with_token(access_token, project_id, provider)
    
    # 如果失败且有 refresh_token，尝试刷新 token 后重试
    if not success and refresh_token:
        new_token_data = refresh_access_token(refresh_token, provider)
        if new_token_data and new_token_data.get("access_token"):
            quota, success = fetch_quota_with_token(new_token_data["access_token"], project_id, provider)
            if success:
                token_refreshed = True
    
    # 设置 token 状态
    if token_refreshed:
        quota["token_status"] = "refreshed"
        quota["token_refreshed"] = True
    elif success:
        quota["token_status"] = "valid"
    else:
        quota["token_status"] = "error"
    
    return quota
