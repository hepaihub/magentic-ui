# 标准库导入
import asyncio
import os, json
from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import (
    Any,
    Literal,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

# 第三方库导入
from openai import Stream

# 项目内部模块导入
from autogen_core import (
    AgentId,
    AgentInstantiationContext,
    CancellationToken,
    DefaultTopicId,
    MessageContext,
    event,
    rpc,
)
from autogen_agentchat.base import ChatAgent, Response, TaskResult, TerminationCondition
from autogen_agentchat.messages import (
    AgentEvent,
    BaseChatMessage,
    ChatMessage,
    ModelClientStreamingChunkEvent,
    StopMessage,
    TextMessage,
    ToolCallSummaryMessage,
    ToolCallRequestEvent,
)
from autogen_core.models import (
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResultMessage,
    LLMMessage,
    UserMessage,
    AssistantMessage,
    SystemMessage,
    RequestUsage
)
from autogen_agentchat.state import RoundRobinManagerState
from autogen_agentchat.teams._group_chat._chat_agent_container import ChatAgentContainer
from autogen_agentchat.teams._group_chat._events import (
    GroupChatAgentResponse,
    GroupChatMessage,
    GroupChatRequestPublish,
    GroupChatStart,
    GroupChatTermination,
)

from drsai import BaseChatAgent, DrSaiRoundRobinGroupChat, HepAIChatCompletionClient
from drsai.modules.managers.base_thread import Thread
from drsai.modules.managers.base_thread_message import Content, Text, ThreadMessage
from drsai.modules.managers.threads_manager import ThreadsManager

# 相对路径导入
from .task import Task
from besiii.modules.groupchat.groupchat_mgr import CustomGroupChatManager
from besiii.modules.agents.CustomAgent import CustomAgent
from besiii.utils import str_utils
from besiii.configs.config import load_configs
from besiii.configs import constant as CONST
from besiii.configs.prompts.groupchat.host_action import ask_Planner, ask_Coder, ask_Tester, ask_Editor, ask_Navigator, ask_Charm, ask_TaskManager, ask_WebNavigator
import interface

class CustomGroupChat(DrSaiRoundRobinGroupChat):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs) 
        self._root_task = Task(content="", source="", metadata={"global_info": {"job_info": []}}) # 初始化根任务
        self._current_task = self.get_next_task(current_task=self._root_task) # 继承历史任务树的current_task
        self._max_turns = kwargs.get('max_turns', None)
        self._stop_reason = ""
        self.data = []
    
    def _create_group_chat_manager_factory(
        self,
        **kwargs,
    ) -> Callable[[], CustomGroupChatManager]:
        def _factory() -> CustomGroupChatManager:
            return CustomGroupChatManager(
                thread=self._thread,
                thread_mgr=self._thread_mgr,
                **kwargs,
            )

        return _factory
    
    @property
    def current_task(self) -> Task:
        return self._current_task
    
    @property
    def root_task(self) -> Task:
        return self._root_task

    async def run_stream(
        self,
        *,
        task: str | ChatMessage | Sequence[ChatMessage] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[AgentEvent | ChatMessage | TaskResult, None]:
        # Create the messages list if the task is a string or a chat message.
        messages: List[ChatMessage] = [] ## 历史
        ######## 有待商榷
        chat_id=self._thread.metadata["extra_requests"].get('chat_id',None)
        base_models=self._thread.metadata["extra_requests"].get('base_models',None)
        message_id=self._thread.metadata["extra_requests"].get('message_id',None)
        history_messages=self._thread.metadata["extra_requests"].get('history_oai_messages',None)
        api_key=self._thread.metadata["extra_requests"].get('apikey',None)
        # 将消息传递给守护进程
        interface.send_history_messages({
            "chat_id": chat_id,
            "base_models": base_models,
            "message_id": message_id,
            "history_messages": [],
            "api_key":api_key
        })
        # with open('test.json','w',encoding='utf-8') as f:
        #     json.dump(history_messages,f,ensure_ascii=False,indent=4)
        print("history_messages",history_messages)

        # 从守护进程获取当前智能体是否有在运行
        status=interface.get_status(chat_id)

        # 获取当前任务由谁接管,默认由前端接管
        manager=interface.get_manager(chat_id)

        if task=="获取后台消息":
            # 将后台运行时的消息抛出到前台
            async for message in interface.get_backend_message(chat_id):
                yield message
                # pass
        # elif task=="终止任务":
        #     interface.kill_thread(chat_id)

        # elif status["running_status"] !="continue" and  status["running_status"] !="None":
        # 获取是谁监管。
        elif manager=="backend":
            if task == "status":
                    tester = self.get_expert("Tester")
                    gen_tester = tester.on_messages_stream([TextMessage(content=f"请查询jobid: {self._current_task.metadata['jobid']}的状态", source="user")], CancellationToken())
                    async for message in gen_tester:
                        if isinstance(message, Response):
                            yield message.chat_message
                            # interface.store_backend_massage(chat_id,message.chat_message,manager)
                            response = message
                        else:
                            yield message
            else:
                yield ModelClientStreamingChunkEvent(content=f"当前存在任务正在进行，执行的agent: {status['agent']}，执行的状态：{status['running_status']}", source="Host")
        else:
            # 标记任务开始运行
            interface.send_status({
                                "agent":"None",
                                "running_status":'running',
                                "chat_id":chat_id,
                                "task_finished":False
                            })
            
            # 从thread中获取历史消息
            history_thread_messages: List[ThreadMessage] = self._thread.messages
            for history_thread_message in history_thread_messages:
                messages.append(TextMessage(content=history_thread_message.content_str(), source=history_thread_message.sender))
        
            ## 加载历史任务树
            if self._thread.metadata.get('root_task', None) is not None:
                self._root_task = self.mapping_json2task(self._thread.metadata['root_task']) # 历史任务树的根任务
                ## 更新并检索首个未完成的任务（即current_task）
                self._current_task = self.get_next_task(current_task=self._root_task) # 继承历史任务树的current_task

            ## detect Long Task
            is_continue = True
            if self._current_task.status == "paused":
                if task == "status":
                    tester = self.get_expert("Tester")
                    gen_tester = tester.on_messages_stream([TextMessage(content=f"请查询jobid: {self._current_task.metadata['jobid']}的状态", source="user")], CancellationToken())
                    async for message in gen_tester:
                        if isinstance(message, Response):
                            yield message.chat_message
                            # interface.store_backend_massage(chat_id,message.chat_message,manager)
                            response = message
                        else:
                            yield message
                            # interface.store_backend_massage(chat_id,message,manager)
                    self._stop_reason = "Query the status of long tasks"
                    is_continue = False
                elif task == "continue":
                    self._current_task.set_completed("Long Task finished")
                    self._current_task = self.get_next_task() ## 直接跳转到下一个任务
                    if self._current_task == self._root_task:
                        self._thread.metadata['root_task'] = self.mapping_task2json(self._root_task) # 更新任务树
                        yield ModelClientStreamingChunkEvent(content=f"All previous tasks are complete. Please start a new task.", source="Host")
                        # interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=f"All previous tasks are complete. Please start a new task.", source="Host"),manager)
                        self._stop_reason = "All tasks completed"
                        is_continue = False
                else:
                    yield ModelClientStreamingChunkEvent(content=f"You have unfinished long tasks! Please hold on. Enter 'status' to check the status of the job.", source="Host")
                    interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=f"You have unfinished long tasks! Please hold on. Enter 'status' to check the status of the job.", source="Host"),manager)
                    is_continue = False
            else:
                await self.update_tasks_from_message(task) ## 将新任务插入到旧任务树中

            if is_continue:
                if self._is_running:
                    raise ValueError("The team is already running, it cannot run again until it is stopped.")
                self._is_running = True
                
                # Start the runtime.
                # TODO: The runtime should be started by a managed context.
                self._runtime.start()

                if not self._initialized:
                    await self._init(self._runtime) # 注册participants + group chat manager

                # Start a coroutine to stop the runtime and signal the output message queue is complete.
                async def stop_runtime() -> None:
                    try:
                        await self._runtime.stop_when_idle()
                    finally:
                        await self._output_message_queue.put(None)

                # shutdown_task = asyncio.create_task(stop_runtime())

                host = self.get_expert("Host") # 获取Host对象
                parser = self.get_expert("Parser") # 获取Parser对象

                try:
                    # Run the team by sending the start message to the group chat manager.
                    # The group chat manager will start the group chat by relaying the message to the participants
                    # and the closure agent.
                    ## 这里进到SingleThreadedAgentRuntime并执行groupchat manager的初始化
                    # await self._runtime.send_message(
                    #     GroupChatStart(messages=messages),
                    #     recipient=AgentId(type=self._group_chat_manager_topic_type, key=self._team_id),
                    #     cancellation_token=cancellation_token,
                    # )
                    # Collect the output messages in order.

                    ## 定义消息
                    ### messages # 单纯的问题+assistant回复的QA对，问题内容不附加任何额外信息。 This is for Host
                    messages_expert = [] # for expert，包含核心任务+围绕任务内容的多轮讨论
                    conclusion = TextMessage(content="", source="user") ## 任务结束后的结论，可能是系统消息或QA对
                    speaker = host ## 当前发言者，默认是Host

                    gen_runtimeData = True ## 是否生成runtimeData
                    task_round = 1
                    while self._current_task != self._root_task: ## 循环执行单任务，直到所有任务都完成
                        ## 群聊终止条件判断
                        if await self.is_termination_condition():
                            break
                        
                        ## 更新current_task状态
                        self._current_task.status = "in_progress"
                        current_task_content = self._current_task.content
                        print(f"\033[31m\n\n============================================================================\nCurrent task: {current_task_content}\n\033[0m")

                        ## 发送任务树给前端
                        yield ModelClientStreamingChunkEvent(content=self.get_task_map(), source="TaskManager")
                        # for chunk in str_utils.chunk_string(self.get_task_map(), chunk_size=10):
                        #     yield ModelClientStreamingChunkEvent(content=chunk, source="TaskManager")
                        if interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=self.get_task_map(), source="TaskManager"),manager):raise Exception

                        ## 添加任务prompt
                        messages.append(TextMessage(content=current_task_content, source="user"))
                        messages_expert = []
                        if task_round == 1 and gen_runtimeData:
                            self.data.append(self.gen_data(None, messages, Response(chat_message=TextMessage(content="", source="user"))))

                        ## 单任务处理循环
                        for discussion_round in range(1, self._max_turns):
                            #messages[-1].content = await self.build_expert_advice(current_task_content, messages_expert)

                            interface.send_status({
                                    "agent":"host",
                                    "running_status":'running',
                                    "chat_id":chat_id,
                                    "task_finished":False
                                })
                            ## 单任务结束条件判断
                            if discussion_round == self._max_turns - 1:
                                gen3 = await self.summarize(messages_expert)
                                async for message in gen3:
                                    if isinstance(message, Response):
                                        yield message.chat_message
                                        if interface.store_backend_massage(chat_id,message.chat_message,manager):raise Exception
                                        response3 = message
                                    else:
                                        yield message
                                        if interface.store_backend_massage(chat_id,message,manager):raise Exception
                                conclusion = response3.chat_message
                                break

                            ## Host生成回复
                            # print(f"\n正在咨询专家...")
                            # yield TextMessage(content="正在咨询专家...", source="user")
                            # yield ModelClientStreamingChunkEvent(content="正在咨询专家...", type="ModelClientStreamingChunkEvent")
                            # yield ModelClientStreamingChunkEvent(content=f"\n\n**{host.name}发言(循环{task_round})：**\n\n", source=f'')
                            # response = await host.on_messages(messages, CancellationToken())
                            #print(f"\n[{host.name}] speaking:")
                            if discussion_round == 1:
                                gen = host.on_messages_stream(messages, CancellationToken())  # 可以是tool call的结果，或者是host的直接回复
                            else:
                                gen = host.on_messages_stream(messages_expert, CancellationToken())  # 预期这里只应调用tool_call选人
                            
                            async for message in gen:
                                if isinstance(message, ModelClientStreamingChunkEvent):
                                    yield message
                                    if interface.store_backend_massage(chat_id,message,manager):raise Exception
                                elif isinstance(message, Response):
                                    #yield message.chat_message
                                    if interface.store_backend_massage(chat_id,message.chat_message,manager):raise Exception
                                    response = message
                                # else:
                                #     yield message
                                #     if interface.store_backend_massage(chat_id,message,manager):raise Exception

                            reply_host = await self.parse_host_response(response)
                            if gen_runtimeData:
                                self.data.append(self.gen_data(host, messages, response))

                            if isinstance(reply_host, str): ## 无专家建议，直接输出Host的最终回答，格式应为str
                                #await self.handle_host_response(response, messages, messages_expert)
                                conclusion = response.chat_message
                                break
                            elif isinstance(reply_host, List): ## 选择专家
                                dict_reply = reply_host[0] ## 选择最后一个专家指示，因为可能由于历史消息干扰同时选择多个专家
                                next_speaker_name = dict_reply.get("expert", None)
                                request = dict_reply.get("request", self._current_task.content)
                                
                                interface.send_status({
                                        "agent":next_speaker_name,
                                        "running_status":'None',
                                        "chat_id":chat_id,
                                        "task_finished":False
                                    })

                                ## 让专家说话
                                if conclusion.source == "Coder": ## Coder回复后，下次默认使用Tester执行
                                    next_speaker_name = "Tester"
                                    request = f"Please execute the code for the task: {conclusion.content}"
                                
                                #yield ModelClientStreamingChunkEvent(content=f"选中智能体`{next_speaker_name}`，传递信息：`{request}`", source="Host")
                                #print(f"\n[{next_speaker_name}] speaking:")
                                job_info = self.get_job_info()
                                if job_info and next_speaker_name != "Tester":
                                    request += f"Please handle the request: {request}\n\nHere are some additional information that might be useful for you to handle the request: {job_info}"
                                print(f"\n\033[31mrequest:\n{request}\n\033[0m")

                                messages_expert.append(TextMessage(content=request, source="user")) # add current_task_content?
                            
                                speaker = self.get_expert(next_speaker_name)
                                # reply_expert = await speaker.on_messages_stream([TextMessage(content=request, source="user")], CancellationToken())
                                gen2 = speaker.on_messages_stream([TextMessage(content=request, source="user")], CancellationToken())
                                async for message in gen2:
                                    if isinstance(message, Response):
                                        yield message.chat_message
                                        response2 = message
                                    else:
                                        yield message
                                reply_expert = response2.chat_message.content
                                conclusion = response2.chat_message

                                ## 将专家回复添加到expert_replies列表中
                                if gen_runtimeData:
                                    self.data.append(self.gen_data(speaker, messages_expert, response2))
                                messages_expert.append(TextMessage(content=f"{speaker.name}'s thoughts: {reply_expert}", source=speaker.name))

                                ## 处理特殊专家的回复内容
                                if speaker.name == "Tester":
                                    ## 添加全局作业信息
                                    new_file_path = str_utils.extract_specific_info(conclusion.content)
                                    self._root_task.metadata['global_info']["job_info"].append(
                                        {
                                            "task_id": self._current_task.id,
                                            "task_content": self._current_task.content,
                                            "conclusion": new_file_path
                                        }
                                    )

                                    ## detect Long Task
                                    # flag_LT = True if "long-task job_ids" in conclusion.content else True
                                    job_ids=[int(i[1]) for i in re.findall("(\n\| +(\d+) +\| +\d+ \|)",conclusion.content.split("long-task job_ids:")[-1],re.DOTALL)]
                                    # 
                                    if interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=f"\n[Attention]: 当前任务已被后端接管。\n", source="Tester"),"backend"):raise Exception
                                    if job_ids !=[]:
                                        self._current_task.status = "paused"
                                        
                                        interface.store_job_ids({
                                            "chat_id":chat_id,
                                            "job_ids":job_ids
                                        })
                                        
                                        conclusion.content += "\n\nYour task has been processed successfully."
                                        # self._current_task.metadata['jobid'] = "123456"

                                        # TODO: use re.findall ... to search the job_ids in the msg.
                                        self._current_task.metadata['jobid'] = job_ids

                                        yield ModelClientStreamingChunkEvent(content=f"\n[Attention]: Your task has been submitted successfully. Please wait until the results are available.\nUse these messages to check the task status:\n- `status`: check the status of your task\n- `continue`: continue your conversation", source="Tester")
                                        # for chunk in str_utils.chunk_string(f"\n[Attention]: Your task has been submitted successfully. Please wait until the results are available.\nUse these messages to check the task status:\n- `status`: check the status of your task\n- `continue`: continue your conversation", chunk_size=10):
                                        #     yield ModelClientStreamingChunkEvent(content=chunk, source="Tester")
                                        if interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=f"\n[Attention]: Your task has been submitted successfully. Please wait until the results are available.\nUse these messages to check the task status:\n- `status`: check the status of your task\n- `continue`: continue your conversation", source="Tester"),manager):raise Exception
                                        interface.send_status({
                                                "agent":"host",
                                                "running_status":'wait',
                                                "chat_id":chat_id,
                                                "task_finished":False
                                            })
                                        break

                                ## reflect
                                human_ok = True
                                if human_ok:
                                    #conclusion = response2.chat_message
                                    break
                            else:
                                raise ValueError(f"Invalid host response: {reply_host}")

                        ## 单轮任务讨论结束，更新任务树
                        messages.append(conclusion)
                        if speaker.name == "Planner" or speaker.name == "TaskManager":
                            yield ModelClientStreamingChunkEvent(content="Task tree updating...\n", source="System")
                            response_parser = await parser.on_messages([conclusion], CancellationToken())
                            conclusion = response_parser.chat_message
                            print(f"\n\n[Parser]:\n{conclusion.content}")
                            if gen_runtimeData:
                                    self.data.append(self.gen_data(parser, [conclusion], response_parser))
                        result = await self.update_tasks_from_message(conclusion)
                        if result:
                            yield ModelClientStreamingChunkEvent(content=result, source="System")
                            if interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content=result, source="System"),manager):raise Exception
                        await self.update_thread(messages[-2:])
                        task_round += 1
                    
                    # Yield the final result.
                    self._is_running = False ## Indicate that the team is no longer running.
                    if gen_runtimeData:
                        self.save_runtime_data()
                    yield TaskResult(messages=messages, stop_reason=self._stop_reason)
                    if interface.store_backend_massage(chat_id,TaskResult(messages=messages, stop_reason=self._stop_reason),manager):raise Exception
                    if self._current_task == self._root_task and interface.get_status(chat_id)["running_status"] !="wait":
                            # interface.send_status({
                            #     "agent":"",
                            #     "running_status":'None',
                            #     "chat_id":chat_id,
                            #     "task_finished":True
                            #     })
                            if interface.store_backend_massage(chat_id,ModelClientStreamingChunkEvent(content="task 结束\n", source="System"),"frontend"):raise Exception
                except Exception as e:
                    self._stop_reason = str(e)
                    self._is_running = False
                    print(f"\033[31m\n\n============\n{self._stop_reason}\n==========\n\033[0m")
                    if gen_runtimeData:
                        self.save_runtime_data()
                    raise e
            else:
                self._is_running = False
                yield TaskResult(messages=messages, stop_reason=self._stop_reason)
                if interface.store_backend_massage(chat_id,message.chat_message,manager):raise Exception
        
    async def run_stream_old(
        self,
        *,
        task: str | ChatMessage | Sequence[ChatMessage] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[AgentEvent | ChatMessage | TaskResult, None]:
        # Create the messages list if the task is a string or a chat message.
        messages: List[ChatMessage] = [] ## 历史

        # 从thread中获取历史消息
        if self._thread is not None:
            history_thread_messages: List[ThreadMessage] = self._thread.messages
            for history_thread_message in history_thread_messages:
                messages.append(TextMessage(content=history_thread_message.content_str(), source=history_thread_message.sender))
        
            ## 加载历史任务树
            if self._thread.metadata.get('root_task', None) is not None:
                self._root_task = self.mapping_json2task(self._thread.metadata['root_task']) # 历史任务树的根任务
                ## 更新并检索首个未完成的任务（即current_task）
                self._current_task = self.get_next_task(current_task=self._root_task) # 继承历史任务树的current_task

        tasks_from_msg: List[str] = await self.parse_tasks_from_message(message=task)
        
        process_result = await self.process_tasks_from_taskList(tasks_from_msg, source="user")
        # print(f"\n\033[31m======================================\n{process_result}\n{'\n'.join([f'- {task}' for task in tasks_from_msg])}\n\033[0m")
        #print(process_result)
        ## 分离出任务之后，更新记录一下任务树
        self._thread.metadata['root_task'] = self.mapping_task2json(self._root_task)
        
        ## 初始化current_task
        if self._current_task == self._root_task:
            self._current_task = self.get_next_task(current_task=self._current_task)


        # if task is None:
        #     pass
        # elif isinstance(task, str):
        #     messages.append(TextMessage(content=task, source="user"))
        # elif isinstance(task, BaseChatMessage):
        #     messages.append(task)
        # else:
        #     if not task:
        #         raise ValueError("Task list cannot be empty.")
        #     messages = []
        #     for msg in task:
        #         if not isinstance(msg, BaseChatMessage):
        #             raise ValueError("All messages in task list must be valid ChatMessage types")
        #         messages.append(msg)

        if self._is_running:
            raise ValueError("The team is already running, it cannot run again until it is stopped.")
        self._is_running = True
        
        # Start the runtime.
        # TODO: The runtime should be started by a managed context.
        self._runtime.start()

        if not self._initialized:
            await self._init(self._runtime) # 注册participants + group chat manager

        # Start a coroutine to stop the runtime and signal the output message queue is complete.
        async def stop_runtime() -> None:
            try:
                await self._runtime.stop_when_idle()
            finally:
                await self._output_message_queue.put(None)

        shutdown_task = asyncio.create_task(stop_runtime())

        prompt_template = load_configs(f'{CONST.PROMPTS_DIR}/groupchat/host.yaml')
        system_message = prompt_template['system']
        tools = self.register_tools()
        host = CustomAgent(
            name="Host",
            model_client=self.model_client,
            tools=tools,
            #tools=[ask_Planner, ask_Coder, ask_Tester],
            system_message=system_message,
            reflect_on_tool_use=False,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )

        try:
            # Run the team by sending the start message to the group chat manager.
            # The group chat manager will start the group chat by relaying the message to the participants
            # and the closure agent.
            ## 这里进到SingleThreadedAgentRuntime并执行groupchat manager的初始化
            # await self._runtime.send_message(
            #     GroupChatStart(messages=messages),
            #     recipient=AgentId(type=self._group_chat_manager_topic_type, key=self._team_id),
            #     cancellation_token=cancellation_token,
            # )
            # Collect the output messages in order.
            output_messages: List[AgentEvent | ChatMessage] = [] ## 专家回复+host回复
            task_round = 1
            while self._current_task != self._root_task: ## 循环直到所有任务都完成
                ## 停止条件判断
                if await self.is_all_tasks_finished():
                    self._is_running = False ## Indicate that the team is no longer running.
                    break
                
                task_map: str = self.get_task_map()
                yield ModelClientStreamingChunkEvent(content=f'\n\n**分层任务系统(任务循环{task_round}): **\n\n{task_map}', source=f"")
                await asyncio.sleep(0.1)
                
                ## 更新current_task状态
                self._current_task.status = "in_progress"
                current_task_content = self._current_task.content
                print(f"\033[31m\n\n============================================================================\nCurrent task: {current_task_content}\033[0m")

                task_map: str = self.get_task_map()
                yield ModelClientStreamingChunkEvent(content=task_map, source="TaskManager")
                
                ## 初始化消息和专家消息列表
                messages.append(TextMessage(content="", source="user")) ## 准备任务prompt
                expert_replies = []

                ## 单任务处理循环
                for discussion_round in range(1, self._max_turns):
                    messages[-1].content = await self.build_expert_advice(current_task_content, expert_replies)

                    if discussion_round == self._max_turns - 1:
                        response = await self.handle_summarization(current_task_content, expert_replies, messages, output_messages)
                        yield expert_replies[-1]
                        response.chat_message = expert_replies[-1]
                        await self.handle_host_response(response, messages, expert_replies, output_messages)
                        break

                    ## Host生成回复
                    # print(f"\n正在咨询专家...")
                    # yield TextMessage(content="正在咨询专家...", source="user")
                    # yield ModelClientStreamingChunkEvent(content="正在咨询专家...", type="ModelClientStreamingChunkEvent")
                    # yield ModelClientStreamingChunkEvent(content=f"\n\n**{host.name}发言(循环{task_round})：**\n\n", source=f'')
                    # response = await host.on_messages(messages, CancellationToken())
                    gen = host.on_messages_stream(messages, CancellationToken())  # 可以是tool call的结果，或者是host的回复
                    async for message in gen:
                        yield message
                        if isinstance(message, Response):
                            response = message
                    
                    reply_host = await self.parse_host_response(response)

                    if isinstance(reply_host, str): ## 无专家建议，直接输出Host的最终回答，格式应为str
                        await self.handle_host_response(response, messages, expert_replies, output_messages)
                        break
                    elif isinstance(reply_host, List): ## 选择专家
                        dict_reply = reply_host[0] ## 选择最后一个专家指示，因为可能由于历史消息干扰同时选择多个专家
                        thoughts = dict_reply.get("thoughts", "")
                        next_speaker_name = dict_reply.get("expert", None)
                        request = dict_reply.get("request", None)
                        # print(f"\n[{next_speaker_name}] speaking:")
                        yield ModelClientStreamingChunkEvent(
                            content=f"选中智能体`{next_speaker_name}`，传递信息：`{request}`", source="")
                        await asyncio.sleep(0.1)
                    
                        ## 让专家说话
                        for i, agentname in enumerate(self._participant_names):
                            if next_speaker_name == agentname:
                                speaker = self._participants[i]  # 根据索引获取对应的参与者
                                break
                            if i == len(self._participant_names) - 1:
                                raise AssertionError(f"Suggested agent: {next_speaker_name} not found")
                        
                        # reply_expert = await speaker.on_messages_stream([TextMessage(content=request, source="user")], CancellationToken())
                        
                        ### NOTE
                        if speaker.name == "Tester":
                            request = output_messages[-1].content

                        gen2 = speaker.on_messages_stream([TextMessage(content=f"{thoughts} {request}", source="user")], CancellationToken())
                        async for message in gen2:
                            yield message
                            if isinstance(message, Response):
                                reply_expert = message

                        expert_content = reply_expert.chat_message.content
                        ## 处理特定agent的回复
                        task_type = ""
                        if speaker.name == "TaskManager":
                            ## TaskManager的回应不直接输出，而是根据回复的参数执行任务操作
                            json_taskManager = str_utils.extract_json_content(reply_expert)
                            
                            task_type = json_taskManager.get("task_type", "insert")
                            tasks = json_taskManager.get("tasks", [])
                            if not tasks: # 如果没有子任务，那就把当前任务内容作为子任务
                                tasks = [request]
                            tasks.insert(0, task_type)
                            #print(colored(f"\n`{speaker.name}`:\n" + ', '.join(task for task in tasks), "yellow"))

                            ## 处理任务列表并更新任务树
                            expert_content = await self.update_tasks_from_message(tasks)
                        
                            if task_type == "select":
                                expert_content = "The task tree has been updated successfully. The tasks tree has been shown." # 避免单条消除存在大量独立任务影响LLM判断
                        if speaker.name == "Planner":
                            await self.handle_host_response(reply_expert, messages, expert_replies, output_messages)
                            break

                        ## 将agent回复添加到任务处理消息列表中
                        expert_replies.append(TextMessage(content=f"{speaker.name}'s thoughts: {expert_content}", source=speaker.name))
                        
                        ## 特殊agent完成回复直接结束任务
                        if speaker.name == "TaskManager":
                            break # 跳出循环，结束该轮任务的讨论。因为TaskManager的执行结果不需要反思
                    else:
                        raise ValueError(f"Invalid host response: {reply_host}")
                task_round += 1
            # Yield the final result.
            yield TaskResult(messages=output_messages, stop_reason=self._stop_reason)

        # finally:
        #     # Wait for the shutdown task to finish.
        #     try:
        #         # This will propagate any exceptions raised in the shutdown task.
        #         # We need to ensure we cleanup though.
        #         await shutdown_task
        #     finally:
        #         # Clear the output message queue.
        #         while not self._output_message_queue.empty():
        #             self._output_message_queue.get_nowait()

        #         # Indicate that the team is no longer running.
        #         self._is_running = False
        except Exception as e:
            self._stop_reason = str(e)
            self._is_running = False
            print(f"\033[31m\n\n============\n{self._stop_reason}\n==========\n\033[0m")
            raise e


    async def run_stream_origin(
        self,
        *,
        task: str | ChatMessage | Sequence[ChatMessage] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> AsyncGenerator[AgentEvent | ChatMessage | TaskResult, None]:
        # Create the messages list if the task is a string or a chat message.
        messages: List[ChatMessage] = [] ## 历史+最新

        # 从thread中获取历史消息
        if self._thread is not None:
            history_thread_messages: List[ThreadMessage] = self._thread.messages
            for history_thread_message in history_thread_messages:
                messages.append(TextMessage(content=history_thread_message.content_str(), source=history_thread_message.sender))
        
            ## 加载历史任务树
            if self._thread.metadata.get('root_task', None) is not None:
                self.root_task = self.mapping_json2task(self._thread.metadata['root_task']) # 历史任务树的根任务
                ## 更新并检索首个未完成的任务（即current_task）
                self.current_task = self.get_next_task(current_task=self._root_task) # 继承历史任务树的current_task

        tasks_from_msg: List[str] = self.parse_tasks_from_message(message=task)
        process_result = self.process_tasks_from_taskList(tasks_from_msg, source="user")
        ## 分离出任务之后，更新记录一下任务树
        if self._thread is not None:
            self._thread.metadata['root_task'] = self.mapping_task2json(self._root_task)
        
        ## 初始化current_task
        if self._current_task == self._root_task:
            self._current_task = self.get_next_task(current_task=self._current_task)


        if task is None:
            pass
        elif isinstance(task, str):
            messages.append(TextMessage(content=task, source="user"))
        elif isinstance(task, BaseChatMessage):
            messages.append(task)
        else:
            if not task:
                raise ValueError("Task list cannot be empty.")
            messages = []
            for msg in task:
                if not isinstance(msg, BaseChatMessage):
                    raise ValueError("All messages in task list must be valid ChatMessage types")
                messages.append(msg)

        if self._is_running:
            raise ValueError("The team is already running, it cannot run again until it is stopped.")
        self._is_running = True
        
        yield messages[-1]

        # Start the runtime.
        # TODO: The runtime should be started by a managed context.
        self._runtime.start()

        if not self._initialized:
            await self._init(self._runtime) # 注册participants + group chat manager

        # Start a coroutine to stop the runtime and signal the output message queue is complete.
        async def stop_runtime() -> None:
            try:
                await self._runtime.stop_when_idle()
            finally:
                await self._output_message_queue.put(None)

        shutdown_task = asyncio.create_task(stop_runtime())

        try:
            # Run the team by sending the start message to the group chat manager.
            # The group chat manager will start the group chat by relaying the message to the participants
            # and the closure agent.
            ## 这里进到SingleThreadedAgentRuntime并执行groupchat manager的初始化
            await self._runtime.send_message(
                GroupChatStart(messages=messages),
                recipient=AgentId(type=self._group_chat_manager_topic_type, key=self._team_id),
                cancellation_token=cancellation_token,
            )
            # Collect the output messages in order.
            output_messages: List[AgentEvent | ChatMessage] = [] ## 最新+往后
            # Yield the messsages until the queue is empty.
            while True:
                message_future = asyncio.ensure_future(self._output_message_queue.get())
                if cancellation_token is not None:
                    cancellation_token.link_future(message_future)
                # Wait for the next message, this will raise an exception if the task is cancelled.
                message = await message_future ## 首个task直接传进来，群聊的消息都是chunk

                if message is None:
                    break
                if message == messages[-1]:
                    pass
                else:
                    yield message
                if isinstance(message, ModelClientStreamingChunkEvent):
                    # Skip the model client streaming chunk events.
                    continue
                output_messages.append(message)

                # 使用thread储存完整的文本消息，以后可能有多模态消息
                if self._thread is not None:
                    self._thread_mgr.create_message(
                        thread=self._thread,
                        role = "assistant" if (message.source != "user" or message.source != "system") else message.source,
                        content=[Content(type="text", text=Text(value=message.content,annotations=[]))],
                        sender=message.source,
                        metadata={},
                    )

            # Yield the final result.
            yield TaskResult(messages=output_messages, stop_reason=self._stop_reason)

        finally:
            # Wait for the shutdown task to finish.
            try:
                # This will propagate any exceptions raised in the shutdown task.
                # We need to ensure we cleanup though.
                await shutdown_task
            finally:
                # Clear the output message queue.
                while not self._output_message_queue.empty():
                    self._output_message_queue.get_nowait()

                # Indicate that the team is no longer running.
                self._is_running = False




    def get_expert(self, expert_name: str) -> CustomAgent:
        '''
        根据专家名称获取专家对象
        '''
        for i, agentname in enumerate(self._participant_names):
            if expert_name == agentname:
                speaker = self._participants[i]  # 根据索引获取对应的参与者
                return speaker
            if i == len(self._participant_names) - 1:
                raise AssertionError(f"Suggested agent: {expert_name} not found")

    def create_task(self, task_content: str, source: str, parent_task: Task = None) -> Task:
        '''
        创建任务，作为parent的子任务添加到子任务列表的末尾
        '''
        task = Task(content=task_content, source=source, parent_task=parent_task)
        return task
    
    def add_task(self, task_list: List[str], source: str) -> None:
        '''
        根据一串任务字符串创建任务
        '''
        for content in task_list:
            ## 逐个创建任务，并作为子任务挂靠在当前任务上
            itask = self.create_task(content, source)
            self._current_task.add_subtask(itask) # 主任务与子任务相互交叉绑定
    
    def insert_task(self, task_list: List[str], base_task: Task = None) -> None:
        '''
        1. 使用str创建新任务并插入到base_task之前(同一层级), base_task默认是current_task
        2. 更新current_task为新任务
        '''
        ## insert tasks before base_task. default is current_task
        if base_task is None:
            base_task = self.current_task

        base_task_list = base_task.parent_task.sub_tasks
        index = base_task_list.index(base_task) # 标记参考位置

        for i, content in enumerate(task_list):
            ## 逐个创建任务，并作为子任务挂靠在base_task之前
            itask = self.create_task(content, source="", parent_task=base_task.parent_task)
            base_task_list.insert(index, itask)
            index += 1
            if i == 0: # 第一个任务，更新current_task为新任务
                self._current_task = itask
    
    def delete_task(self, task_id: str = "") -> None:
        '''
        1. 设置current_task(焦点任务)状态为已完成
        2. 更新current_task为焦点任务的下一个任务
        3. 删除焦点任务 TODO:现在只能删除当前任务
        '''

        parent_task = self._current_task.parent_task
        index = parent_task.sub_tasks.index(self._current_task)
        self._current_task.set_completed(solution="deleted") # 这是目标任务
        self._current_task = self.get_next_task(current_task=self._current_task) # 跳转到目标任务的下一个任务
        parent_task.sub_tasks.pop(index) # 删除当前任务
    
    def update_task(self, task: Task, new_content: str) -> None:
        '''
        更新任务内容
        '''
        task.update_content(new_content)

    def get_task_map(self, tasks: List[Task] = [], level=0, index="") -> str:
        '''
        递归调用，输出带颜色的任务树结构(str) -- ANSI 转义序列
        '''
        # 颜色代码定义
        COLORS = {
            'TASK_ID': '\033[94m',        # 任务ID：蓝色
            'CURRENT_MARKER': '\033[91m',  # 当前任务标记：红色
            'IN_PROGRESS': '\033[93m',    # 进行中：黄色
            'COMPLETED': '\033[92m',      # 已完成状态：绿色
            'QUEUED': '\033[96m',         # 排队中状态：青色
            'CONTENT_DIM': '\033[2m',     # 淡化文本
            'RESET': '\033[0m'            # 重置颜色
        }
        COLORS = {
            'TASK_ID': '',        # 任务ID：蓝色
            'CURRENT_MARKER': '',  # 当前任务标记：红色
            'IN_PROGRESS': '',    # 进行中：黄色
            'COMPLETED': '',      # 已完成状态：绿色
            'QUEUED': '',         # 排队中状态：青色
            'CONTENT_DIM': '',     # 淡化文本
            'RESET': ''            # 重置颜色
        }

        # 状态美化映射
        STATUS_ICONS = {
            'in_progress': '● 进行中',
            'completed': '✓ 已完成',
            'queued': '○ 排队中'
        }

        if level == 0 and tasks == []:
            tasks = self._root_task.sub_tasks  # 默认从第一层任务开始
            
        output = ""
        for i, task in enumerate(tasks):
            index_anchor = f"{index}{i+1}."
            index_sub = f"{'  '*level}{index}{i+1}."
            
            # 格式化状态标签
            status_color = COLORS.get(task.status.upper(), COLORS['RESET'])
            status_label = STATUS_ICONS.get(task.status, task.status)
            
            # 构建任务行
            task_line = (
                f"{COLORS['TASK_ID']}{index_anchor}{COLORS['RESET']} "
            )
            
            # 添加当前任务标记（如果是当前任务）
            # if task == self._current_task:
            #     task_line += (
            #         f"{COLORS['CURRENT_MARKER']}[当前任务]{COLORS['RESET']} "
            #     )
            
            # 根据任务状态决定是否淡化内容
            content_color = COLORS['CONTENT_DIM'] if task.status in ['completed', 'queued'] else ''
            content_reset = COLORS['RESET'] if task.status in ['completed', 'queued'] else ''
            
            # 添加任务内容和状态
            task_line += (
                f"{content_color}{task.content}{content_reset}  "
                f"{status_color}{status_label}{COLORS['RESET']}"
            )
            
            # 如果是当前任务，添加箭头标记
            if task == self._current_task:
                task_line += " \u2190"
                
            output += f"\n{task_line}\n"
            
            # 递归处理子任务
            output += self.get_task_map(task.sub_tasks, level + 1, index_sub)
        
        return output
    
    # def get_task_map(self, tasks: List[Task] = [], level=0, index="") -> str:
    #     '''
    #     递归调用，输出带颜色的任务树结构(HTML格式)
    #     '''
    #     if level == 0 and tasks == []:
    #         tasks = self._root_task.sub_tasks  # 默认从第一层任务开始
            
    #     output = ""
    #     for i, task in enumerate(tasks):
    #         index_anchor = f"{index}{i+1}."
    #         index_sub = f"{'  '*level}{index}{i+1}."
            
    #         # 格式化状态标签
    #         status_class = {
    #             'in_progress': 'in-progress',
    #             'completed': 'completed',
    #             'queued': 'queued'
    #         }.get(task.status, '')
            
    #         status_icon = {
    #             'in_progress': '● 进行中',
    #             'completed': '✓ 已完成',
    #             'queued': '○ 排队中'
    #         }.get(task.status, task.status)
            
    #         # 构建任务行
    #         task_line = f'<div><span class="task-id">{index_anchor}</span> '
            
    #         # 添加当前任务标记（如果是当前任务）
    #         if task == self._current_task:
    #             task_line += f'<span class="current-marker">[当前任务]</span> '
            
    #         # 根据任务状态决定是否淡化内容
    #         content_class = 'dim-text' if task.status in ['completed', 'queued'] else ''
    #         content_class_html = f' class="{content_class}"' if content_class else ''
            
    #         # 添加任务内容和状态
    #         task_line += (
    #             f'<span{content_class_html}>{task.content}</span>  '
    #             f'<span class="{status_class}">{status_icon}</span>'
    #         )
            
    #         # 如果是当前任务，添加箭头标记
    #         if task == self._current_task:
    #             task_line += " ←"
                
    #         task_line += '</div>'
    #         output += task_line
            
    #         # 递归处理子任务
    #         if task.sub_tasks:
    #             output += f'<div class="subtask">'
    #             output += self.get_task_map(task.sub_tasks, level + 1, index_sub)
    #             output += '</div>'
        
    #     return self.generate_task_tree_html(output)

    # # 示例输出包装函数，生成完整HTML页面
    # def generate_task_tree_html(self, task_tree_html):
    #     return f"""
    #     <div class="task-tree">
    #         {task_tree_html}
    #     </div>
        
    #     <style>
    #     .task-tree {{
    #         font-family: monospace;
    #         line-height: 1.5;
    #     }}
    #     .task-id {{
    #         color: #3498db; /* 蓝色 */
    #         font-weight: bold;
    #     }}
    #     .current-marker {{
    #         color: #e74c3c; /* 红色 */
    #         font-weight: bold;
    #     }}
    #     .in-progress {{
    #         color: #f39c12; /* 黄色 */
    #     }}
    #     .completed {{
    #         color: #2ecc71; /* 绿色 */
    #     }}
    #     .queued {{
    #         color: #3498db; /* 青色 */
    #     }}
    #     .dim-text {{
    #         opacity: 0.6; /* 淡化文本 */
    #     }}
    #     .subtask {{
    #         margin-left: 2em;
    #     }}
    #     </style>
    #     """
    
    def get_next_task(self, current_task: Task = None) -> Task:
        current_task = current_task if current_task is not None else self.current_task
        next_task = current_task # 从当前任务开始检索
        
        if next_task.status == "paused":
            return next_task # 如果当前任务被暂停，则返回当前任务

        while True:
            ## 如果当前任务完成了，向上检索父任务状态
            if next_task.status == "completed":
                next_task = next_task.parent_task
            else: # 对于没有完成的任务，向下检索子任务队列，如果没有子任务未完成则返回自己
                sub_tasks = next_task.sub_tasks
                if sub_tasks: # 当前任务有子任务
                    isFind = False # 是否找到未完成的子任务
                    for sub_task in sub_tasks:
                        if sub_task.status != "completed":
                            next_task = sub_task
                            isFind = True
                            break
                    if isFind: # 如果找到了未完成的子任务，在下一轮判断中检查该子任务状态
                        pass
                    else: # 如果没找到未完成的子任务，标记当前任务的状态为已完成，进入下一轮判断
                        if next_task == self._root_task: # 如果根任务的子任务都执行完毕，意味着任务树执行完毕，返回自己
                            return next_task
                        else: # 对于普通任务，直接设置其状态为完成。这意味着节点任务不执行
                            next_task.status = "completed"
                else: # 当前任务没有子任务，返回自己
                    return next_task
    
    def mapping_task2json(self, task: Task) -> Dict:
        '''
        将任务对象映射为json格式
        '''
        task_dict = {
            "id": task.id,
            "metadata": task.metadata,
            "created_at": task.created_at,
            "content": task.content,
            "source": task.source,
            "status": task.status,
            "parent_task": task.parent_task.id if task.parent_task is not None else None,
            "sub_tasks": [self.mapping_task2json(sub_task) for sub_task in task.sub_tasks],
            "task_type": task.task_type,
        }
        return task_dict

    def mapping_json2task(self, task_dict: Dict) -> Task:
        '''
        将json格式的任务对象映射为Task对象
        '''
        def mapping_json2subtask(task_dict: Dict) -> Task:
            parent_task_id = task_dict["parent_task"]
            task = Task(
                id=task_dict["id"],
                metadata=task_dict["metadata"],
                created_at=task_dict["created_at"],
                content=task_dict["content"],
                source=task_dict["source"],
                status=task_dict["status"],
                parent_task=None,  # 暂时设置为None，后续再设置
                sub_tasks=[mapping_json2subtask(sub_task) for sub_task in task_dict["sub_tasks"]],
                task_type=task_dict["task_type"],
            )
            task.parent_task_id = parent_task_id  # 存储parent_task的ID
            return task
        
        root_task = mapping_json2subtask(task_dict)

        # 创建一个任务ID到任务对象的映射
        task_map = {}
        def build_task_map(task: Task):
            task_map[task.id] = task
            for sub_task in task.sub_tasks:
                build_task_map(sub_task)
        build_task_map(root_task)

        # 设置parent_task
        def set_parent_task(task: Task):
            if task.parent_task_id is not None:
                task.parent_task = task_map.get(task.parent_task_id)
            for sub_task in task.sub_tasks:
                set_parent_task(sub_task)
        set_parent_task(root_task)

        return root_task
    
    async def is_termination_condition(self) -> bool:
        if self._current_task.status == "paused":
            return True
        return False
        #return all(task.is_finished() for task in self.tasks)
        # if self._current_task == self._root_task: # 到达任务树顶点，返回True
        #     ## 将任务树存进thread.metadata
        #     self.thread.metadata['root_task'] = await self.mapping_task2json(self._root_task) ## TODO：如何考虑用户是否需要保存历史任务树？
        #     return True
        # else:
        #     return False
    
    async def parse_tasks_from_message(self, message: Optional[Union[TextMessage, List[str]]]) -> List[str] | None:
        """
        从message或者任务清单（字符串）中提取任务列表。
        只有来自Host和Human的message会分解出任务，其他agents不可以。
        如果message类型是List[str]，直接用它创建任务
        """

        output = []
        if isinstance(message, (TextMessage, ToolCallSummaryMessage)):
            if message.source == "user": ## 如果来自人类，用agent解析任务类型，覆盖任务列表
                output.append("insert")
                
                value = message.content

                tasks = str_utils.extract_items_from_text(value) ## 按序号等分割符提取可能的任务列表

                ## 假如有任务清单则添加，假如没有则将原始文本作为任务插入任务树
                if tasks: 
                    output.extend(tasks)
                else:
                    output.append(value)
            if message.source == "Parser":
                output.append("add")
                value = message.content
                try:
                    tasks = json.loads(value)
                    #tasks = str_utils.extract_items_from_text(value) ## 按序号等分割符提取可能的任务列表
                except:
                    tasks = []

                ## 假如有任务清单则添加，假如没有则将原始文本作为任务插入任务树
                if tasks: 
                    output.extend(tasks)
                else:
                    output = None
            else: # if message from a general agent, do not add tasks
                return None
        elif isinstance(message, str): ## 首个人类任务
            tasks = str_utils.extract_items_from_text(message) ## 按序号等分割符提取可能的任务列表
            output.extend(tasks)
        else: # messages类型是List[str]，直接用它创建任务。 -- 主要是来自TaskManager的任务创建
            output = message
        
        return output
    
    async def process_tasks_from_taskList(self, tasks: List[str], task_type: str="", source: str="") -> str:
        '''
        处理任务，增删改查
        tasks是任务列表(str)，包含任务类型和任务内容。 = [task_type, task1, task2, ...]
        空tasks返回""
        '''
        
        tasks_tmp = tasks.copy()
        output = ""
        if tasks_tmp:
            if task_type == "" and any(element in tasks_tmp[0] for element in ["add", "insert", "delete", "update", "select"]): # 任务类型为空，则从任务列表中提取
                task_type = tasks_tmp.pop(0) # get the task category
            else:
                task_type = "insert" # 默认为插入任务，优先执行

            if self.current_task == self._root_task or "add" in task_type: # 新建任务树，或拆分任务为子任务
                for task in tasks_tmp:
                    self.create_task(task, source=source, parent_task=self.current_task)
                output = f"{len(tasks_tmp)} Tasks created as sub-tasks of the current task."
            elif "insert" in task_type: # 在当前任务前面插入新任务
                self.insert_task(tasks_tmp)
                output = f"{len(tasks_tmp)} Tasks inserted."
            elif "delete" in task_type: # 删除任务（连带其子任务分支）
                try:
                    self.delete_task() # 删除内容为“删除任务”的任务
                    self.delete_task() # 删除目标任务
                except:
                    pass
                output = f"Current Tasks deleted."
            elif "update" in task_type: # 更新当前任务
                self.delete_task() # 删除内容为“更新任务”的任务
                self._current_task.content = tasks_tmp[0] # 更新目标任务内容
                output = f"Current Task updated."
            elif "select" in task_type: # 显示任务列表
                output = f"The task tree is:\n{self.get_task_map()}"
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
        return output
    
    async def update_tasks_from_message(self, message: Optional[Union[TextMessage, List[str]]]) -> str:
        output = ""

        ## 提取任务列表，若有则创建任务，并挂靠到当前任务上作为其子任务交叉绑定
        tasks_from_msg = await self.parse_tasks_from_message(message) # List[str] | None

        if tasks_from_msg: # 如果当前任务分离出子任务，那么按任务种类更新任务树
            finish_reason = await self.process_tasks_from_taskList(tasks_from_msg)
            output += finish_reason
        else: # 如果没有分离出子任务，并且没有子任务，那么设置任务状态为完成 -- 通常是其他agent update thread
            try:
                finish_reason = message.content
            except:
                finish_reason = ""
        
        ## 更新任务状态
        # 如果是查看任务树，那么该任务执行完之后，即当前任务就结束了
        if not self._current_task.sub_tasks and self._current_task.status != "paused": # 如果当前任务没有子任务，则直接设置状态为完成
            self._current_task.set_completed(finish_reason)

        ## 顺序执行下一个任务
        self._current_task = self.get_next_task()
        ## 将任务树存进thread.metadata
        self._thread.metadata['root_task'] = self.mapping_task2json(self._root_task)
        
        return output
    
    async def update_thread(self, messages: List[TextMessage]) -> None:
        """
        更新thread的状态
        """
        for message in messages:
            self._thread_mgr.create_message(
                thread=self._thread,
                role = "assistant" if (message.source != "user" or message.source != "system") else message.source,
                content=[Content(type="text", text=Text(value=message.content,annotations=[]))],
                sender=message.source,
                metadata={},
            )
    
    async def parse_host_response(self, response) -> Union[str, List[Dict[str, str]]]:
        try:
            x = response.chat_message.content
            #reply_str=re.findall("expert.:(.*?),.*?request.:(.*?)}",x,re.DOTALL|re.M|re.S)
            reply_str=re.findall("expert.:(.*?)}",x,re.DOTALL|re.M|re.S)
            # return [{
            #     "expert":reply_str[0][0].strip()[1:-1],
            #     "request":reply_str[0][1].strip()[1:-1]
            # }]
            return [{
                "expert": reply_str[0].strip()[1:-1],
                #"request":reply_str[0][1].strip()[1:-1]
            }]
        except:
            return response.chat_message.content
    
    async def summarize(self, messages: List[TextMessage]) -> None:
        """
        总结对话记录
        """
        prompt_template = load_configs(f'{CONST.PROMPTS_DIR}/groupchat/host.yaml')
        system_message_summarizer = prompt_template['summarizer']
        host_summarizer = CustomAgent(
            name="summarizer",
            model_client=self.model_client,
            tools=[],
            system_message=system_message_summarizer,
            reflect_on_tool_use=False,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )
        response = await host_summarizer.on_messages_stream(messages, CancellationToken())

        ## NOTE:await self.handle_host_response(response, messages, expert_replies, output_messages)
        return response
    
    def get_job_info(self) -> str:
        """
        获取任务信息
        """
        output = ""
        global_info = self._root_task.metadata.get("global_info", {})
        job_info = global_info.get("job_info", "")

        if job_info:
            output = "| Task No. | Task Requirement | Key result |\n| --- | --- | --- |\n"
            for index, info in enumerate(job_info):
                output += f"| {index + 1} | {info.get('task_content', '')} | {info.get('conclusion', '')} |\n"
        else:
            output = ""
        return output
    
    def gen_data(self, speaker, messages: List[TextMessage], response: Response) -> dict:
        """
        生成数据集
        """
        data = {}
        data["current_task"] = self.current_task.content
        data["input_msg"] = [m.content for m in messages]
        data["speaker"] = response.chat_message.source
        rag_results = speaker._rag_result if speaker else None
        data["memory_msg"] = rag_results[-1] if rag_results else ""
        data["thoughts"] = response.inner_messages[0].content if response.inner_messages else ""
        try:
            data["tool_call"] = response.inner_messages[1].content[0].name
        except:
            data["tool_call"] = ""
        data["output_msg"] = response.chat_message.content
        data["status"] = self.current_task.status
        data["comment"] = ""
        return data
    
    def process_non_json_file(self, content: Any):
        try:
            # # 匹配数据中的所有键值对
            matched_pairs = self.data

            # 解析匹配到的键值对，提取键名和键值内容
            matched_values_list = []
            current_dict = {}
            for pair in matched_pairs:
                current_dict["current_task"] = pair.get("current_task", "")
                current_dict["input_msg"] = [pair.get("input_msg", "")]
                current_dict["speaker"] = pair.get("speaker", "")
                current_dict["memory_msg"] = pair.get("memory_msg", "")
                current_dict["tool_call"] = pair.get("tool_call", "")
                current_dict["thoughts"] = pair.get("thoughts", "")
                current_dict["output_msg"] = pair.get("output_msg", "")
                current_dict["status"] = pair.get("status", "")
                current_dict["comment"] = ""
            
                matched_values_list.append(current_dict)
                current_dict = {}  # 清空当前字典对象

            # 组装成新的字典对象列表
            new_data_list = []
            for data_dict in matched_values_list:
                new_data_dict = {
                    "current_task": data_dict.get("current_task", ""),
                    "input_msg": [data_dict.get("input_msg", "")],
                    "speaker": data_dict.get("speaker", ""),
                    "memory_msg": data_dict.get("memory_msg", ""),
                    "tool_call": data_dict.get("tool_call", ""),
                    "thoughts": data_dict.get("thoughts", ""),
                    "output_msg": data_dict.get("output_msg", ""),
                    "status": data_dict.get("status", ""),
                    "comment": "",
                }
                new_data_list.append(new_data_dict)

            # 转换为JSON字符串
            new_json_string = json.dumps(new_data_list, ensure_ascii=False, indent=4)

            return new_json_string

        except Exception as e:
            print('Error:', e)
            return f"Error processing non-JSON file: {e}"
            
    def check_dir(self, path: str) -> None:
        """
        检查数据目录是否存在，不存在则创建
        """
        # 判断目录是否存在，不存在则新建
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)  # exist_ok=True 表示若存在则不报错
            #print(f"已创建目录：{path}")
        else:
            #print(f"目录已存在：{path}")
            pass

    def save_runtime_data(self, path: str = None) -> None:
        """
        保存运行数据
        """
        from datetime import datetime
        now = datetime.now()
        dirstamp = now.strftime("%Y%m%d")
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        try:
            content = json.dumps(self.data, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error in save runtime data: {e}")
            content = self.process_non_json_file(self.data)
        
        self.check_dir(f"{CONST.FS_DIR}/runtime_data")
        self.check_dir(f"{CONST.FS_DIR}/runtime_data/{dirstamp}")
        path = path or f"{CONST.FS_DIR}/runtime_data/{dirstamp}/log_{timestamp}.json"
        with open(path, "w") as f:
            f.write(content)
        print(f"\n\033[31m\n\n[System]: Runtime data saved to {path}\n\033[0m")











    # def set_status(self, obj, value, emit=False):
    #     """
    #     Set the status of one object.
    #     for ThreadRun object in stream mode, it will emit corresponding event to the event collector.
    #     """
    #     if obj is None:
    #         return
    #     else:
    #         obj.set_status(value, emit=emit)
    
    # def send_message_to_frontend(self, message: Union[Generator, str], agent: BaseChatAgent, update_tasks: bool = False) -> Union[Generator, str]:
    #     output = message

    #     ## 创建ThreadMessage用于输出到前端
    #     th_msg: ThreadMessage = self.threads_mgr.create_message(
    #             thread=self.thread,
    #             role="assistant",
    #             content=[],
    #             sender=agent.name,
    #             stream=True,
    #         )
    #     yield from th_msg.status_event("created", set_status=True)
    #     yield from th_msg.status_event("in_progress", set_status=True)

    #     ## 判断消息类型 str | Stream (oai_stream)
    #     if isinstance(message, str):
    #         reply2msd=Content(type="text", text=Text(value=message,annotations=[])) # 更新content。若ThreadMessage的content为空，会导致无法发送消息
    #         th_msg.content = [reply2msd]
    #         yield from th_msg.convert_str_to_stream_message_delta(text=message, chunk_size=5, sleep_time=0.05) # 发送消息到前端
    #     elif isinstance(message, Stream):
    #         output = yield from th_msg.convert_oai_stream_to_message_delta(message)
    #     else:
    #         raise ValueError("The message should be a string or a generator of ChatCompletionChunk.")

    #     ## 更新th_msg状态为completed
    #     yield from th_msg.status_event("completed", set_status=True)

    #     ## 更新任务树
    #     if update_tasks:
    #         self.update_tasks_from_message(th_msg)
        
    #     return output ## return str

