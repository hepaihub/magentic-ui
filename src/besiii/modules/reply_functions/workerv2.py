import os, sys
from pathlib import Path
import hepai
from hepai import HepAI, Stream, HRModel
from drsai import AssistantAgent, HepAIChatCompletionClient
from typing import List, Dict, Union, AsyncGenerator
import json, re, uuid

from besiii.utils import Logger

logger = Logger.get_logger("reply_functions_workerv2.py")
worker_name = "hepai/code-worker-v2-mapping"  # The name of the worker to connect to
# base_url = "https://aiapi.ihep.ac.cn/apiv2"  # controller's address
base_url = "http://beslogin005.ihep.ac.cn:42899/apiv2"  # Internal controller's address
api_key = os.getenv("HEPAI_API_KEY")  # api key


def list_models():
    """
    List all available models in the HepAI API.
    Returns:
        List[Dict]: A list of models with their details.
    """
    client = HepAI(api_key=api_key, base_url=base_url)
    models = client.models.list()
    return models


def list_functions(model_name: str):
    """
    List all remote callable functions of a specific model.
    Args:
        model_name (str): The name of the model to list functions for.
    Returns:
        None: Prints the list of remote callable functions.
    """
    model = HRModel.connect(
        name=model_name,
        api_key=api_key,
        base_url=base_url,
    )
    funcs = model.functions()  # Get all remote callable functions.
    print(f"Remote callable funcs: {funcs}")


