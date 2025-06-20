import os, sys
from pathlib import Path
from hepai import HepAI, Stream, HRModel
from drsai import AssistantAgent, HepAIChatCompletionClient
import asyncio
from typing import List, Dict, Tuple, Optional, Any, Literal, Callable
from typing_extensions import Annotated
import json, re, uuid

from besiii.utils import Logger, str_utils

logger = Logger.get_logger("reply_functions_workerv2.py")
worker_name = "hepai/code-worker-v2-mapping"  # The name of the worker to connect to
# base_url = "https://aiapi.ihep.ac.cn/apiv2"  # controller's address
base_url = "http://beslogin005.ihep.ac.cn:42899/apiv2"  # Internal controller's address
api_key = os.getenv("HEPAI_API_KEY")  # api key


@str_utils.print_args
def call_algorithm_mapping(
    json_content: Annotated[Dict[str, Any], "JSON内容，包含算法名称和参数"],
    json_file_path: Annotated[Optional[str], "保存JSON文件名，默认为None，则使用随机名称"] = None,
) -> str:
    """The tool to call algorithm mapping function from a JSON file.
    PS: 分析算法程序（algorithm）是BESIII实验基于C++语言和Gaudi框架编写的，利用多探测器信息以得到鉴别粒子的物理量，同时组合末态粒子以得到中间态粒子的程序包。"""
    
    # Check if the json_content is valid
    json_code = json_content
    # try: 
    #     json_code = json.loads(json_content)
    # except:
    #     json_code = re.findall(r'```json\n(.*?)\n```', json_content, re.DOTALL)[0]
    #     logger.warning(f"Invalid JSON content, trying to extract from markdown: {json_code}")
    logger.info(f"json_code: {json_code}")

    # Check output name
    if json_file_path is None:
        json_file_path = f"./runs/algorithm_mapping_{uuid.uuid4().hex}.json"
    if not json_file_path.endswith(".json"):
        json_file_path += ".json"
    if not json_file_path.startswith("./runs/"):
        json_file_path = f"./runs/{json_file_path}"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output_name = uuid.uuid4().hex
    output = model.write_code(content=json.dumps(json_content), file_path=json_file_path)
    output = model.interface(
        messages='{"role": "user", "content": "请将JSON内容转换为BESIII实验的算法映射代码"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_algorithm_mapping",
            "args": {
                "json_file_path": json_file_path,
                "template_path": "besiii/FixedAlg",
                "output_name": output_name,
                "output_path": "./runs"
            }
        }
    )

    return output


@str_utils.print_args
def call_joboption_mapping(
    json_content: Annotated[Dict[str, Any], "JSON内容，包含作业控制脚本的参数"],
    json_file_path: Annotated[Optional[str], "保存JSON文件名，默认为None，则使用随机名称"] = None,
) -> str:
    """The tool to call joboption mapping function from a JSON file.
    PS: BOSS作业控制脚本（joboption）是利用BESIII实验离线软件框架进行数据分析的参数设置文件，用户将需求按格式写入这些脚本，再利用BOSS程序运行，可以产生对应的探测器模拟信号，track(径迹)或cluster(光子簇团)级别的物理信息，以及用户联合多探测器信息鉴别得到的粒子以及他们组成的中间态粒子的物理信息。同时，还利用BESIII实验离线软件框架进行长作业提交的设置文件，可以提交data，inclusive MC的多作业生成和提交。"""
    
    # Check if the json_content is valid
    json_code = json_content
    # try: 
    #     json_code = json.loads(json_content)
    # except:
    #     json_code = re.findall(r'```json\n(.*?)\n```', json_content, re.DOTALL)[0]
    #     logger.warning(f"Invalid JSON content, trying to extract from markdown: {json_code}")
    logger.info(f"json_code: {json_code}")

    # Check output name
    if json_file_path is None:
        json_file_path = f"./runs/joboption_mapping_{uuid.uuid4().hex}.json"
    if not json_file_path.endswith(".json"):
        json_file_path += ".json"
    if not json_file_path.startswith("./runs/"):
        json_file_path = f"./runs/{json_file_path}"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output_name = uuid.uuid4().hex
    output = model.write_code(content=json.dumps(json_content), file_path=json_file_path)
    output = model.interface(
        messages='{"role": "user", "content": "请将JSON内容转换为BESIII实验的作业控制脚本代码"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_joboption_mapping",
            "args": {
                "json_file_path": json_file_path,
                "template_path": "besiii/FixedJobOption",
                "output_name": output_name,
                "output_path": "./runs"
            }
        }
    )

    return output


