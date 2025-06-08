import asyncio
import json
from typing import Any, AsyncGenerator, List, Sequence, Callable, Mapping, Dict, Tuple, Optional

from drsai import DrSaiRoundRobinGroupChat, DrSaiRoundRobinGroupChatManager
from drsai.modules.managers.base_thread import Thread
from drsai.modules.managers.threads_manager import ThreadsManager
from drsai.modules.managers.base_thread_message import ThreadMessage, Content, Text

from besiii.configs.config import load_configs
from besiii.configs import constant as CONST
from besiii.configs.prompts.groupchat.host_action import ask_Planner, ask_Coder, ask_Tester, ask_Editor, ask_Navigator, ask_Charm, ask_TaskManager, ask_WebNavigator

from autogen_agentchat.messages import AgentEvent, BaseChatMessage, ChatMessage, ModelClientStreamingChunkEvent, TextMessage, StopMessage
from autogen_agentchat.base import ChatAgent, TaskResult, TerminationCondition, Response
from autogen_agentchat.teams._group_chat._events import GroupChatStart, GroupChatTermination, GroupChatRequestPublish, GroupChatAgentResponse, GroupChatMessage
from autogen_agentchat.teams._group_chat._chat_agent_container import ChatAgentContainer
from autogen_agentchat.state import RoundRobinManagerState
from autogen_core import DefaultTopicId, MessageContext, event, rpc
from autogen_core import (
    AgentId,
    CancellationToken,
    AgentInstantiationContext,
)


from drsai import AssistantAgent, HepAIChatCompletionClient
import os
model_client = HepAIChatCompletionClient(
        model="openai/gpt-4o",
        api_key="apikey",
        #base_url = "http://192.168.32.148:42601/apiv2"
    )