def request_demo(messages: str) -> str:
    """
    Request the demo function based on the messages.
    This function is used to test the worker's ability to respond to simple messages.
    Args:
        messages (str): The message containing the request.
    Returns:
        str: The output of the worker demo function.
    """

    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    ## --- simple function
    # output = model.hello_world(messages=messages)
    # output = model.inspect_environment()
    # output = model.inspect_system()
    # output = model.run_command(command="sleep 5")
    # output = model.run_command(command="hep_q -u liaoyp")
    # output = model.list_callable_functions()
    # output = model.print_function_args(function="call_getting_branch_name")

    ## --- string to List[Dict]
    # output = model.get_stream(messages=[{"role": "user", "content": messages}, {"role": "assistant", "content": "Hello, I am a code worker!"}])

    ## --- interface USE function
    output = model.interface(
        messages=[
            {"role": "user", "content": "Please run a command for me."}, 
        ],
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "run_command",
            "args": {
                "command": "echo 'Hello, I am a code worker!'"
            }
        }
    )

    output = model.interface(
        messages=[
            {"role": "user", "content": "Please run a command for me."}, 
        ],
        worker_config={
            "intention_understanding": False,
        },
        function={
            "name": "run_command",
            "args": {
                "command": """cp /afs/ihep.ac.cn/users/l/liaoyp/sharefs/Boss709/cloneTrack/pipiJpsi/morebin1.png .;
                              cp /afs/ihep.ac.cn/users/l/liaoyp/sharefs/Boss709/cloneTrack/pipiJpsi/sigmc_check.pdf .;
                              sleep 2"""
            }
        }
    )

    ## --- interface USE llm [*Still with bugs]
    # msg = """
    # Please run a command for me.
    # I want you to run the shell command: echo 'Hello, I am a code worker!'
    # You can use the `run_command` function to run the command.
    # """
    # output = model.interface(
    #     messages=[
    #         {"role": "user", "content": msg}, 
    #     ],
    #     worker_config={
    #         "intention_understanding": True,
    #         "llm_config": {
    #             "config_list": [
    #                 {
    #                     "model": "openai/gpt-4o",
    #                     "base_url": base_url,
    #                     "api_key": api_key,
    #                 }
    #             ]
    #         },
    #     },
    # )

    ## --- drawing
    # output = model.interface(
    #     messages=messages,
    #     worker_config={
    #         "intention_understanding": False,
    #     },
    #     function={
    #         "name": "call_drawing_mapping",
    #         "args": {
    #             "json_file_path": "besiii/ExampleVarsCard/DrawVarsCard/draw_TH3.json",
    #             "template_path": "besiii/FixedDrawing",
    #             "output_name": "drawing_mapping",
    #             "output_path": "./runs"
    #         }
    #     }
    # )

    ## --- joboption
    # output = model.interface(
    #     messages=messages,
    #     worker_config={
    #         "intention_understanding": False,
    #     },
    #     function={
    #         "name": "call_joboption_mapping",
    #         "args": {
    #             "json_file_path": "besiii/JobVarsCard.json",
    #             "template_path": "besiii/FixedJobOption",
    #             "output_name": "joboption_mapping",
    #             "output_path": "./runs"
    #         }
    #     }
    # ) # data: "{\"success\": true, \"message\": \"Mapping from besiii/JobSubVarsCard.json based on template<besiii/FixedJobSubmit> to ./runs/test_submit with 100 jobs ...\\n{'success': True, 'message': 'Mapping from besiii/JobSubVarsCard.json based on template<besiii/FixedJobSubmit> to ./runs/test_submit ...\\\\nData job submission successfully: 100 job(s) submitted to cluster 20614002.\\\\nInmc job submission successfully: 98 job(s) submitted to cluster 20614003.\\\\nAll job maker scripts executed successfully, output files are in ./runs.', 'job_ids': [{'job_id': '20614002', 'job_num': '100'}, {'job_id': '20614003', 'job_num': '98'}]}\\n\", \"stderr\": \"\", \"changed_files\": []}

    ## --- algorithm
    # output = model.interface(
    #     messages=messages,
    #     worker_config={
    #         "intention_understanding": False,
    #     },
    #     function={
    #         "name": "call_algorithm_mapping",
    #         "args": {
    #             "json_file_path": "besiii/AlgoVarsCard.json",
    #             "template_path": "besiii/FixedAlg",
    #             "output_name": "algorithm_mapping",
    #             "output_path": "./runs"
    #         }
    #     }
    # )

    ## --- write_code
    # content = """
    # {
    #     "MetaData": {
    #         "AlgorithmName": "xxx",
    #         "DecayChain": "psi(2S) -> pi+ pi- [J/psi -> mu+ mu-]",
    #         "Type": "algorithm"
    #     }
    # }
    # """
    # output = model.write_code(
    #     content=content,
    #     file_path="./runs/test1.json",
    #     lang="json"
    # )

    ## --- job query
    # output = model.interface(
    #     messages=messages,
    #     worker_config={
    #         "intention_understanding": False,
    #     },
    #     function={
    #         "name": "call_boss_jobs_query",
    #         "args": {
    #             "job_ids": [21308821],
    #             "query_opt": ""
    #         }
    #     }
    # ) # [{}, {}]
    # output = json.loads(output)
    # if isinstance(output, list) and len(output) > 0:
    #     for job in output:
    #         if job.get("status") != "idle":
    #             print(f"Job {job.get('job_id')} is waiting, start_time: {job.get('start_time')}.")
    #         if job.get("status") == "running":
    #             print(f"Job {job.get('job_id')} is running, start_time: {job.get('start_time')}, run_time: {job.get('run_time')}.")
    #         if job.get("status") == "held":
    #             print(f"Job {job.get('job_id')} is held, start_time: {job.get('start_time')}, memory_usage: {job.get('memory_usage')}, command: {job.get('command')}.")
    # else:
    #     print("No job status returned, maybe they are all finished.")

    ## --- get branch name
    # output = model.interface(
    #     messages=messages,
    #     worker_config={
    #         "intention_understanding": False,
    #     },
    #     function={
    #         "name": "call_getting_branch_name",
    #         "args": {
    #             "root_path": "./besiii/ExampleData/signal.root",
    #         }
    #     }
    # ) # "\\nProcessing besiii/tools/get_branchNames.C(\\\"./besiii/ExampleData/signal.root\\\")...\\n1 files loaded to the TChain named 't_data'.\\nTree Name: sigma\\n  Branch Name: runNo\\n  Branch Name: evtNo\\n  Branch Name: tagNo\\n  Branch Name: indexmc\\n  Branch Name: pdgid\\n  Branch Name: motheridx\\n  Branch Name: nTot\\n  Branch Name: nCharg\\n  Branch Name: npCharg\\n  Branch Name: nnCharg\\n  Branch Name: nNeu\\n  Branch Name: mode\\n  Branch Name: v_svtx_chisq\\n  Branch Name: k_chisq\\n  Branch Name: lambda_len\\n  Branch Name: lambda_len_err\\n  Branch Name: lambda_len_err_ra\\n  Branch Name: lambda_mass\\n  Branch Name: lambda_e\\n  Branch Name: lambda_costheta\\n  Branch Name: lambda_rho\\n  Branch Name: lambda_phi\\n  Branch Name: pi_jpsi_mass\\n  Branch Name: pi_jpsi_e\\n  Branch Name: pi_jpsi_costheta\\n  Branch Name: pi_jpsi_rho\\n  Branch Name: pi_jpsi_phi\\n  Branch Name: sigma_mass\\n  Branch Name: sigma_e\\n  Branch Name: sigma_costheta\\n  Branch Name: sigma_rho\\n  Branch Name: sigma_phi\\n  Branch Name: lambda_pi_mass\\n  Branch Name: lambda_sigma_mass\\n  Branch Name: sigma_pi_mass\\n\"


    return output


