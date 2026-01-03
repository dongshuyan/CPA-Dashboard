"""
配额服务 - 负责获取账户配额信息
"""
import requests
import time
from typing import Optional
from config import (
    CLOUD_CODE_API_URL,
    ANTIGRAVITY_USER_AGENT,
    ANTIGRAVITY_CLIENT_ID,
    ANTIGRAVITY_CLIENT_SECRET,
    GOOGLE_TOKEN_URL
)

# 禁用代理
NO_PROXY = {"http": None, "https": None}


def refresh_access_token(refresh_token: str) -> Optional[dict]:
    """使用 refresh_token 刷新 access_token"""
    try:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": ANTIGRAVITY_CLIENT_ID,
                "client_secret": ANTIGRAVITY_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token
            },
            timeout=15,
            proxies=NO_PROXY
        )
        if resp.status_code == 200:
            return resp.json()
        print(f"Token 刷新失败: {resp.status_code} - {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"Token 刷新异常: {e}")
        return None


def fetch_project_and_tier(access_token: str) -> tuple[Optional[str], Optional[str]]:
    """
    获取项目 ID 和订阅类型
    返回: (project_id, subscription_tier)
    """
    try:
        resp = requests.post(
            f"{CLOUD_CODE_API_URL}/v1internal:loadCodeAssist",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity/windows/amd64"
            },
            json={"metadata": {"ideType": "ANTIGRAVITY"}},
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
        print(f"获取项目信息失败: {e}")
        return None, None


def fetch_quota_with_token(access_token: str, project_id: Optional[str] = None) -> tuple[dict, bool]:
    """
    使用指定 token 获取配额信息
    返回: (配额数据, 是否成功)
    """
    result = {
        "models": [],
        "last_updated": int(time.time()),
        "is_forbidden": False,
        "subscription_tier": None
    }
    
    # 获取项目 ID 和订阅等级
    fetched_project_id, subscription_tier = fetch_project_and_tier(access_token)
    result["subscription_tier"] = subscription_tier
    
    final_project_id = project_id or fetched_project_id or "bamboo-precept-lgxtn"
    
    try:
        resp = requests.post(
            f"{CLOUD_CODE_API_URL}/v1internal:fetchAvailableModels",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": ANTIGRAVITY_USER_AGENT
            },
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
            print(f"配额 API 错误: {resp.status_code} - {resp.text[:200]}")
            return result, False
        
        data = resp.json()
        models = data.get("models", {})
        
        for name, info in models.items():
            # 只保留 gemini 和 claude 相关模型
            if "gemini" not in name.lower() and "claude" not in name.lower():
                continue
            
            quota_info = info.get("quotaInfo", {})
            remaining_fraction = quota_info.get("remainingFraction", 0)
            percentage = int(remaining_fraction * 100)
            reset_time = quota_info.get("resetTime", "")
            
            result["models"].append({
                "name": name,
                "percentage": percentage,
                "reset_time": reset_time
            })
        
        # 按模型名称排序
        result["models"].sort(key=lambda x: x["name"])
        
        return result, True
        
    except Exception as e:
        print(f"获取配额失败: {e}")
        return result, False


def get_quota_for_account(auth_data: dict) -> dict:
    """
    为账户获取配额信息
    auth_data 包含账户认证信息（从 auth file 或 management API 获取）
    """
    provider = auth_data.get("type", "").lower()
    
    # 目前只支持 antigravity 类型的配额查询
    if provider != "antigravity":
        return {
            "models": [],
            "last_updated": int(time.time()),
            "is_forbidden": False,
            "subscription_tier": None,
            "error": f"配额查询暂不支持 {provider} 类型账号"
        }
    
    access_token = auth_data.get("access_token")
    refresh_token = auth_data.get("refresh_token")
    project_id = auth_data.get("project_id")
    
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
        new_token_data = refresh_access_token(refresh_token)
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
    quota, success = fetch_quota_with_token(access_token, project_id)
    
    # 如果失败且有 refresh_token，尝试刷新 token 后重试
    if not success and refresh_token:
        new_token_data = refresh_access_token(refresh_token)
        if new_token_data and new_token_data.get("access_token"):
            quota, success = fetch_quota_with_token(new_token_data["access_token"], project_id)
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
