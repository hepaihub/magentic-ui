from magentic_ui.task_team import get_task_team
from magentic_ui.backend.teammanager import TeamManager
from pathlib import PosixPath

config = {'model': 'openai/gpt-4o', 'api_key': 'sk-zsweMXYEBosassgKomLDAvEJiAvlThRQLBmFirihEcpegFN', 'base_url': 'https://aiapi.ihep.ac.cn/apiv2', 'max_retries': 10}
model_config = {
    'model_config': {
        'provider': 'drsai.HepAIChatCompletionClient', 'config': config}, 
        'orchestrator_client': {'provider': 'drsai.HepAIChatCompletionClient', 'config': config}, 
        'coder_client': {'provider': 'drsai.HepAIChatCompletionClient', 'config': config}, 
        'web_surfer_client': {'provider': 'drsai.HepAIChatCompletionClient', 'config': config}, 
        'file_surfer_client': {'provider': 'drsai.HepAIChatCompletionClient', 'config': config}, 
        'action_guard_client': {'provider': 'drsai.HepAIChatCompletionClient', 'config': config}
}

team_manager = TeamManager(
                internal_workspace_root=PosixPath('/home/drsai/.magentic_ui'),
                external_workspace_root=PosixPath('/home/drsai/.magentic_ui'),
                inside_docker=False,
                config=model_config,
            )

# async for message in team_manager.run_stream(
#                 task=task,
#                 team_config=team_config,
#                 state=state,
#                 input_func=input_func,
#                 cancellation_token=cancellation_token,
#                 env_vars=env_vars,
#                 settings_config=settings_config,
#                 run=run,
#             ):