class CustomGroupChatManager(DrSaiRoundRobinGroupChatManager):
    """A group chat manager that selects the next speaker in a round-robin fashion."""

    def __init__(
        self,
        name: str,
        group_topic_type: str,
        output_topic_type: str,
        participant_topic_types: List[str],
        participant_descriptions: List[str],
        termination_condition: TerminationCondition | None,
        max_turns: int | None = None,
        thread: Thread = None,
        thread_mgr: ThreadsManager = None,
        group_chat = None,
        **kwargs: Any
    ) -> None:
        super().__init__(
            name = name,
            group_topic_type = group_topic_type,
            output_topic_type = output_topic_type,
            participant_topic_types = participant_topic_types,
            participant_descriptions = participant_descriptions,
            termination_condition = termination_condition,
            max_turns = max_turns,
            thread = thread,
            thread_mgr = thread_mgr,
            **kwargs
        )
        self._next_speaker_index = 0
        self._theard: Thread = thread
        self._thread_mgr: ThreadsManager = thread_mgr
        self.groupchat = group_chat

        prompt_template = load_configs(f'{CONST.PROMPTS_DIR}/groupchat/host.yaml')
        system_message = prompt_template['system']
        self.agent = AssistantAgent(
            name="Host",
            model_client=model_client,
            tools=[ask_planner, ask_Coder, ask_Tester, ask_Editor, ask_Navigator, ask_Charm, ask_TaskManager, ask_WebNavigator],
            system_message=system_message,
            reflect_on_tool_use=False,
            model_client_stream=True,  # Enable streaming tokens from the model client.
        )

    @rpc
    async def handle_start(self, message: GroupChatStart, ctx: MessageContext) -> None:
        """Handle the start of a group chat by selecting a speaker to start the conversation."""

        # Check if the conversation has already terminated.
        if self._termination_condition is not None and self._termination_condition.terminated:
            early_stop_message = StopMessage(
                content="The group chat has already terminated.", source="Group chat manager"
            )
            await self.publish_message(
                GroupChatTermination(message=early_stop_message), topic_id=DefaultTopicId(type=self._output_topic_type)
            )
            # Stop the group chat.
            return

        # Validate the group state given the start messages
        await self.validate_group_state(message.messages)

        if message.messages is not None:
            # Log all messages at once
            await self.publish_message(
                GroupChatStart(messages=message.messages), topic_id=DefaultTopicId(type=self._output_topic_type)
            )

            # Relay all messages at once to participants
            await self.publish_message(
                GroupChatStart(messages=message.messages),
                topic_id=DefaultTopicId(type=self._group_topic_type),
                cancellation_token=ctx.cancellation_token,
            )

            # Append all messages to thread
            self._message_thread.extend(message.messages)

            # Check termination condition after processing all messages
            if self._termination_condition is not None:
                stop_message = await self._termination_condition(message.messages)
                if stop_message is not None:
                    await self.publish_message(
                        GroupChatTermination(message=stop_message),
                        topic_id=DefaultTopicId(type=self._output_topic_type),
                    )
                    # Stop the group chat and reset the termination condition.
                    await self._termination_condition.reset()
                    return

        # # Select a speaker to start/continue the conversation
        # speaker_topic_type_future = asyncio.ensure_future(self.select_speaker(self._message_thread))
        # # Link the select speaker future to the cancellation token.
        # ctx.cancellation_token.link_future(speaker_topic_type_future)
        # speaker_topic_type = await speaker_topic_type_future
        # await self.publish_message(
        #     GroupChatRequestPublish(),
        #     topic_id=DefaultTopicId(type=speaker_topic_type),
        #     cancellation_token=ctx.cancellation_token,
        # )

    @event
    async def handle_agent_response(self, message: GroupChatAgentResponse, ctx: MessageContext) -> None:
        # Append the message to the message thread and construct the delta.
        delta: List[AgentEvent | ChatMessage] = []
        if message.agent_response.inner_messages is not None:
            for inner_message in message.agent_response.inner_messages:
                self._message_thread.append(inner_message)
                delta.append(inner_message)
        self._message_thread.append(message.agent_response.chat_message)
        delta.append(message.agent_response.chat_message) ## 被选中agent的回复

        # Check if the conversation should be terminated.
        if self._termination_condition is not None:
            stop_message = await self._termination_condition(delta) ## 跳转到groupchat run_stream的更新thread之前，将新回复添加到messages中
            if stop_message is not None:
                await self.publish_message(
                    GroupChatTermination(message=stop_message), topic_id=DefaultTopicId(type=self._output_topic_type)
                )
                # Stop the group chat and reset the termination conditions and turn count.
                await self._termination_condition.reset()
                self._current_turn = 0
                return
        
        # Increment the turn count.
        self._current_turn += 1
        # Check if the maximum number of turns has been reached.
        if self._max_turns is not None:
            if self._current_turn >= self._max_turns:
                await self.terminate(reason=f"Maximum number of turns {self._max_turns} reached.")
                return
        
        ## check if all tasks are finished
        if self.groupchat.is_all_tasks_finished():
            await self.terminate(reason="All tasks have been finished.")
            return
        
        ## 从任务树中提取本轮需要处理的任务。以及其他消息处理。
        current_task_content = self.groupchat.current_task.content

        # Select a speaker to continue the conversation.
        speaker_topic_type_future = asyncio.ensure_future(self.select_speaker(self._message_thread))
        # Link the select speaker future to the cancellation token.
        ctx.cancellation_token.link_future(speaker_topic_type_future)
        speaker_topic_type = await speaker_topic_type_future # select_speaker返回的agent name
        await self.publish_message(
            GroupChatRequestPublish(),
            topic_id=DefaultTopicId(type=speaker_topic_type),
            cancellation_token=ctx.cancellation_token,
        )
    
    async def terminate(self, reason: str, source: str= "Group chat manager") -> None:
        """Terminate the group chat."""
        stop_message = StopMessage(
            content=reason,
            source=source,
        )
        await self.publish_message(
            GroupChatTermination(message=stop_message), topic_id=DefaultTopicId(type=self._output_topic_type)
        )
        # Stop the group chat and reset the termination conditions and turn count.
        if self._termination_condition is not None:
            await self._termination_condition.reset()
        self._current_turn = 0    
    
    # async def handle_request(self, message: GroupChatRequestPublish, ctx: MessageContext) -> None:
    #     """Handle a content request event by passing the messages in the buffer
    #     to the delegate agent and publish the response."""
    #     # Pass the messages in the buffer to the delegate agent.
    #     response: Response | None = None
    #     async for msg in self._agent.on_messages_stream(self._message_buffer, ctx.cancellation_token):
    #         if isinstance(msg, Response):
    #             # Log the response.
    #             await self.publish_message(
    #                 GroupChatMessage(message=msg.chat_message),
    #                 topic_id=DefaultTopicId(type=self._output_topic_type),
    #             )
    #             response = msg
    #         else:
    #             # Log the message.
    #             await self.publish_message(
    #                 GroupChatMessage(message=msg), topic_id=DefaultTopicId(type=self._output_topic_type)
    #             )
    #     if response is None:
    #         raise ValueError("The agent did not produce a final response. Check the agent's on_messages_stream method.")

    #     # Publish the response to the group chat.
    #     self._message_buffer.clear()
    #     await self.publish_message(
    #         GroupChatAgentResponse(agent_response=response),
    #         topic_id=DefaultTopicId(type=self._parent_topic_type),
    #         cancellation_token=ctx.cancellation_token,
    #     )



    async def validate_group_state(self, messages: List[ChatMessage] | None) -> None:
        pass

    async def reset(self) -> None:
        self._current_turn = 0
        self._message_thread.clear()
        if self._termination_condition is not None:
            await self._termination_condition.reset()
        self._next_speaker_index = 0

    async def save_state(self) -> Mapping[str, Any]:
        state = RoundRobinManagerState(
            message_thread=list(self._message_thread),
            current_turn=self._current_turn,
            next_speaker_index=self._next_speaker_index,
        )
        return state.model_dump()

    async def load_state(self, state: Mapping[str, Any]) -> None:
        round_robin_state = RoundRobinManagerState.model_validate(state)
        self._message_thread = list(round_robin_state.message_thread)
        self._current_turn = round_robin_state.current_turn
        self._next_speaker_index = round_robin_state.next_speaker_index

    async def select_speaker(self, messages: List[AgentEvent | ChatMessage]) -> str:
        """让host选人"""
        response = await self.agent.on_messages(messages, CancellationToken())
        #current_speaker= response.chat_message.content

        try:
            reply_host = json.loads(response.chat_message.content)
            if isinstance(reply_host, Dict):
                next_speaker_name = reply_host.get("expert", None)
                return next_speaker_name
        except:
            raise ValueError("Host did not produce a valid response. Please check host's on_messages method.")
        # self._participant_topic_types
        # self._participant_descriptions
    