async def request_worker_test(messages: List[Dict], **kwargs) -> Union[str, AsyncGenerator[str, None]]:
    """
    Request the worker test function based on the messages.
    This function is used to test the worker's ability to respond to simple messages.
    Args:
        messages (List[Dict]): A list of messages containing the request.
        kwargs: Additional keyword arguments.
    Returns:
        Union[str, AsyncGenerator[str, None]]: The output of the worker test function.
    """

    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
        )
    
    msg = messages[-1]["content"]
    logger.info(f"msg: {msg}")

    output = model.hello_world(messages=msg)
    yield output


async def request_mapping(messages: List[Dict], **kwargs) -> Union[str, AsyncGenerator[str, None]]:
    """
    Request the mapping function based on the messages.
    Types of mapping:
        - algorithm
        - joboption
        - fom
        - tmva
        - drawing
    The messages should contain a JSON string with the mapping request.
        
    Args:
        messages (List[Dict]): A list of messages containing the mapping request.
        kwargs: Additional keyword arguments.
    Returns:
        Union[str, AsyncGenerator[str, None]]: The output of the mapping function.
    """

    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    output = None
    json_content = None

    msg = messages[-1]["content"]
    logger.info(f"msg: {msg}")

    # from msg to json code
    match = re.findall(r'```json\n(.*?)\n```', msg, re.DOTALL)
    if match:
        json_content = match[0]
    else:
        json_content = msg


    # Check if the json_content is valid
    try: 
        json_content = msg
        json_code = json.loads(json_content)
    except:
        json_content = re.findall(r'```json\n(.*?)\n```', msg, re.DOTALL)[0]
        json_code = json.loads(json_content)
    logger.info(f"json_content: {json_content}")

    mapping_type = "unknown"

    if json_code.get("MetaData", {}).get("Type", "") == "algorithm":
        mapping_type = "algorithm"
    elif json_code.get("MetaData", {}).get("Type", "") == "joboption":
        mapping_type = "joboption"
    elif json_code.get("MetaData", {}).get("Type", "") == "drawing":
        mapping_type = "drawing"
    elif json_code.get("MetaData", {}).get("Type", "") == "fom":
        mapping_type = "fom"
    elif json_code.get("MetaData", {}).get("Type", "") == "tmva":
        mapping_type = "tmva"
    elif json_code.get("MetaData", {}).get("Type", "") == "Pull":
        mapping_type = "Pull" # TODO: optimize


    
    if mapping_type == "TH1" or mapping_type == "TH2" or mapping_type == "TH3" or mapping_type == "Pull":
        mapping_type = "drawing"

    logger.info(f"Finally, the mapping type is {mapping_type}")
    
    json_file_path = "./runs/" + uuid.uuid4().hex + ".json"
    output_name = uuid.uuid4().hex

    # json_file_path = "./runs/test.json"
    # output_name = "mytry"


    if mapping_type == "algorithm":
        output = model.write_code(content=json_content, file_path=json_file_path)
        output = model.interface(
            messages=messages,
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
    
    if mapping_type == "joboption":
        num_jobs = kwargs.get("num_jobs", 100)
        output = model.write_code(content=json_content, file_path=json_file_path)
        output = model.interface(
            messages=messages,
            worker_config={
                "intention_understanding": False,
            },
            function={
                "name": "call_joboption_mapping",
                "args": {
                    "json_file_path": json_file_path,
                    "template_path": "besiii/FixedJobOption",
                    "output_name": output_name,
                    "output_path": "./runs",
                    "num_jobs": num_jobs,
                }
            }
        )

    if mapping_type == "drawing":
        output = model.write_code(content=json_content, file_path=json_file_path)
        output = model.interface(
            messages=messages,
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

    if mapping_type == "fom":
        output = model.write_code(content=json_content, file_path=json_file_path)
        output = model.interface(
            messages=messages,
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

    if mapping_type == "tmva":
        output = model.write_code(content=json_content, file_path=json_file_path)
        output = model.interface(
            messages=messages,
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

    if mapping_type == "unknown":
        root_path = msg

        logger.info(f"Root path: {root_path}")
        output = model.interface(
            messages=[{"role": "user", "content": "Please query the job status."}],
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
        logger.info(f"Output: {output}")


    yield output


async def get_branch_name(root_path: str, **kwargs) -> str:
    """
    Get the branch name by root path.
    Args:
        root_path : path of root file.
        kwargs: Additional keyword arguments.
    Returns:
        str: The branch name extracted from the root file.
    """
    
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    if not root_path:
        logger.error("Root path is empty!")
        return ""
    
    logger.info(f"Root path: {root_path}")

    output = model.interface(
        messages=[{"role": "user", "content": "Please query the job status."}],
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
    logger.info(f"Output: {output}")

    return output


def request_job_query(job_ids: List[int], **kwargs) -> bool:
    """
    Query the job status by job IDs.
    Args:
        job_ids (List[int]): A list of job IDs to query.
        kwargs: Additional keyword arguments.
    Returns:
        bool: True if jobs are all finished, False otherwise.
    """
    model = HRModel.connect(
        name=worker_name,
        base_url=base_url,
        api_key=api_key,
    )

    if not job_ids:
        logger.error("Job IDs are empty!")
        return True
    
    if isinstance(job_ids, int):
        job_ids = [job_ids]
    logger.info(f"Job IDs: {job_ids}")

    # Check if job_ids is a list of integers
    if not all(isinstance(job_id, int) for job_id in job_ids):
        logger.error("Job IDs must be a list of integers!")
        return True
    
    # Job query
    query_opt = kwargs.get("query_opt", "-u")
    output = model.interface(
        messages=[{"role": "user", "content": "Please query the job status."}],
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
    logger.info(f"Output: {output}")

    # Convert output to JSON
    try:
        output = json.loads(output)
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON from output.")
        return False

    # Check Job status
    if isinstance(output, list) and len(output) > 0:
        for job in output:
            if job.get("status") != "idle":
                logger.info(f"Job {job.get('job_id')} is waiting, start_time: {job.get('start_time')}.")
            if job.get("status") == "running":
                logger.info(f"Job {job.get('job_id')} is running, start_time: {job.get('start_time')}, run_time: {job.get('run_time')}.")
            if job.get("status") == "held":
                logger.info(f"Job {job.get('job_id')} is held, start_time: {job.get('start_time')}, memory_usage: {job.get('memory_usage')}, command: {job.get('command')}.")
        return False
    else:
        logger.info("No job status returned, maybe they are all finished.")
        return True
