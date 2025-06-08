import  sys
import os
from typing import List, Dict, Tuple, Optional, Any, Literal
from typing_extensions import Annotated
import requests
from bs4 import BeautifulSoup
import mechanize
import urllib.error
import http.cookiejar as cookielib
import urllib.request
# import feedparser
from urllib.parse import quote
import json
import arxiv
import time
import re
import base64

from besiii.configs import CONST
from besiii.utils import str_utils
from besiii.utils.pdf_parser import pdf_parser_by_mineru
from besiii.utils import Logger

logger = Logger.get_logger("tool_calls_register.py")

from pathlib import Path
here = Path(__file__).parent
this_filename = f'{here.parent}/tool_calls_register.py'


# 在环境变量中加载DocDB的用户名和密码、serpapi搜索API的API_KEY
api_key_serpapi = os.environ.get("SERPAPI_API_KEY", None) or "389a1c2fa8394ede00168f7405e794f56edb917b0235434a8f0040e6863ee68a"
DOCDB_ACCOUNT = os.environ.get("DOCDB_ACCOUNT", None) or "zhangbolun@ihep.ac.cn"
DOCDB_PASSWORD = os.environ.get("DOCDB_PASSWORD", None) or "Zhang808515"


#########################################################################################################
## 文章检索结果输出格式化定义及其他工具
def article_output_formatting(title="", url="", authors=None, published_date="", abstract="", **kwargs) -> str:
    ## add hyperlink and convert to markdown format
    article_info = {}
    article_info["Title"] = f"[{title}]({url})" if url and url != "Unknown" else title
    
    formatted_authors = ""
    if authors:
        formatted_authors = ', '.join(authors[:3]) + ' *et al.*' if len(authors) > 3 else ', '.join(authors)
    article_info["Authors"] = formatted_authors

    article_info["Published date"] = published_date
    
    # abstract_split = abstract.split()
    # if len(abstract_split) > 50:
    #     # abstract_short = " ".join(abstract_split[:10]) + "..."
    #     # article_info["Abstract"] = f"<details>\n<summary>{abstract_short}</summary>\n{abstract}\n</details>"
    #     article_info["Abstract"] = " ".join(abstract_split[:50]) + "..."
    # else:
    #     article_info["Abstract"] = abstract
    article_info["Abstract"] = abstract # 假如作为参考意见给Host，则直接提供完整内容
    

    ## 假如需要全文，重新组织输出信息
    if kwargs.get("full_text", None):
        article_info.clear()
        article_info["Title"] = title
        article_info["Full text"] = kwargs["full_text"]
    
    output = ""
    for key, value in article_info.items():
        output += f"**{key}:** {value}\n"
    return output

def articleInfos_to_string(source: str, article_infos: Dict[str, str], url: str = "") -> str:
    output = ""
    if not article_infos:
        output = f'''Oops, no article found in {source}. Please check your query url:\n```\n{url}\n```'''
    else:
        if len(article_infos) > 1:
            for key, value in article_infos.items():
                output += f"**Result {key+1}:**\n{value}\n\n"
        else:
            output = article_infos[0]
        
        output = "Here are the articles found in " + source + ":\n\n" + output
    
    output = str_utils.mathml2latex(output)
    return output

def query_formatting(query: str) -> str:
    tokens = query.split()
    result = []
    current_group = []

    for i, token in enumerate(tokens):
        if token in {'AND', 'OR', 'NOT'}:
            if current_group:
                result.append('(' + ' AND '.join(current_group) + ')' if len(current_group) > 1 else current_group[0])
                current_group = []  # 重置当前组

            result.append(token)  # 添加逻辑符号

        else:
            current_group.append(token)

    if current_group:
        result.append('(' + ' AND '.join(current_group) + ')')

    return ' '.join(result)

