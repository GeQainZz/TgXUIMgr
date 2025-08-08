# query_logic.py
from datetime import datetime
import config
from xui_api import XUIApi

async def query_user_data(panel_name: str, email: str) -> (bool, dict or str):
    """
    核心用户数据查询逻辑.
    
    :param panel_name: 面板名称
    :param email: 用户 email
    :return: 一个元组 (success, result). 
             成功时 result 是一个包含数据的字典.
             失败时 result 是一个错误信息字符串.
    """
    panel_config = config.get_panel_config(panel_name)
    if not panel_config:
        return False, f"未找到名为 '{panel_name}' 的面板配置。"

    api = XUIApi(panel_config["url"], panel_config["username"], panel_config["password"])
    
    inbounds_data = await api.get_inbounds()
    if not inbounds_data or not inbounds_data.get("success"):
        return False, "无法从面板获取数据，请稍后再试或联系管理员。"

    found_inbound = None
    for inbound in inbounds_data.get("obj", []):
        clients = inbound.get("clientStats", [])
        for client in clients:
            if client.get("email") == email:
                found_inbound = client
                found_inbound.update({
                    'total': client.get('total', inbound.get('total', 0)),
                    'expiryTime': client.get('expiryTime', inbound.get('expiryTime', 0))
                })
                break
        if found_inbound:
            break

    if found_inbound:
        used_bytes = found_inbound.get("up", 0) + found_inbound.get("down", 0)
        total_bytes = found_inbound.get("total", 0)
        
        used_gb = used_bytes / (1024**3)
        total_gb = total_bytes / (1024**3)
        
        expiry_ts = found_inbound.get("expiryTime", 0)
        expiry_date = datetime.fromtimestamp(expiry_ts / 1000).strftime('%Y-%m-%d') if expiry_ts > 0 else "永不过期"

        return True, {
            "email": email,
            "panel_name": panel_name,
            "used_gb": f"{used_gb:.2f}",
            "total_gb": f"{total_gb:.2f}",
            "expiry_date": expiry_date,
        }
    else:
        return False, f"在 '{panel_name}' 上未找到用户名为 '{email}' 的节点。"
