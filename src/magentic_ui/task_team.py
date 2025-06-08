from typing import Union, Any, Dict, Optional
from autogen_core.models import ChatCompletionClient
from autogen_core import ComponentModel
from autogen_agentchat.agents import UserProxyAgent

from .tools.playwright.browser import get_browser_resource_config
from .utils import get_internal_urls
from .teams import GroupChat, RoundRobinGroupChat
from .teams.orchestrator.orchestrator_config import OrchestratorConfig
from .agents import WebSurfer, CoderAgent, USER_PROXY_DESCRIPTION, FileSurfer
from .magentic_ui_config import MagenticUIConfig, ModelClientConfigs
from .types import RunPaths
from .agents.web_surfer import WebSurferConfig
from .agents.users import DummyUserProxy, MetadataUserProxy
from .approval_guard import (
    ApprovalGuard,
    ApprovalGuardContext,
    ApprovalConfig,
    BaseApprovalGuard,
)
from .input_func import InputFuncType, make_agentchat_input_func
from .learning.memory_provider import MemoryControllerProvider

# besiii 
from magentic_ui.agents import MagenticAgent
from besiii.modules.groupchat.orchestrator import DrSaiGroupChat

from besiii.modules.tools.rag_client import hairag_client

from besiii.configs import CONST
from besiii.configs.config import load_configs
# from besiii.utils.tool import timed_method
from besiii.modules.tools.mapping_json import (
    create_AlgorithmCard, 
    create_JobOptionsCard, 
    create_DrawCard, 
    create_FoMCard, 
    create_TMVACard)
# from besiii.modules.tools.tools_workerv2 import (
#     call_algorithm_mapping, 
#     call_joboption_mapping, 
#     call_drawing_mapping, 
#     call_optimizer_fom_mapping, 
#     call_optimizer_tmva_mapping, 
#     call_getting_branch_name, 
#     call_boss_jobs_query)
from besiii.modules.reply_functions.workerv2_reply import woker_v2_reply_function
# from besiii.modules.tools.tools import get_weather
from besiii.magentic_utils.drsai_magentic_ui_config import DrSaiModelClientConfigs, DrSaiMagenticUIConfig
# from besiii.magentic_utils.input_func import InputFuncType, InputRequestType
# from drsai import Thread

async def get_task_team_drsai(
    magentic_ui_config: Optional[DrSaiMagenticUIConfig] = None,
    input_func: Optional[InputFuncType] = None,
    *,
    paths: RunPaths,
) -> GroupChat | RoundRobinGroupChat:
    """
    Creates and returns a GroupChat team with specified configuration.

    Args:
        magentic_ui_config (MagenticUIConfig, optional): Magentic UI configuration for team. Default: None.
        paths (RunPaths): Paths for internal and external run directories.

    Returns:
        GroupChat | RoundRobinGroupChat: An instance of GroupChat or RoundRobinGroupChat with the specified agents and configuration.
    """
    if magentic_ui_config is None:
        magentic_ui_config = DrSaiMagenticUIConfig()

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

    # groupchat manager config
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

    # groupchat manager clients
    model_client_parser = get_model_client(magentic_ui_config.model_client_configs.parser)
    model_client_host = get_model_client(magentic_ui_config.model_client_configs.host)

    # TODO:  get thread
    # thread = Thread(
    #         id=uu,
    #         object="thread",
    #         created_at=int(time.time()),
    #         metadata={},
    #         tool_resources=tool_resources,
    #         username=username,
    #         order_id=order_id
    #     )

    user_proxy: DummyUserProxy | MetadataUserProxy | UserProxyAgent

    if magentic_ui_config.user_proxy_type == "dummy":
        user_proxy = DummyUserProxy(name="user_proxy")
    elif magentic_ui_config.user_proxy_type == "metadata":
        assert (
            magentic_ui_config.task is not None
        ), "Task must be provided for metadata user proxy"
        assert (
            magentic_ui_config.hints is not None
        ), "Hints must be provided for metadata user proxy"
        assert (
            magentic_ui_config.answer is not None
        ), "Answer must be provided for metadata user proxy"
        user_proxy = MetadataUserProxy(
            name="user_proxy",
            description="Metadata User Proxy Agent",
            task=magentic_ui_config.task,
            helpful_task_hints=magentic_ui_config.hints,
            task_answer=magentic_ui_config.answer,
            model_client=model_client_host,
        )
    else:
        user_proxy_input_func = make_agentchat_input_func(input_func)
        user_proxy = UserProxyAgent(
            description=USER_PROXY_DESCRIPTION,
            name="user_proxy",
            input_func=user_proxy_input_func,
        )
    
    # coder client
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

    # tester client
    model_client_tester = get_model_client(magentic_ui_config.model_client_configs.tester)
    Tester = MagenticAgent(
        name="Tester",
        model_client=model_client_tester,
        # tools=[call_algorithm_mapping, call_joboption_mapping, call_drawing_mapping, call_optimizer_fom_mapping, call_optimizer_tmva_mapping, call_getting_branch_name, call_boss_jobs_query],
        description="An Executor who can execute a specified code block or a variable card.",
        system_message = "你是一个代码执行器，你可以执行指定的代码块或变量卡片。不要对其他形式的消息内容做出反应，若有请回复“我只执行代码块”。现在，请查看你的任务。",
        allow_reply_function = True,
        reply_function=woker_v2_reply_function,
    )
    
    team = DrSaiGroupChat(
        participants=[Coder, Tester, user_proxy],
        orchestrator_config=orchestrator_config,
        model_client_parser = model_client_parser,
        model_client_host = model_client_host,
        memory_provider=None,
    )

    if (
        orchestrator_config.memory_controller_key is not None
        and orchestrator_config.retrieve_relevant_plans in ["reuse", "hint"]
    ):
        memory_provider = MemoryControllerProvider(
            internal_workspace_root=paths.internal_root_dir,
            external_workspace_root=paths.external_root_dir,
            inside_docker=magentic_ui_config.inside_docker,
        )
    else:
        memory_provider = None

    team = DrSaiGroupChat(
        participants=[Coder, Tester, user_proxy],
        orchestrator_config=orchestrator_config,
        model_client_parser = model_client_parser,
        model_client_host = model_client_host,
        memory_provider=memory_provider,
    )

    await team.lazy_init()
    return team