def docDB_request(url: str = "") -> str:
    if not url:
        return "No url provided to request DocDB."
    # url = "https://docbes3.ihep.ac.cn/cgi-bin/DocDB/ShowDocument?docid=1458"
    # url = "https://docbes3.ihep.ac.cn/cgi-bin/DocDB/Search?&titlesearch=3770+reconstruction&titlesearchmode=allsub&outformat=xml"
    # url = "view-source:https://docbes3.ihep.ac.cn/cgi-bin/DocDB/ShowDocument?docid=1515&version=1"
    
    cj = cookielib.CookieJar()
    br = mechanize.Browser()
    br.set_handle_robots(False)
    br.set_cookiejar(cj)

    br.set_handle_equiv(True)
    br.set_handle_gzip(True)
    br.set_handle_redirect(True)
    br.set_handle_refresh(False)
    br.set_handle_referer(True)
    br.set_handle_robots(False)

    br.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(), max_time=1)
    br.addheaders = [('User-agent', 'Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.0.1) Gecko/2008071615 Fedora/3.0.1-1.fc9 Firefox/3.0.1')]

    br.open(url, timeout=10)  # 增加超时设置

    br.select_form(nr=0)
    br.form['j_username'] = DOCDB_ACCOUNT
    br.form['j_password'] = DOCDB_PASSWORD
    br.submit()
    br.select_form(nr=0)
    br.submit()

    response = br.response().read()
    # print(response)
    return response

#########################################################################################################

query_prompt = """
        Return a effective search string using non-metadata keywords. Please think step by step to generate the search string because this is very important. Here are the steps:
        1. **Keyword Extraction**:
            - Extract only keywords that pertain to the article's main content, such as the title, main body, author names, or abstract. Please refrain from including metadata like publication date and source.
        2. **English Translation**:
            - Translate keywords to English if they aren't already.
        3. **Logical Operator Explanation**:
            - Use logical operators to connect the keywords, where:
                - **AND**: All keywords must appear simultaneously.
                - **OR**: At least one keyword must meet the condition.
                - **NOT**: Certain keywords should not appear in the search results.
            - The combinations of keywords can be nested.
        4. **Special Handling**:
            - If there are names of high-energy physics particles (e.g., "Zc3900"), generate 3-5 spelling variants in LaTeX format as needed, connecting them with "OR" to improve retrieval accuracy. For example, to search for "Zc3900", use: "(Zc3900 OR 3900 OR Z_c(3900) OR Z*(3900) OR Z_{c}*)".

        ### Sample Requests and Outputs

        - **Example 1**:
        - **Request**: Find 4 articles about COVID-19, vaccination, or public health policies, avoiding the field of mental health.
        - **Output**: "(COVID AND 19) OR vaccination OR (public AND health AND policies) NOT (mental AND health)"

        - **Example 2**:
        - **Request**: Find articles about the discovery of a new elementary particle, such as the discovery of a new particle called "psi(3770)."
        - **Output**: "discovery AND (psi(3770) OR 3770 OR psi3770)"
    """

TIME_SLEEP = 3 


