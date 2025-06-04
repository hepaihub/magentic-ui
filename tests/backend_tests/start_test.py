"""
API客户端示例 - 创建会话

这个脚本演示如何调用Magentic-UI的/sessions/端点来创建新会话。
"""

import json
import requests
from typing import Dict, Any
from pathlib import Path
here = Path(__file__).parent.resolve()
# from datetime import datetime 

# config_json_path = here / "config.json"
# # 判断配置文件是否存在，否则创建默认配置文件
# if not config_json_path.exists():
#     with open(config_json_path, "w", encoding="utf-8") as f:
#         f.write(json.dumps(
#             {
#                 "base_url": "http://localhost:8081/api",
#                 "default_session_id": 123,
#                 "user_id": "test_user_123",
#                 "team_id": 123
#             }
#         ))

# # API基础配置
# with open(config_json_path, "r", encoding="utf-8") as f:
#     config = json.load(f)

# 基础URL
BASE_URL = "http://localhost:8081/api"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def get_version() -> Dict[str, Any]:
    """
    获取Magentic-UI版本信息
    
    返回:
        包含版本信息的字典
    """
    version: Dict[str, Any] = requests.get(
        f"{BASE_URL}/version",
        headers=HEADERS
    ).json()
    return version

def create_session(
        user_id: str, 
        name: str|None = None, 
        team_id: int|None = None,
        version: str|None = None
        ) -> Dict[str, Any]:
    """
    创建新会话
    
    参数:
        user_id: 用户唯一标识
        name: 会话名称(可选)
        team_id: 创建的team_id的，
    
    返回:
        包含响应数据的字典
        
    异常:
        抛出requests.HTTPError如果请求失败
    """
    url = f"{BASE_URL}/sessions/"
    payload = {
        "id": 0,
        # "created_at": "2025-05-29T07:51:06.016Z",
        # "updated_at": "2025-05-29T07:51:06.016Z",
        "user_id": user_id,
        "version": version,
        "team_id": team_id,
        "name": name
    }
    
    response = requests.post(
        url,
        headers=HEADERS,
        data=json.dumps(payload)
    )
    response.raise_for_status()  # 如果请求失败抛出异常
    
    return response.json()

if __name__ == "__main__":
    # 示例用法
    try:
        # 获取Magentic-UI版本
        version_dict = get_version()
        # print(f"Magentic-UI版本: {version["data"]['version']}")
        version = version_dict["data"]["version"]

        # 创建测试会话
        result = create_session(
            user_id="test_user_123",
            name="user_id_tester",
            team_id=1,
            version=version
        )
        
        print("会话创建成功:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
    except requests.exceptions.HTTPError as err:
        print(f"请求失败，HTTP错误: {err}")
        if err.response is not None:
            print(f"响应内容: {err.response.text}")
    except requests.exceptions.RequestException as err:
        print(f"请求失败: {err}")
    except json.JSONDecodeError as err:
        print(f"JSON解析失败: {err}")
