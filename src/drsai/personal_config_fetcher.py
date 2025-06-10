import os
from typing import Dict, Any
from hepai import HepAI
from hepai.types import APIKeyInfo
from dotenv import load_dotenv
load_dotenv()



class PersonalKeyConfigFetcher:
    """获取个人密钥配置"""
    admin_api_key = os.getenv("HEPAI_APP_ADMIN_API_KEY")  # 从环境变量中读取API-KEY
    base_url = "https://aiapi.ihep.ac.cn/apiv2"
    assert admin_api_key, "HEPAI_APP_ADMIN_API_KEY is not set, please set it in .env file"
    client = HepAI(api_key=admin_api_key, base_url=base_url)
    
    def get_personal_key(self, username: str) -> str:
        """获取个人密钥"""
        
        api_key: APIKeyInfo = self.client.fetch_api_key(username=username)
        if not api_key or not api_key.api_key:
            raise ValueError(f"API key for user {username} not found.")
        return api_key.api_key
        
    
    def get_default_config(self, username: str) -> Dict[str, Any]:
        """获取默认配置"""
        
        personal_key = self.get_personal_key(username=username)
        model_configs = f"""model_config: &client
        provider: OpenAIChatCompletionClient
        config:
            model: "openai/gpt-4o"
            base_url: "https://aiapi.ihep.ac.cn/apiv2"
            api_key: "{personal_key}"
            max_retries: 5
            
        orchestrator_client: *client
        coder_client: *client
        web_surfer_client: *client
        file_surfer_client: *client
        action_guard_client: *client
    """

        return {
            "cooperative_planning": True,
            "autonomous_execution": False,
            "allowed_websites": [],
            "max_actions_per_step": 5,
            "multiple_tools_per_call": False,
            "max_turns": 20,
            "approval_policy": "auto-conservative",
            "allow_for_replans": True,
            "do_bing_search": False,
            "websurfer_loop": False,
            "model_configs": model_configs,
            "retrieve_relevant_plans": "never"
        }