@str_utils.print_args
def call_drawing_mapping(
    json_content: Annotated[Dict[str, Any], "JSON内容，包含画图类型和参数"],
    json_file_path: Annotated[Optional[str], "保存JSON文件名，默认为None，则使用随机名称"] = None,
) -> str:
    """The tool to call drawing mapping function from a JSON file.
    PS: CERN ROOT画图脚本（drawing）是基于C++语言和CERN ROOT语言编写的画图程序，可以读取ROOT类型文件中的变量，将其绘制在画布上保存成图片返回。目前支持"TH1", "TH2", "TH3", "Pull"四种画图类型，分别对应一维直方图，二维直方图，三维直方图，和Pull分布图。"""
    
    # Check if the json_content is valid
    json_code = json_content
    # try: 
    #     json_code = json.loads(json_content)
    # except:
    #     json_code = re.findall(r'```json\n(.*?)\n```', json_content, re.DOTALL)[0]
    #     logger.warning(f"Invalid JSON content, trying to extract from markdown: {json_code}")
    logger.info(f"json_code: {json_code}")

    # Check output name
    if json_file_path is None:
        json_file_path = f"./runs/drawing_mapping_{uuid.uuid4().hex}.json"
    if not json_file_path.endswith(".json"):
        json_file_path += ".json"
    if not json_file_path.startswith("./runs/"):
        json_file_path = f"./runs/{json_file_path}"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output_name = uuid.uuid4().hex
    output = model.write_code(content=json.dumps(json_content), file_path=json_file_path)
    output = model.interface(
        messages='{"role": "user", "content": "请将JSON内容转换为CERN ROOT画图脚本代码"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_drawing_mapping",
            "args": {
                "json_file_path": json_file_path,
                "template_path": "besiii/FixedDrawing",
                "output_name": output_name,
                "output_path": "./runs"
            }
        }
    )

    return output


@str_utils.print_args
def call_optimizer_fom_mapping(
    json_content: Annotated[Dict[str, Any], "JSON内容，包含Fom算法所需内容和参数"],
    json_file_path: Annotated[Optional[str], "保存JSON文件名，默认为None，则使用随机名称"] = None,
) -> str:
    """The tool to call FoM mapping function from a JSON file.
    PS: FoM脚本是基于C++语言和CERN ROOT语言编写的，用于计算物理量的Figure of Merit（FoM），通常用于评估实验数据的信噪比，并给出最佳优化条件。"""
    
    # Check if the json_content is valid
    json_code = json_content
    # try: 
    #     json_code = json.loads(json_content)
    # except:
    #     json_code = re.findall(r'```json\n(.*?)\n```', json_content, re.DOTALL)[0]
    #     logger.warning(f"Invalid JSON content, trying to extract from markdown: {json_code}")
    logger.info(f"json_code: {json_code}")

    # Check output name
    if json_file_path is None:
        json_file_path = f"./runs/optimizer_fom_mapping_{uuid.uuid4().hex}.json"
    if not json_file_path.endswith(".json"):
        json_file_path += ".json"
    if not json_file_path.startswith("./runs/"):
        json_file_path = f"./runs/{json_file_path}"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output_name = uuid.uuid4().hex
    output = model.write_code(content=json.dumps(json_content), file_path=json_file_path)
    output = model.interface(
        messages='{"role": "user", "content": "请将JSON内容转换为Fom脚本代码"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_optimizer_fom_mapping",
            "args": {
                "json_file_path": json_file_path,
                "template_path": "besiii/FixedOptimizer",
                "output_name": output_name,
                "output_path": "./runs"
            }
        }
    )

    return output


