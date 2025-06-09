import sys, pathlib
here = pathlib.Path(__file__).parent
magentic_ui_path = str(here.parent)+'/src/magentic_ui'
sys.path.append(magentic_ui_path)
besiii_path = str(here.parent.parent)+'/src/besiii'
sys.path.append(besiii_path)

from typing import Union, Any, Dict, Optional, ClassVar, List, Literal, cast, Callable, Tuple
from pydantic import BaseModel, Field
import yaml
from loguru import logger
import aiofiles
import json

from autogen_core.models import ChatCompletionClient
from autogen_core import CancellationToken, ComponentModel
from autogen_agentchat.agents import UserProxyAgent
# from autogen_agentchat.base import ChatAgent, TaskResult, Team
from autogen_agentchat.messages import AgentEvent, ChatMessage, TextMessage

from magentic_ui.agents import USER_PROXY_DESCRIPTION
from magentic_ui.agents import MagenticAgent
from magentic_ui.magentic_ui_config import MagenticUIConfig, ModelClientConfigs
# from magentic_ui.teams.orchestrator.orchestrator_config import OrchestratorConfig
# from magentic_ui.teams import GroupChat
from magentic_ui.input_func import InputFuncType, make_agentchat_input_func
# from magentic_ui.learning.memory_provider import MemoryControllerProvider
# from magentic_ui.types import Plan

# from besiii.modules.tools.navigator_tool import inspire_search, arxiv_search, docDB_search, web_searching
# from besiii.modules.groupchat.groupchat import CustomGroupChat
# from besiii.modules.agents.CustomAgent import CustomAgent
from besiii.modules.groupchat.orchestrator.orchestrator_config import OrchestratorConfig
from besiii.modules.groupchat.orchestrator import DrSaiGroupChat
from besiii.modules.learning.memory_provider import MemoryControllerProvider
from besiii.magentic_utils.types import Plan

from besiii.modules.tools.rag_client import hairag_client

from besiii.configs import CONST
from besiii.configs.config import load_configs
from besiii.utils.tool import timed_method
from besiii.modules.tools.mapping_json import (
    create_AlgorithmCard, 
    create_JobOptionsCard, 
    create_DrawCard, 
    create_FoMCard, 
    create_TMVACard)
from besiii.modules.tools.tools_workerv2 import (
    call_algorithm_mapping, 
    call_joboption_mapping, 
    call_drawing_mapping, 
    call_optimizer_fom_mapping, 
    call_optimizer_tmva_mapping, 
    call_getting_branch_name, 
    call_boss_jobs_query)
from besiii.modules.tools.tools import get_weather
from besiii.magentic_utils.drsai_magentic_ui_config import DrSaiModelClientConfigs, DrSaiMagenticUIConfig
from besiii.magentic_utils.input_func import InputFuncType, InputRequestType