# class CustomChatAgentContainer(ChatAgentContainer):
#     async def handle_request(self, message: GroupChatRequestPublish, ctx: MessageContext) -> None:
#         """Handle a content request event by passing the messages in the buffer
#         to the delegate agent and publish the response."""
#         # Pass the messages in the buffer to the delegate agent.
#         response: Response | None = None
#         async for msg in self._agent.on_messages_stream(self._message_buffer, ctx.cancellation_token):
#             if isinstance(msg, Response):
#                 # Log the response.
#                 await self.publish_message(
#                     GroupChatMessage(message=msg.chat_message),
#                     topic_id=DefaultTopicId(type=self._output_topic_type),
#                 )
#                 response = msg
#             else:
#                 # Log the message.
#                 await self.publish_message(
#                     GroupChatMessage(message=msg), topic_id=DefaultTopicId(type=self._output_topic_type)
#                 )
#         if response is None:
#             raise ValueError("The agent did not produce a final response. Check the agent's on_messages_stream method.")

#         # Publish the response to the group chat.
#         self._message_buffer.clear()
#         await self.publish_message(
#             GroupChatAgentResponse(agent_response=response),
#             topic_id=DefaultTopicId(type=self._parent_topic_type),
#             cancellation_token=ctx.cancellation_token,
#         )