async def get_task_team(
    magentic_ui_config: Optional[MagenticUIConfig] = None,
    input_func: Optional[InputFuncType] = None,
    *,
    paths: RunPaths,
) -> GroupChat | RoundRobinGroupChat:
    """
    Creates and returns a GroupChat team with specified configuration.

    Args:
        magentic_ui_config (MagenticUIConfig, optional): Magentic UI configuration for team. Default: None.
        paths (RunPaths): Paths for internal and external run directories.

    Returns:
        GroupChat | RoundRobinGroupChat: An instance of GroupChat or RoundRobinGroupChat with the specified agents and configuration.
    """
    if magentic_ui_config is None:
        magentic_ui_config = MagenticUIConfig()

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

    if not magentic_ui_config.inside_docker:
        assert (
            paths.external_run_dir == paths.internal_run_dir
        ), "External and internal run dirs must be the same in non-docker mode"

    model_client_orch = get_model_client(
        magentic_ui_config.model_client_configs.orchestrator
    )
    approval_guard: BaseApprovalGuard | None = None

    approval_policy = (
        magentic_ui_config.approval_policy
        if magentic_ui_config.approval_policy
        else "never"
    )

    websurfer_loop_team: bool = (
        magentic_ui_config.websurfer_loop if magentic_ui_config else False
    )

    model_client_coder = get_model_client(magentic_ui_config.model_client_configs.coder)
    model_client_file_surfer = get_model_client(
        magentic_ui_config.model_client_configs.file_surfer
    )
    browser_resource_config, _novnc_port, _playwright_port = (
        get_browser_resource_config(
            paths.external_run_dir,
            magentic_ui_config.novnc_port,
            magentic_ui_config.playwright_port,
            magentic_ui_config.inside_docker,
        )
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
    websurfer_model_client = magentic_ui_config.model_client_configs.web_surfer
    if websurfer_model_client is None:
        websurfer_model_client = ModelClientConfigs.get_default_client_config()
    websurfer_config = WebSurferConfig(
        name="web_surfer",
        model_client=websurfer_model_client,
        browser=browser_resource_config,
        single_tab_mode=False,
        max_actions_per_step=magentic_ui_config.max_actions_per_step,
        url_statuses={key: "allowed" for key in orchestrator_config.allowed_websites}
        if orchestrator_config.allowed_websites
        else None,
        url_block_list=get_internal_urls(magentic_ui_config.inside_docker, paths),
        multiple_tools_per_call=magentic_ui_config.multiple_tools_per_call,
        downloads_folder=str(paths.internal_run_dir),
        debug_dir=str(paths.internal_run_dir),
        animate_actions=True,
        start_page=None,
        use_action_guard=True,
        to_save_screenshots=False,
    )

    user_proxy: DummyUserProxy | MetadataUserProxy | UserProxyAgent

    if magentic_ui_config.user_proxy_type == "dummy":
        user_proxy = DummyUserProxy(name="user_proxy")
    elif magentic_ui_config.user_proxy_type == "metadata":
        assert (
            magentic_ui_config.task is not None
        ), "Task must be provided for metadata user proxy"
        assert (
            magentic_ui_config.hints is not None
        ), "Hints must be provided for metadata user proxy"
        assert (
            magentic_ui_config.answer is not None
        ), "Answer must be provided for metadata user proxy"
        user_proxy = MetadataUserProxy(
            name="user_proxy",
            description="Metadata User Proxy Agent",
            task=magentic_ui_config.task,
            helpful_task_hints=magentic_ui_config.hints,
            task_answer=magentic_ui_config.answer,
            model_client=model_client_orch,
        )
    else:
        user_proxy_input_func = make_agentchat_input_func(input_func)
        user_proxy = UserProxyAgent(
            description=USER_PROXY_DESCRIPTION,
            name="user_proxy",
            input_func=user_proxy_input_func,
        )

    if magentic_ui_config.user_proxy_type in ["dummy", "metadata"]:
        model_client_action_guard = get_model_client(
            magentic_ui_config.model_client_configs.action_guard,
            is_action_guard=True,
        )

        # Simple approval function that always returns yes
        def always_yes_input(prompt: str, input_type: str = "text_input") -> str:
            return "yes"

        approval_guard = ApprovalGuard(
            input_func=always_yes_input,
            default_approval=False,
            model_client=model_client_action_guard,
            config=ApprovalConfig(
                approval_policy=approval_policy,
            ),
        )
    elif input_func is not None:
        model_client_action_guard = get_model_client(
            magentic_ui_config.model_client_configs.action_guard
        )
        approval_guard = ApprovalGuard(
            input_func=input_func,
            default_approval=False,
            model_client=model_client_action_guard,
            config=ApprovalConfig(
                approval_policy=approval_policy,
            ),
        )
    with ApprovalGuardContext.populate_context(approval_guard):
        web_surfer = WebSurfer.from_config(websurfer_config)
    if websurfer_loop_team:
        # simplified team of only the web surfer
        team = RoundRobinGroupChat(
            participants=[web_surfer, user_proxy],
            max_turns=10000,
        )
        await team.lazy_init()
        return team

    coder_agent = CoderAgent(
        name="coder_agent",
        model_client=model_client_coder,
        work_dir=paths.internal_run_dir,
        bind_dir=paths.external_run_dir,
        model_context_token_limit=magentic_ui_config.model_context_token_limit,
        approval_guard=approval_guard,
    )

    file_surfer = FileSurfer(
        name="file_surfer",
        model_client=model_client_file_surfer,
        work_dir=paths.internal_run_dir,
        bind_dir=paths.external_run_dir,
        model_context_token_limit=magentic_ui_config.model_context_token_limit,
        approval_guard=approval_guard,
    )

    if (
        orchestrator_config.memory_controller_key is not None
        and orchestrator_config.retrieve_relevant_plans in ["reuse", "hint"]
    ):
        memory_provider = MemoryControllerProvider(
            internal_workspace_root=paths.internal_root_dir,
            external_workspace_root=paths.external_root_dir,
            inside_docker=magentic_ui_config.inside_docker,
        )
    else:
        memory_provider = None

    team = GroupChat(
        participants=[web_surfer, user_proxy, coder_agent, file_surfer],
        orchestrator_config=orchestrator_config,
        model_client=model_client_orch,
        memory_provider=memory_provider,
    )

    await team.lazy_init()
    return team

# async def get_task_team(
#     magentic_ui_config: Optional[MagenticUIConfig] = None,
#     input_func: Optional[InputFuncType] = None,
#     *,
#     paths: RunPaths,
# ) -> GroupChat | RoundRobinGroupChat:
#     if 