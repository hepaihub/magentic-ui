
from typing import List, Dict, Union
from hepai import HRModel
import re


async def hairag_client(messages: List[Dict], **kwargs) -> Dict[str, str]:
    """
    This function is a RAG client for the DrSaiAPP. It connects to the RAG model and retrieves the reference materials
    based on the user's query. The reference materials are then used to generate a new question for the user.

    Paras:
    - messages (List[Dict]): A list of messages in the chat history.
    - mapping (bool): A flag to indicate whether the user's query contains a mapping statement.

    Ret:
    - List[Dict]: A list of messages in the chat history.
    """
    
    model = HRModel.connect(
        name="hepai/hai-rag-OS",
        base_url="http://aidev.ihep.ac.cn:42899/apiv2"
        # name="hepai/hai-rag-xiongdb",
        # base_url="http://aidev.ihep.ac.cn:42898/apiv2"
    )

    query = messages[-1]["content"]  # Select the last message of the chat history as the RAG query statement.

    mapping = kwargs.get("mapping", False)
    if mapping:
        print("\nMapping statement detected.")
        if re.search(r"(job\s?option)", query, re.IGNORECASE):
            query = "Generate a BESIII JobOption file."
        elif re.search(r"(algorithm)", query, re.IGNORECASE):
            query = "Generate a BESIII analysis algorithm file."
        elif re.search(r"(drawing)", query, re.IGNORECASE):
            query = "Generate a CERN ROOT drawing file."
        print(f"New query: {query}")

    memory_config = kwargs.get("memory_config")
    username = memory_config.get("username", "Zijie")
    collection = memory_config.get("collection", "test")
    method = memory_config.get("method", "retrieve")
    similarity_top_k = memory_config.get("similarity_top_k", 5)
    verbose = memory_config.get("verbose", False)

    results = model.interface(
        username=username,
        collection=collection,
        method=method,
        content=query,
        similarity_top_k=similarity_top_k,
    )

    ## 请保证retrieve_txt是List格式
    if method == "get_full_text":
        #retrieve_txt = results[0]["full_text"]
        retrieve_txt = results[0]
    else:
        retrieve_txt = ''
        for result in results:
            retrieve_txt += result['node']['text']

    if verbose:
        print(f"*Searching RAG ::: username: {username}, collection: {collection}, method: {method}, similarity_top_k: {similarity_top_k} *")
        print(f"Retrieve text: {retrieve_txt}")

    last_txt = f"\n\nPlease provide closely related answers based on the reference materials provided below. Ensure that your response is closely integrated with the content of the reference materials to provide appropriate and well-supported answers.\nThe reference materials are: {retrieve_txt}."
    messages[-1]["content"] += last_txt
    
    return {"messages":messages, "retrieve_txt":retrieve_txt}