@str_utils.print_args
def arxiv_search(
    query: Annotated[str, query_prompt], # must be the first parameter, otherwise error. PS: if you wanna requried parameters, do not use default value!
    category: Annotated[Literal["astro-ph", "cond-mat", "gr-qc", "hep-ex", "hep-lat", "hep-ph", "hep-th", "math-ph", "nlin", "nucl-ex", "nucl-th", "physics", "quant-ph", "cs", "econ", "eess", "math", "q-bio", "q-fin", "stat"], "The article's category. "] = "",
    metadata: Annotated[Literal["ti", "au", "abs", "id", "co", "all"], f"The search scope. 'ti' for titles, 'au' for authors, 'abs' for abstracts, 'id' for arXiv identifiers, 'co' for comments, and 'all' to search across all categories by default."] = "all",
    index: Annotated[int, "The starting index of the initial article displayed in the search results list."] = 0,
    max_results: Annotated[int, "Specify the exact number of articles to retrieve based on user query. For example, if the user asks for '3 articles on topic X' or '找三篇关于3770的文章', set this value to 3."] = 3,
    is_content_needed: Annotated[bool, "Return True if the full text of the article is needed."] = False,
    # **kwargs: Annotated[Any, "Additional keywords to be passed to the function."], # so many similar search functions, the parameters may be confusing for LLM.
) -> str:
    """
    Search for articles in arXiv. This is the preferred choice for searching papers.
    """

    client = arxiv.Client()
    
    ## 构建query字符串
    query_pro = str_utils.add_prefix(query, metadata + ":") # arxiv use "ti:keywords"
    query_pro = query_formatting(query_pro) # 格式化query字符串
    query_pro = query_pro.replace("*", "").replace("{", "").replace("}", "") # arxiv API检索不支持通配符和花括号，单词的括号也会影响结果
    
    ## 检索
    search = arxiv.Search(
        query = query_pro,
        max_results = max_results, # seems bug here, always =100 in query url
        sort_by = arxiv.SortCriterion.SubmittedDate, # "Relevance", "LastUpdatedDate", "SubmittedDate" ### ???用SubmittedDate或LastUpdatedDate时复杂逻辑式直接什么也搜不到，例如all:Zc3900 OR all:3900 OR all:Z_c(3900) OR all:Z(3900) OR (all:Z_c) #NOTE 不是搜索不到，而是单词括号内外的内容会当做单独的东西去搜索。比如Z(3900)，他实际会按照Z OR 3900去搜，导致匹配大量无关文章
        sort_order = arxiv.SortOrder.Descending, # "Ascending" or "Descending"
        # id_list=[], # no need to use: search_by_id = arxiv.Search(id_list=["1605.08386v1"]),
    )

    ## 处理结果
    article_infos = {}
    for i, paper in enumerate(client.results(search)):          
        title = paper.title
        authors = [author.name for author in paper.authors]
        published_date = paper._raw.published[:10]
        #article_url = paper.entry_id
        article_url = paper.pdf_url
        abstract = paper.summary

        ## 下载与解析pdf
        params = {}
        if is_content_needed:
            paper.download_pdf(dirpath=f"{CONST.FILE_DIR}", filename=f"{article_url.split('/')[-1]}.pdf")
            #paper.download_source(dirpath=f"{CONST.FILE_DIR}", filename=f"{paper.id}.tar.gz") # 源代码
            pdf_content = pdf_parser_by_mineru(
                path=f"{CONST.FILE_DIR}/{article_url.split('/')[-1]}.pdf")
            params["full_text"] = pdf_content
        
        article_info = article_output_formatting(title=title, authors=authors, published_date=published_date, url=article_url, abstract=abstract, **params)
        article_infos[i] = article_info

    
    ## 输出结果
    output = articleInfos_to_string(source="arXiv", article_infos=article_infos, url=query_pro)

    time.sleep(TIME_SLEEP) # 延迟3秒，避免频繁访问服务器
    return output

@str_utils.print_args
def inspire_search(
    query: Annotated[str, query_prompt], # must be the first parameter, otherwise error
    record_type: Annotated[Literal['literature', 'authors', 'institutions', 'conferences', 'seminars', 'journals', 'jobs', 'experiments', 'data'], "The record type."] = "literature",
    author_names: Annotated[List[str], f"The author names."] = None,
    isExactAuthor: Annotated[bool, "Return true if the user specifies that the request author name is the exact author name of the article."] = False,
    isFirstAuthor: Annotated[bool, "Return true if the user specifies that the request author name is the first author of the article."] = False,
    collaboration: Annotated[str, f"The collaboration name. Example: 'BESIII'"] = "",
    number_of_authors: Annotated[str, "If the user specifies the required number of authors, return the number in a specific format. Examples include: 'exactly 5 authors': '5', 'at least 5 authors': '5+', 'larger than 5 authors': '10+', 'at most 10 authors': '10-', 'at least 10 and at most 20 authors': '10-20'"] = "0+",
    Affiliation: Annotated[str, f"The affiliation."] = "",
    metadata: Annotated[Literal["ti", "au", "abs", "id", "co", "all"], f"The search scope. 'ti' for titles, 'au' for authors, 'abs' for abstracts, 'id' for arXiv identifiers, 'co' for comments, and 'all' to search across all categories by default."] = "all",
    #keys_and: Annotated[str, f"Extract keywords from the provided text that must all be valid simultaneously during searching. Generate spelling variations for elementary particle names or frequently used alternative forms, excluding plural or past tense variations. If the user is unsure about certain keywords and offers other options (like A or B), use these options as spelling variations of the original keyword like 'A:A,B'. Please think step by step, first extract the keywords which is supposed to be connected by 'and' to search, then identify the variations of the keywords, and finally generate the output in a specific format, such as 'keyword1:keyword1,variation1,variation2|keyword2:keyword2,variation1,variation2|keyword3|keyword4|...'. {seperator_prompt} Here are some examples: 1. the extracted keywords: '3770, Zc3900, pi, mu, electron, quark, experiment, energy', the output should be: '3770|Zc3900:Zc3900,3900,Zc(3900),Z_c(3900),Z*(3900),Z_c*|pi:pi,pion|mu:mu,muon|electron|quark|experiment|energy'. 2. the extracted keywords: 'psip, hc, p-wave, hidden-charm, charmonium, Jpsi, psi(3770), K-mesons', the output should be: 'psip:psi3686,3686,psi(3686)|hc:hc,h_c|p|wave|hidden|charm|charmonium|Jpsi:Jpsi,J/psi|psi|3770|K:K,kaon|mesons'. {language_setting}"] = "",
    # keys_or: Annotated[Optional[str], f"Extract keywords from the provided text that are connected by 'or', indicating that one of them must be valid during searching. Generate spelling variations for elementary particle names or frequently used alternative forms, excluding plural or past tense variations. {seperator_prompt} Here are some examples: 1. the extracted keywords: '3770, Zc3900, pi, mu, electron, quark, experiment, energy', the output should be: '3770|Zc3900:Zc3900,3900,Zc(3900),Z_c(3900),Z*(3900),Z_c*|pi:pi,pion|mu:mu,muon|electron|quark|experiment|energy'. 2. the extracted keywords: 'psip, hc, p-wave, hidden-charm, charmonium, Jpsi, psi(3770), K-mesons', the output should be: 'psip:psi3686,3686,psi(3686)|hc:hc,h_c|p|wave|hidden|charm|charmonium|Jpsi:Jpsi,J/psi|psi|3770|K:K,kaon|mesons'. {language_setting}"] = "",
    #keys_not: Annotated[Optional[str], f"Extract keywords that users DO NOT want to search for from the provided text. Generate spelling variations for elementary particle names or frequently used alternative forms or the alternative words the user wants to search, excluding plural or past tense variations. {seperator_prompt} Please think step by step, first extract the keywords which is supposed to be excluded in searching, then identify the variations of the keywords, and finally generate the output in a specific format, such as 'keyword1:keyword1,variation1,variation2|keyword2:keyword2,variation1,variation2|keyword3|keyword4|...'. Here are some examples: 1. the extracted keywords: '3770, 3686, Zc3900, pi, mu, electron, quark, experiment, energy' where one of '3770' and '3686' is required to be valid, the output should be: '3770:3770,3686|Zc3900:Zc3900,3900,Zc(3900),Z_c(3900),Z*(3900),Z_c*|pi:pi,pion|mu:mu,muon|electron|quark|experiment|energy'. 2. the extracted keywords: 'psip, hc, p-wave, hidden-charm, charmonium, Jpsi, psi(3770), K-mesons', the output should be: 'psip:psi3686,3686,psi(3686)|hc:hc,h_c|p|wave|hidden|charm|charmonium|Jpsi:Jpsi,J/psi|psi|3770|K:K,kaon|mesons'. {language_setting}"] = "",
    texkey: Annotated[str, f"The texkey. Examples: 'Bala:2019qcu', 'Asbury:1968zz', 'Iacovelli:2024mjy'."] = "",
    Eprint: Annotated[str, f"The eprint ID. Examples: 'arXiv:1907.11692v1', '1207.7214', 'arXiv:2408.16649', '2408.07593', 'hep-ph/0603175', 'hep-th/0309125', 'hep-ex/0309015'."] = "",
    doi: Annotated[str, f"The DOI. Examples: '10.1103/PhysRevLett.19.1264', '10.1016/0550-3213(79)90082-8', '10.1088/1475-7516/2018/07/014', 'https://doi.org/10.48550/arXiv.2406.15813', 'https://doi.org/10.1002/apxr.202400057', 'https://doi.org/10.48550/arXiv.2404.03675', '10.48550/arXiv.2404.03675'."] = "",
    report_number: Annotated[str, f"The report number. Examples: 'IFJPAN-IV-2019-12', 'CERN-EP-2024-202', 'CERN-EP-2024-188'."] = "",
    record_id: Annotated[str, f"The record ID in the inspire data base. Examples: '1756201', '728300', '848110', 'recid 1742630', 'recid 801208', 'recid 728300'."] = "",
    document_type: Annotated[Literal["b", "c", "core", "i", "l", "note", "p", "proceedings", "r", "t"], f"The abbreviation of a specific document type requested. 'b' for books, 'c' for conference paper, 'core' for work covering high-energy-physics subjects, 'i' for introductory, 'l' for lectures, 'note' for experimental notes, 'p' for published papers, 'proceedings' for collected volume of a conference proceedings, 'r' for reviews, 't' for thesis"] = "",
    date: Annotated[str, f"The date range to search for. Examples: '2018+' for 'after 2018', '2020-' for 'before 2020', '2000-2020' for 'from 2000 to 2020', '2000' for 'in 2000'"] = "",
    journal: Annotated[str, f"The journal name. Examples: 'Phys.Rev.' for 'Physical Review', 'Mod.Phys.Lett.' for 'Modern Physics Letters', 'PoS' for 'Proceedings of Science', 'Comments Nucl.Part.Phys.' for 'Comments on Nuclear and Particle Physics', etc."] = "",
    citation_number: Annotated[str, f"The number of citations. Examples: '100+' for 'over 100 citations', '20+' for 'larger than 20 citations', '5-' for 'less than 5 citations', '100-200' for 'between 100 and 200 citations', '100' for 'exactly 100 citations'."] = "",
    isCheckRecord: Annotated[bool, "Return true if the user is looking to perform a citation search to see if a paper is cited by other papers."] = False,
    sort_order: Annotated[Literal["mostrecent", "mostcited", "dateasc", "datedesc", "deadline"], "The sort order of the search results.'mostrecent' and 'deadline' for the jobs type. 'dateasc' and 'datedesc' for conferences and seminars, in which 'dataasc' means the earliest starting date appear first, and 'datedesc' means the most recent starting date appear first."] = "mostrecent",
    max_results: Annotated[int, "The number of articles the user would like to search for."] = 3,
    is_content_needed: Annotated[bool, "Return True if the full text of the article is needed."] = False,
    # **kwargs: Annotated[Any, "Additional keywords to be passed to the function."], # so many similar search functions, the parameters may be confusing for LLM.
) -> str:
    """
    Search for articles in INSPIRE, a database of high-energy physics papers.
    """
    
    query_string = "" # the full query string for the API request
    
    ## unique IDs
    if texkey:
        query_string = f"q={texkey}"
    if Eprint:
        query_string = f"q={Eprint}"
    if doi:
        query_string = f"q={doi}"
    if report_number:
        query_string = f"q=rn {report_number}"
    if record_id:
        ## 去掉可能存在的recid和空格前缀
        record_id = record_id.replace("recid", "").strip()  
        query_string = f"q=recid {record_id}"
    
    if not query_string: # 没有唯一识别码
        query_string = "q="
        
        ## initial with keywords
        query_pro = str_utils.add_prefix(query, "ti ") if metadata == "ti" else query
        query_pro = query_formatting(query_pro) # 格式化query字符串
        query_string += query_pro

        ## general search
        author_prefix = "au"
        if isExactAuthor:
            author_prefix = "ea"
        elif isFirstAuthor:
            author_prefix = "fa"
        if author_names:
            query_string += " AND (" + " AND ".join([f"{author_prefix} {author}" for author in author_names]) + ")"

        if collaboration:
            query_string += f" AND cn {collaboration}"
        if Affiliation:
            query_string += f" AND aff {Affiliation}"   
        if document_type:
            query_string += f" AND tc {document_type}"
        if date:
            date = quote(date)
            query_string += f" AND date {date}"
        if journal:
            query_string += f" AND j {journal}"
        if citation_number:
            citation_number = quote(citation_number)
            query_string += f" AND cited {citation_number}"
        number_of_authors = quote(number_of_authors)
        query_string += f" AND ac {number_of_authors}" # must handle "+,-" mark in the url

        ## other parameters
        query_string += f"&sort={sort_order}"
        #query_string += f"fields=titles,authors.full_name,authors.affiliations.record"
        query_string += "&format=json" # output format
    
    article_infos = {}
    # num_inspire = 0
    # num_arxiv = 0
    # num_docDB = 0
    # num_total = 0
    
    ## search in inspire
    url = f"https://inspirehep.net/api/{record_type}?{query_string}"
    print("\033[93m"+url+"\033[0m")
    #encoded_url = quote(url)
    response = requests.get(url)
    if response.status_code == 200:
        hits = response.json().get("hits", {})
        if hits:
            num_inspire = hits["total"]
            for i, entry in enumerate(hits["hits"]):
            #for i, entry in enumerate(response.json()["hits"]):
                if i > max_results - 1:
                    break
                # for j, entry2 in enumerate(entry):
                # #for j, entry2 in enumerate(entry["metadata"]):
                #     print(j, entry2)
                ## extract infos
                title = entry.get("metadata", {}).get("titles", [{}])[0].get("title", "Unknown")
                authors = entry.get("metadata", {}).get("authors", [])
                author_name_list = []
                for author in authors:
                    #full_name = author.get("full_name", "Unknown")
                    first_name = author.get("first_name", "Unknown")
                    last_name = author.get("last_name", "Unknown")
                    author_name_list.append(f"{first_name} {last_name}")
                    
                # first_author = entry.get("metadata", {}).get("first_author", {}).get("full_name", "Unknown")
                # if not first_author:
                #     first_author = entry.get("metadata", {}).get("authors", [{}])[0].get("full_name", "Unknown")
                published_date = entry.get("created", "")[:10]
                article_url = entry.get("metadata", {}).get("documents", [{}])[0].get("url", "Unknown")
                abstract = entry.get("metadata", {}).get("abstracts", [{}])[0].get("value", "Unknown")
                arxiv_id = entry.get("metadata", {}).get("arxiv_eprints", [{}])[0].get("value", "Unknown")
                if article_url == "Unknown" and arxiv_id != "Unknown":
                    article_url = f"https://arxiv.org/pdf/{arxiv_id}"
                
                ## 下载
                params = {}
                if is_content_needed:
                    if article_url != "Unknown":
                        # paper = next(arxiv.Client().results(arxiv.Search(id_list=[arxiv_id])))
                        # paper.download_pdf(dirpath=f"{CONST.FILE_DIR}", filename=f"{paper.id}.pdf")
                        # paper.download_source(dirpath=f"{CONST.FILE_DIR}", filename=f"{paper.id}.tar.gz") # 源代码
                        response = requests.get(article_url)
                        if response.status_code == 200:
                            arxiv_id_save = arxiv_id.split("/")[-1]
                            with open(f"{CONST.FILE_DIR}/{arxiv_id_save}.pdf", "wb") as file:
                                file.write(response.content)
                            
                            pdf_content = pdf_parser_by_mineru(
                                path=f"{CONST.FILE_DIR}/{article_url.split('/')[-1]}.pdf")
                            params["full_text"] = pdf_content
                        else:
                            print("Failed to download PDF file from inspire.")
                    else:
                        print("No PDF link found in INSPIRE.")
        
                article_info = article_output_formatting(title=title, authors=author_name_list, published_date=published_date, url=article_url, abstract=abstract, **params)
                article_infos[i] = article_info
    else:
        print("Failed to connect to INSPIRE.")
    
    ## 输出结果
    output = articleInfos_to_string(source="INSPIRE", article_infos=article_infos, url=url)
    
    time.sleep(TIME_SLEEP) # 延迟3秒，避免频繁访问服务器
    return output