async def test_create_team() -> DrSaiGroupChat:
    
    # model_configs = load_configs(config_path = CONST.model_client_configs)
    async with aiofiles.open(CONST.model_client_configs) as f:
            drsai_client_yaml = await f.read()
    
        
    # 传入前端配置
    settings_config = {
        'cooperative_planning': True, 
        'autonomous_execution': False, 
        'allowed_websites': [], 
        'max_actions_per_step': 5, 
        'multiple_tools_per_call': False, 
        'max_turns': 20, 
        'approval_policy': 'auto-conservative', 
        'allow_for_replans': True, 
        'do_bing_search': False, 
        'websurfer_loop': False, 
        'model_configs': drsai_client_yaml, 
        'retrieve_relevant_plans': 'never', 
        'memory_controller_key': 'guestuser@gmail.com'}

    model_configs: Dict[str, Any] = {}
    if settings_config.get("model_configs"):
        try:
            model_configs = yaml.safe_load(settings_config["model_configs"])
        except Exception as e:
            logger.error(f"Error loading model configs: {e}")
            raise e

    # Use model configs from settings if available, otherwise fall back to config
    orchestrator_config = model_configs.get("orchestrator_client", None)
    model_client_configs = DrSaiModelClientConfigs(
        orchestrator=orchestrator_config,
        web_surfer=model_configs.get("web_surfer_client",None),
        # coder=model_configs.get("coder_client",None),
        file_surfer=model_configs.get("file_surfer_client",None),
        action_guard=model_configs.get("action_guard_client",None),
        #
        planner=model_configs.get("planner_client",None),
        coder=model_configs.get("coder_client",None),
        tester=model_configs.get("tester_client",None),
        host=model_configs.get("host_client",None),
        parser=model_configs.get("parser_client",None),
    )

    magentic_ui_config = DrSaiMagenticUIConfig(
        **(settings_config or {}),
        model_client_configs=model_client_configs,
        playwright_port=52620,
        novnc_port=41656,
        inside_docker=False,
    )

    orchestrator_config = OrchestratorConfig(
        cooperative_planning=magentic_ui_config.cooperative_planning,
        autonomous_execution=magentic_ui_config.autonomous_execution,
        allowed_websites=magentic_ui_config.allowed_websites,
        plan=magentic_ui_config.plan,
        model_context_token_limit=magentic_ui_config.model_context_token_limit,
        do_bing_search=magentic_ui_config.do_bing_search,
        retrieve_relevant_plans=magentic_ui_config.retrieve_relevant_plans,
        memory_controller_key=magentic_ui_config.memory_controller_key,
        allow_follow_up_input=magentic_ui_config.allow_follow_up_input,
        final_answer_prompt=magentic_ui_config.final_answer_prompt,
    )

    def get_model_client(
        model_client_config: Union[ComponentModel, Dict[str, Any], None],
        is_action_guard: bool = False,
    ) -> ChatCompletionClient:
        if model_client_config is None:
            return ChatCompletionClient.load_component(
                ModelClientConfigs.get_default_client_config()
                if not is_action_guard
                else ModelClientConfigs.get_default_action_guard_config()
            )
        return ChatCompletionClient.load_component(model_client_config)

    # Dr.Sai's agent
    # Weather_Agent = MagenticAgent(
    #     name="Weather_Agent",
    #     model_client=model_client_coder,
    #     description="An agent that provides weather information.",
    #     tools=[get_weather],
    # )

    # model_client_planner = get_model_client(magentic_ui_config.model_client_configs.planner)
    # prompt_planner = load_configs(f'{CONST.PROMPTS_DIR}/agents/planner.yaml')
    # Planner = MagenticAgent(
    #     name="Planner",
    #     model_client=model_client_planner, ## 需要笨一点的模型，不能思考太多
    #     description="A task planning expert can not only break down complex tasks into simple subtasks, but also design efficient and feasible execution plans based on task content. Consult him only when specificly required to make a plan.",
    #     system_message=prompt_planner['system']
    # )

    prompt_coder = load_configs(f'{CONST.PROMPTS_DIR}/agents/coder.yaml')
    model_client_coder = get_model_client(magentic_ui_config.model_client_configs.coder)
    Coder = MagenticAgent(
        name="Coder",
        model_client=model_client_coder,
        tools=[create_AlgorithmCard, create_JobOptionsCard, create_DrawCard, create_FoMCard, create_TMVACard],
        description="An expert proficient in programming, especially well-versed in developing and understanding proprietary code within the high energy physics domain, with extensive experience in programming for the BESIII experiment. He can not execute code blocks or variable cards.",
        system_message=prompt_coder['system'],
        memory_function=hairag_client,
        memory_config={
            "username":"zhangbolun",
            "collection":"DSL",
            "method":"get_full_text",
            "similarity_top_k":1,
            "verbose":False,
        },
        mapping = True,
    )

    model_client_tester = get_model_client(magentic_ui_config.model_client_configs.tester)
    Tester = MagenticAgent(
        name="Tester",
        model_client=model_client_tester,
        tools=[call_algorithm_mapping, call_joboption_mapping, call_drawing_mapping, call_optimizer_fom_mapping, call_optimizer_tmva_mapping, call_getting_branch_name, call_boss_jobs_query],
        description="An Executor who can execute a specified code block or a variable card.",
        system_message = "你是一个代码执行器，你可以执行指定的代码块或变量卡片。不要对其他形式的消息内容做出反应，若有请回复“我只执行代码块”。现在，请查看你的任务。",
        model_client_stream=True,
    )

    async def human_output(
            prompt: str = "",
            cancellation_token: Optional[CancellationToken] = None,
            input_type: InputRequestType = "text_input",)->str:
        return input(f" \n{prompt}: \n")
        # return "Sure"
    # user_proxy_input_func = make_agentchat_input_func(human_output)
    user_proxy = UserProxyAgent(
        description=USER_PROXY_DESCRIPTION,
        name="user_proxy",
        input_func=human_output,
    )
    
    model_client_parser = get_model_client(magentic_ui_config.model_client_configs.parser)
    model_client_host = get_model_client(magentic_ui_config.model_client_configs.host)
    team = DrSaiGroupChat(
        participants=[Coder, Tester, user_proxy],
        orchestrator_config=orchestrator_config,
        model_client_parser = model_client_parser,
        model_client_host = model_client_host,

        memory_provider=None,
    )
    return team 

async def close(team: DrSaiGroupChat):
        """Close the team manager"""
        if team and hasattr(team, "close"):
            logger.info("Closing team")
            await team.close()  # type: ignore
            team= None
            logger.info("Team closed")
        else:
            logger.warning("Team manager is not initialized or already closed")

async def pause_run(team: DrSaiGroupChat) -> None:
    """Pause the run"""
    if team:
        await team.pause()

async def resume_run(team: DrSaiGroupChat) -> None:
    """Resume the run"""
    if team:
        await team.resume()

async def test_start_team(task: str) -> None:
    team = await test_create_team()
    await team.lazy_init()

    # TODO: 创建一个asyncio task来延时停止team
    async def stop_and_close_team(team: DrSaiGroupChat, delay: int = 20) -> None:
        await asyncio.sleep(delay)
        await pause_run(team)
        logger.info("Stopping team")
        await close(team)
        logger.info("Team stopped")
    # asyncio.create_task(stop_and_close_team(team))

    cancellation_token = CancellationToken()
    async for message in team.run_stream(  # type: ignore
        task=task, cancellation_token=cancellation_token
    ):
        if cancellation_token and cancellation_token.is_cancelled():
            break
        if isinstance(message,  TextMessage):
            content = message.content
            try:
                content = json.loads(content)
                print( json.dumps(content, indent=4, ensure_ascii=False) )
            except:
                pass
                print( content )
    


if __name__ == "__main__":
    import asyncio
    task = "帮我测量psi(4260) -> pi+ pi- J/psi (-> mu+ mu-)过程在4.26 GeV能量点上的截面，并且绘制piJpsi的不变质量。先规划后执行。"
    asyncio.run(test_start_team(task = task))