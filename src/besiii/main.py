from besiii.modules.tools.navigator_tool import inspire_search, arxiv_search, docDB_search, web_searching
from drsai import (
    AssistantAgent, UserProxyAgent, 
    SelectorGroupChat,
    HepAIChatCompletionClient
    )

import os

class DRSAI_BESIII:

    def __init__(
            self,
            base_model: str = None,
            api_key: str = None,
            base_url: str = None,
            **kwargs
            ):
        
        self.base_model = base_model or "openai/gpt-4o"
        self.api_key = api_key or os.environ.get("HEPAI_API_KEY")
        self.base_url = base_url or "https://aiapi.ihep.ac.cn/apiv2"
        self.model_client = HepAIChatCompletionClient(
            model=self.base_model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def load_agents(self):

        agent01 = AssistantAgent(
            name="Personal-Assistant",
            model_client=self.model_client,
            system_message="You are a helpful assistant.",
            description="A personal assistant that can help you with various tasks.",
            reflect_on_tool_use=False,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )

        agent02 = AssistantAgent(
            name="Navigator",
            model_client=self.model_client,
            tools=[inspire_search, arxiv_search, docDB_search, web_searching],
            system_message="You can search the arxiv paper, website, or any other database by web search or API.",
            description="An navigator who can search for data from databases like arxiv.",
            reflect_on_tool_use=False,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )

