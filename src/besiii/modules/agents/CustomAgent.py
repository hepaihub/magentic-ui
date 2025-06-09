from typing import AsyncGenerator, List, Sequence, Dict, Any, Callable, Awaitable, Union, Optional, Coroutine
import asyncio
import logging
import inspect

from pydantic import BaseModel
from autogen_core.tools import (
    BaseTool, 
    FunctionTool, 
    StaticWorkbench, 
    Workbench, 
    ToolResult, 
    TextResultContent, 
    ToolSchema)

from autogen_core import CancellationToken, FunctionCall
from autogen_core.memory import Memory
from autogen_core.model_context import ChatCompletionContext
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

from drsai import AssistantAgent
from autogen_core import EVENT_LOGGER_NAME
# from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import Handoff as HandoffBase
from autogen_agentchat.base import Response
from autogen_agentchat.messages import (
    AgentEvent,
    ChatMessage,
    BaseAgentEvent,
    BaseChatMessage,
    ThoughtEvent,
    HandoffMessage,
    MemoryQueryEvent,
    ModelClientStreamingChunkEvent,
    TextMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    ToolCallSummaryMessage,
)

from drsai.modules.managers.base_thread import Thread
from drsai.modules.managers.threads_manager import ThreadsManager
from drsai.modules.managers.base_thread_message import ThreadMessage, Content, Text

from besiii.utils.tool import timed_method

event_logger = logging.getLogger(EVENT_LOGGER_NAME)

class CustomAgent(AssistantAgent):
    """基于aotogen AssistantAgent的定制Agent"""
    def __init__(
            self, 
            name: str,
            model_client: ChatCompletionClient,
            *,
            tools: List[BaseTool[Any, Any] | Callable[..., Any] | Callable[..., Awaitable[Any]]] | None = None,
            handoffs: List[HandoffBase | str] | None = None,
            model_context: ChatCompletionContext | None = None,
            description: str = "An agent that provides assistance with ability to use tools.",
            system_message: (
                str | None
            ) = "You are a helpful AI assistant. Solve tasks using your tools. Reply with TERMINATE when the task has been completed.",
            model_client_stream: bool = True,
            reflect_on_tool_use: bool = False,
            tool_call_summary_format: str = "{result}",
            memory: Sequence[Memory] | None = None,
            memory_function: Callable = None,
            reply_function: Callable = None,
            thread: Thread = None,
            thread_mgr: ThreadsManager = None,
            **kwargs,
            ):
        '''
        memory_function: 自定义的memory_function，用于RAG检索等功能，为大模型回复增加最新的知识
        reply_function: 自定义的reply_function，用于自定义对话回复的定制
        '''
        super().__init__(
            name, 
            model_client,
            tools=tools,
            handoffs=handoffs,
            model_context=model_context,
            description=description,
            system_message=system_message,
            model_client_stream=model_client_stream,
            reflect_on_tool_use=reflect_on_tool_use,
            tool_call_summary_format=tool_call_summary_format,
            memory=memory,
            memory_function=memory_function,
            reply_function=reply_function,
            thread=thread,
            thread_mgr=thread_mgr,
            **kwargs
            )
        self._rag_result = []
        
    def __repr__(self):
        return f"CustomAgent(name={self.name})"
    
    async def textmessages2llm_messages(self, textmessages: List[TextMessage]) -> List[LLMMessage]:
        """Convert a list of OAI chat messages to a list of LLM messages."""
        messages = []
        for textmessage in textmessages:
            if textmessage.source == "system":
                messages.append(SystemMessage(content=textmessage.content))
            elif textmessage.source == "user":
                messages.append(UserMessage(content=textmessage.content, source=textmessage.source))
            elif textmessage.source == "function":
                messages.append(FunctionExecutionResultMessage(content=textmessage.content))
            else:
                messages.append(AssistantMessage(content=textmessage.content, source=textmessage.source))
        return messages


    async def _call_llm(
        self,
        model_client: ChatCompletionClient,
        model_client_stream: bool,
        system_messages: List[SystemMessage],
        messages: List[BaseChatMessage],
        model_context: ChatCompletionContext,
        workbench: Workbench,
        handoff_tools: List[BaseTool[Any, Any]],
        agent_name: str,
        cancellation_token: CancellationToken,
        output_content_type: type[BaseModel] | None,
    ) -> AsyncGenerator[Union[CreateResult, ModelClientStreamingChunkEvent], None]:
        """
        Perform a model inference and yield either streaming chunk events or the final CreateResult.
        """
        #all_messages = await model_context.get_messages()
        all_messages = await self.textmessages2llm_messages(messages) ## 使用外部消息生成回复
        
        llm_messages: List[LLMMessage] = self._get_compatible_context(model_client=model_client, messages=system_messages + all_messages)

        # 自定义的memory_function，用于RAG检索等功能，为大模型回复增加最新的知识
        if self._memory_function is not None:
            # llm_messages = await self._call_memory_function(llm_messages)
            memory_messages = await self.llm_messages2oai_messages(llm_messages)
            rag_result: dict = await self._memory_function(memory_messages, **self._user_params)
            llm_messages = await self.oai_messages2llm_messages(rag_result["messages"])  # 将RAG检索结果转换为LLM消息
            if rag_result["retrieve_txt"]:
                self._rag_result.append(rag_result["retrieve_txt"])  # 保存RAG检索结果
            yield ModelClientStreamingChunkEvent(content = "\n**RAG retrieve:**\n", source=agent_name)
            # await asyncio.sleep(0.1)
            yield ModelClientStreamingChunkEvent(content = "\n<think>\n", source=agent_name)
            # await asyncio.sleep(0.1)
            yield ModelClientStreamingChunkEvent(content = rag_result["retrieve_txt"][0], source=agent_name)
            # await asyncio.sleep(0.1)
            yield ModelClientStreamingChunkEvent(content = "\n</think>\n", source=agent_name)

        all_tools = (await workbench.list_tools()) + handoff_tools
        # model_result: Optional[CreateResult] = None
        if self._allow_reply_function:
            # 自定义的reply_function，用于自定义对话回复的定制
            async for chunk in self._call_reply_function(
                llm_messages, 
                model_client = model_client, 
                workbench=workbench,
                handoff_tools=handoff_tools,
                tools = all_tools,
                agent_name=agent_name, 
                cancellation_token=cancellation_token,
                thread = self._thread,
                thread_mgr = self._thread_mgr,
            ):
                # if isinstance(chunk, CreateResult):
                #     model_result = chunk
                yield chunk
        else:
           async for chunk in self.call_llm(
                agent_name = agent_name,
                model_client = model_client,
                llm_messages = llm_messages, 
                tools = all_tools, 
                model_client_stream = model_client_stream,
                cancellation_token = cancellation_token,
                output_content_type = output_content_type,
           ):
               yield chunk


    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        async for message in self.on_messages_stream(messages, cancellation_token):
            if isinstance(message, Response):
                return message
        raise AssertionError("The stream should have returned the final result.")

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """
        Process the incoming messages with the assistant agent and yield events/responses as they happen.
        """

        # Gather all relevant state here
        agent_name = self.name
        model_context = self._model_context
        memory = self._memory
        system_messages = self._system_messages
        workbench = self._workbench
        handoff_tools = self._handoff_tools
        handoffs = self._handoffs
        model_client = self._model_client
        model_client_stream = self._model_client_stream
        reflect_on_tool_use = self._reflect_on_tool_use
        tool_call_summary_format = self._tool_call_summary_format
        output_content_type = self._output_content_type
        format_string = self._output_content_type_format

        # # STEP 1: Add new user/handoff messages to the model context
        # await self._add_messages_to_context(
        #     model_context=model_context,
        #     messages=messages,
        # )

        # STEP 2: Update model context with any relevant memory
        inner_messages: List[BaseAgentEvent | BaseChatMessage] = []
        for event_msg in await self._update_model_context_with_memory(
            memory=memory,
            model_context=model_context,
            agent_name=agent_name,
        ):
            inner_messages.append(event_msg)
            yield event_msg

        # STEP 3: Run the first inference
        model_result = None
        async for inference_output in self._call_llm(
            model_client=model_client,
            model_client_stream=model_client_stream,
            system_messages=system_messages,
            messages=messages,
            model_context=model_context,
            workbench=workbench,
            handoff_tools=handoff_tools,
            agent_name=agent_name,
            cancellation_token=cancellation_token,
            output_content_type=output_content_type,
        ):
            if isinstance(inference_output, CreateResult):
                model_result = inference_output
            else:
                # Streaming chunk event
                yield inference_output

        assert model_result is not None, "No model result was produced."

        # --- NEW: If the model produced a hidden "thought," yield it as an event ---
        if model_result.thought:
            thought_event = ThoughtEvent(content=model_result.thought, source=agent_name)
            yield thought_event
            inner_messages.append(thought_event)

        # Add the assistant message to the model context (including thought if present)
        # await model_context.add_message(
        #     AssistantMessage(
        #         content=model_result.content,
        #         source=agent_name,
        #         thought=getattr(model_result, "thought", None),
        #     )
        # )

        # STEP 4: Process the model output
        async for output_event in self._process_model_result(
            model_result=model_result,
            inner_messages=inner_messages,
            cancellation_token=cancellation_token,
            agent_name=agent_name,
            system_messages=system_messages,
            model_context=model_context,
            workbench=workbench,
            handoff_tools=handoff_tools,
            handoffs=handoffs,
            model_client=model_client,
            model_client_stream=model_client_stream,
            reflect_on_tool_use=reflect_on_tool_use,
            tool_call_summary_format=tool_call_summary_format,
            output_content_type=output_content_type,
            format_string=format_string,
        ):
            yield output_event