@str_utils.print_args
def docDB_search(
    query: Annotated[str, query_prompt], # must be the first parameter, otherwise error
    metadata: Annotated[Literal["ti", "au", "abs", "id", "co", "all"], f"The search scope. 'ti' for titles, 'au' for authors, 'abs' for abstracts, 'id' for arXiv identifiers, 'co' for comments, and 'all' to search across all categories by default."] = "all",
    max_results: Annotated[int, "The number of articles the user would like to search for."] = 3,
    is_content_needed: Annotated[bool, "Return True if the full text of the article is needed."] = False,
    # **kwargs: Annotated[Any, "Additional keywords to be passed to the function."], # so many similar search functions, the parameters may be confusing for LLM.
) -> str:
    """
    Search for articles in DocDB, the internal database of BESIII. This function does not return papers related to BESIII itself, but only returns physical analysis articles produced by the BESIII collaboration.
    """
    try:
        base_url_docDB = "https://docbes3.ihep.ac.cn/cgi-bin/DocDB/Search?"
        category_map = {
            "ti": "title",
            "abs": "abstract",
            "key": "keywords",

        }
        query_pro = query_formatting(query) # 格式化query字符串
        url = base_url_docDB + f"titlesearchmode=allsub&titlesearch={query_pro}"
        response_docDB = docDB_request(url)
        soup = BeautifulSoup(response_docDB, 'html.parser')

        article_infos = {}
        for i, article in enumerate(soup.find('table', class_='Alternating DocumentList').find_all('tr')):
            docid_link = article.find('td', class_='Docid')
            if docid_link and docid_link.a:
                article_url = docid_link.a['href']
                docid = docid_link.a.get_text(strip=True)
                
                title_tag = article.find('td', class_='Title')
                title = title_tag.a.get_text(strip=True) if title_tag and title_tag.a else None
                
                author_tags = article.find('td', class_='Author')
                authors = [author.get_text(strip=True) for author in author_tags.find_all('a')] if author_tags else []
                
                updated_tag = article.find('td', class_='Updated')
                published_date = updated_tag.get_text(strip=True) if updated_tag else None

                ## get abstract from the article_url
                child_response_docDB = docDB_request(article_url)
                soup2 = BeautifulSoup(child_response_docDB, 'html.parser')
                abstract = soup2.find(text=lambda text: text and "Abstract" in text).find_next().text

                article_info = article_output_formatting(title=title, authors=authors, published_date=published_date, url=article_url, abstract=abstract)
                article_infos[i] = article_info
            
            if i > max_results - 1:
                break

        ## 输出结果
        output = articleInfos_to_string(source="DocDB", article_infos=article_infos, url=url)
        
        time.sleep(TIME_SLEEP) # 延迟3秒，避免频繁访问服务器
        return output
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"Error in web_searching of {this_filename} for " + str(e)
    
@str_utils.print_args
def web_searching(
    query: Annotated[str, "Questions or keywords that need to be searched"],
    engine: Annotated[Literal["google", "bing", "baidu"], "The search engine to use."] = "google",
    # **kwargs: Annotated[Any, "Additional keywords to be passed to the function."], # so many similar search functions, the parameters may be confusing for LLM.
) -> str:
    """Retrieve a wide range of up-to-date and various information from the internet."""
    engine=engine.lower()

    try:
        base_url = "https://serpapi.com/search.json"
        url = f"{base_url}?engine={engine}&q={query}&api_key={api_key_serpapi}"
        response = requests.get(url)
        results = response.json()
        organic_results = results.get("organic_results", [])
        
        output = ""
        for r in organic_results:
            #str_utils.print_json(result)
            position = r.get("position", "")
            title = r.get("title", "")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            output += f"**Result {position}:**\nTitle: {title}\nSnippet: {snippet}\nLink: {link}\n\n"
        
        if output:
            output = "Here are the search results from " + engine + ":\n\n" + output
        else:
            output = "No results found from " + engine + "."
        
        time.sleep(3) # 延迟3秒，避免频繁访问服务器
        return output
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"Error in web_searching of {this_filename} for " + str(e)