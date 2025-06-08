import os, sys
from typing import List, Dict, Tuple, Optional, Any, Literal, Callable
from typing_extensions import Annotated
import json

from besiii.configs import CONST
from besiii.utils import str_utils

speaker_list = [
        {
            "name": "Planner",
            "description": "If you need to create a plan for any task, consult the Planner for guidance on breaking down complex multi-step tasks into actionable steps.",
        },
        {
            "name": "Coder",
            "description": "When you need help with coding in Python, C++, or Shell, or require expertise in the BESIII BOSS software framework and high-energy physics tools like ROOT, ROOFIT, and PYROOT, turn to the Coder.",
        },
        {
            "name": "Tester",
            "description": "Consult the Tester when you have code that needs to be executed and tested for functionality and reliability.",
        },
        {
            "name": "Editor",
            "description": "For assistance with writing and editing texts, particularly academic papers in Chinese and English, reach out to the Editor.",
        },
        {
            "name": "Navigator",
            "description": "If you need to search for academic articles and retrieve information from databases such as arXiv, INSPIRE, or DocDB, the Navigator is your go-to expert; keep in mind this expert only returns information in a fixed format and may require additional input for reliability.",
        },
        {
            "name": "Charm",
            "description": "For comprehensive knowledge about the BESIII project and related information, consult the Charm expert.",
        },
        {
            "name": "TaskManager",
            "description": "Contact the TaskManager for tasks requiring immediate action, such as adding, removing, or updating items, and checking progress of individual tasks or the entire list. Do not contact the TaskManager for tasks that do not have an immediate execution intent, like 'create a travel itinerary'.",
        },
        {
            "name": "WebNavigator",
            "description": "Contact the WebNavigator if you need to search for common information on the web.",
        },
    ]

thoughts = "Talk about the action you plan to take and the reasons behind it."
request_detail = "基于所有已知的细节，详细且具体地描述你需要咨询的内容。"

@str_utils.print_args
def ask_Planner(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
        
    output = {
        "expert": speaker_list[0]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[0]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_Coder(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
        
    output = {
        "expert": speaker_list[1]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[1]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_Tester(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
        
    output = {
        "expert": speaker_list[2]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[2]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_Editor(
    thoughts: Annotated[str, thoughts],
    request: Annotated[str, f"The request for the {speaker_list[3]['name']}. {request_detail}"],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
        
    output = {
        "expert": speaker_list[3]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[3]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_Navigator(
    thoughts: Annotated[str, thoughts],
    #thoughts: Annotated[str, ""],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    #case_of_ideas: Annotated[str, "the summary of the ideas from other perspectives you see in the conversation. OR tell me how many speakers in the conversation and what they are talking about. **tell me If there's any info from teh assistants?**"],
    #case_of_ideas: Annotated[str, "**tell me If there's any info from the assistants, not from user?**"],
    #reflection: Annotated[str, "在这个参数中的返回值中给出你对thoughts和request两个参数的返回值是否符合它们的描述的反思。"],
    #reflection: Annotated[str, ""],
    # thoughts_on_ideas: Annotated[str, "your thoughts on the ideas you see in the conversation"],
    # is_satisfied: Annotated[str, "whether you are satisfied with your request and thoughts"],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
    
    output = {
        "expert": speaker_list[4]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[4]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_Charm(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"

    output = {
        "expert": speaker_list[5]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[5]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_TaskManager(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
    
    output = {
        "expert": speaker_list[6]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[6]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output

@str_utils.print_args
def ask_WebNavigator(
    thoughts: Annotated[str, thoughts],
    #all_details: Annotated[str, "罗列话题中释出的所有关键信息"], # 4o-mini的tool_call不够智能，经验得知加入这个参数能够提升request内容准确性。
    request: Annotated[str, request_detail],
    **kwargs: Annotated[Any, ""], # in case unexpected arguments from LLM
) -> str:
    extra_info = kwargs.get("kwargs", None)
    if extra_info:
        request = f"{request}. Extra infos: {json.dumps(extra_info)}"
    
    output = {
        "expert": speaker_list[7]['name'],
        "request": request,
        "thoughts": thoughts + f"\nConsulting '{speaker_list[6]['name']}' for assistance.",
    }
    output = json.dumps(output, ensure_ascii=False, indent=4)
    
    return output