@str_utils.print_args
def call_optimizer_tmva_mapping(
    json_content: Annotated[Dict[str, Any], "JSON内容，包含Fom算法所需内容和参数"],
    json_file_path: Annotated[Optional[str], "保存JSON文件名，默认为None，则使用随机名称"] = None,
) -> str:
    """The tool to call TMVA mapping function from a JSON file.
    PS: TMVA是ROOT框架中的多元变量分析工具包，用于数据分类与回归分析，支持多种机器学习算法（如BDT、神经网络），广泛应用于高能物理实验数据处理。"""
    
    # Check if the json_content is valid
    json_code = json_content
    # try: 
    #     json_code = json.loads(json_content)
    # except:
    #     json_code = re.findall(r'```json\n(.*?)\n```', json_content, re.DOTALL)[0]
    #     logger.warning(f"Invalid JSON content, trying to extract from markdown: {json_code}")
    logger.info(f"json_code: {json_code}")

    # Check output name
    if json_file_path is None:
        json_file_path = f"./runs/optimizer_tmva_mapping_{uuid.uuid4().hex}.json"
    if not json_file_path.endswith(".json"):
        json_file_path += ".json"
    if not json_file_path.startswith("./runs/"):
        json_file_path = f"./runs/{json_file_path}"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output_name = uuid.uuid4().hex
    output = model.write_code(content=json.dumps(json_content), file_path=json_file_path)
    output = model.interface(
        messages='{"role": "user", "content": "请将JSON内容转换为TMVA脚本代码"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_optimizer_tmva_mapping",
            "args": {
                "json_file_path": json_file_path,
                "template_path": "besiii/FixedOptimizer",
                "output_name": output_name,
                "output_path": "./runs"
            }
        }
    )

    return output


@str_utils.print_args
def call_getting_branch_name(
    root_path: Annotated[str, "ROOT文件路径"],
) -> str:
    """The tool to get branch name of a specific root file according to its path."""

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output = model.interface(
        messages='{"role": "user", "content": "请获取指定ROOT文件的分支名称"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_getting_branch_name",
            "args": {
                "root_path": root_path,
            }
        }
    )

    return output


@str_utils.print_args
def call_boss_jobs_query(
    job_ids: Annotated[List[int], "List of job IDs to query"],
    query_opt: Annotated[Optional[str], "查询选项，默认为None，表示查询当前用户的作业IDs"] = "-u",
) -> str:
    """The tool to query BOSS jobs information by job IDs.
    PS: BOSS作业查询（query）是BESIII实验基于HTCondor的作业管理系统Hep_Condor，用户可以通过该工具查询作业的状态、结果等信息。"""

    if query_opt is None:
        query_opt = "-u"

    # Connect to the Worker-v2
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output = model.interface(
        messages='{"role": "user", "content": "请查询BOSS作业的相关信息"}',
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "call_boss_jobs_query",
            "args": {
                "job_ids": job_ids,
                "query_opt": query_opt,
            }
        }
    )

    # Convert output to JSON
    try:
        output = json.loads(output)
    except json.JSONDecodeError:
        return f"Error decoding JSON from output: {output}"

    # Markdown table format for job information
    rst = "# Job Information\n\n"
    rst += "| Job ID | Status | Start Time | Run Time | Memory Usage | Command |\n"
    rst += "|--------|--------|------------|----------|--------------|---------|\n"
    for job in output:
        job_id = job.get("job_id", "Unknown")
        status = job.get("status", "Unknown")
        start_time = job.get("start_time", "Unknown")
        run_time = job.get("run_time", "Unknown")
        memory_usage = job.get("memory_usage", "Unknown")
        command = job.get("command", "Unknown")
        
        rst += f"| {job_id} | {status} | {start_time} | {run_time} | {memory_usage} | {command} |\n"
    if not output:
        rst += "| No jobs found | | | | |\n"
    rst += "\n"

    return rst

