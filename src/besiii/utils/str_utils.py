from typing import List, Dict, Union, Callable, Any, Optional
from functools import wraps
import json
import re
import lxml.etree as ET

import sys
from pathlib import Path
here = Path(__file__).parent

#from besiii.configs import CONST


def extract_items_from_text(text) -> List[str]:
    """
    提取以序号开头的任务列表。支持多种序号，例如1)、1.。序号后面必须有至少一个空格！
    不支持(1)，因为'psi(3686) - pi pi Jpsi'可能会被误认为包含序号
    """
    pattern = r'(?:\d+\.\s|\(\d+\)\s)(.*?)(?=\s*(?:\d+\.\s|\(\d+\)\s|$))'
    #pattern = r'(?:(?<!\S)\d+\.\s|(?<!\S)$ \d+ $\s)(.*?)(?=\s*(?:(?<!\S)\d+\.\s|(?<!\S)$ \d+ $\s|$))'
    items = re.findall(pattern, text)

    if len(items) < 2: # 太少了说明大概率没有匹配到任务清单，可能是原文中不存在或者格式错误
        items = [text]

    return [item.strip() for item in items if item]

def extract_text_in_brackets(text: str) -> str:
    start_index = text.rfind('[') + 1
    end_index = text.rfind(']')
    if start_index >= 0 and end_index >= 0:
        return text[start_index:end_index]
    else:
        return f"No brackets found in the text: {text}"

def print_json(content: Union[str, dict], isPrint=True) -> str:
    """
    return
        1. the combined text of a json content str, or a json dict
        2. a pure text if not json
    """
    try:
        output = ""
        if isinstance(content, str):
            dict = json.loads(content)
        else:
            dict = content

        for key,value in dict.items():
            output += f"{key}: {value}\n"
        
        if isPrint:
            print(output)
        return output
    except json.JSONDecodeError:
        return content

def print_json_list(content: list, isPrint=True) -> str:
    """
    return
        1. the combined text of a list of json content
        2. a pure text if not json
    """
    if isinstance(content, list):
        for item in content:
            try:
                output = ""
                if isinstance(item, str):
                    dict = json.loads(item)
                else:
                    dict = item

                for key,value in dict.items():
                    output += f"{key}: {value}\n"
                
                if isPrint:
                    print(output)
                return output
            except json.JSONDecodeError:
                return content

# def convert_dict_to_str(content: Dict[str, Any]) -> str:
#     """
#     将传入的字典格式化为 'key: value' 的字符串。
#     """
#     if isinstance(content, dict) and content:
#         formatted_str = ', '.join(f"{k}: {v}" for k, v in content.items())
#         return formatted_str
#     else:
#         print(f"Error: content is not a valid dict or empty: '{content}'")
#         return content

def fix_json_string(string: str) -> str:
    # """
    # 让字符串变得能被json.loads()解析，去掉非JSON格式的符号，主要是{@"key": "value",@"key2": "value2"@}的三个@位置的噪音处理
    #     [0-9a-zA-Z\s]*代表任意数量的数字字母空格
    #     r'(\\)*\n'代表2*n个反斜杠+\n的字符串
    # """
    
    # # 替换JSON开头的 {\n " 为 { "
    # string = re.sub(r'^\s*{\s*(\\)*\n\s*"', '{ "', string) # 匹配奇数个转义符
    # string = re.sub(r'^\s*{\s*(\\)*\\n\s*"', '{ "', string) # 匹配偶数个转义符
    
    # # 替换JSON中间的 ,\n "" 为 , ""
    # string = re.sub(r',\s*(\\)*\n\s*"(.*?)":', r', "\2":', string) # 匹配奇数个转义符
    # string = re.sub(r',\s*(\\)*\\n\s*"(.*?)":', r', "\2":', string) # 匹配偶数个转义符
    
    # # 替换JSON结尾的 \n} 为 " } ，为了兼容key_value可能不是字符串的情况，不匹配引号" \n}
    # string = re.sub(r'(\\)*\n\s*}[ \t\r]*$', ' }', string) # 匹配奇数个转义符
    # string = re.sub(r'(\\)*\\n\s*}[ \t\r]*$', ' }', string) # 匹配偶数个转义符


    # string = string.strip("'")

    # tmp = "PLACEHOLDERPLACE"
    # string = re.sub(r"\nu", tmp, string) # 保留\nu
    # string = re.sub(r"\n", "", string) # 删除\n，因为其可能出现在字典的键与键值之外导致loads失败，例如"{\n \"key\": \"value\" \n}"
    # string = re.sub(tmp, r"\nu", string) # 恢复\nu
    string = re.sub(r"\\([^n])", r"\\\\\1", string) #将所有非n转义字符组替换，例如\x替换为\\x。转义符无法单独存在在字符串中，LLM生成的包含类似\n的字符串，其底层代码一定是\\n，不然即使在代码中看到的也一定是\n(变色，意味着是有特殊意义的换行符)。
    # identifier = "p|>_<|q"
    # string = string.replace(r"\n", identifier) # 先把\n替换成特殊标识符
    # string = string.replace("\\", "\\\\") # 替换转义符
    # string = string.replace(identifier, r'\n')

    string = sanitize_json(string)
    return string

def sanitize_json(raw_str):
    # 预处理：移除首尾空白字符
    s = raw_str.strip()
  
    # 1. 检查起始字符是否为[或{，否则找到第一个有效起始符
    start_chars = {'[', '{'}
    start_pos = 0
    for i, c in enumerate(s):
        if c in start_chars:
            start_pos = i
            break
    else:
        raise ValueError("字符串中未找到有效的JSON起始符([或{)")
  
    # 截取有效起始位置后的内容
    s = s[start_pos:]
  
    # 2. 检查末尾字符是否为]或}，否则找到最后一个有效结束符
    end_chars = {']', '}'}
    end_pos = len(s)
    for i in range(len(s)-1, -1, -1):
        if s[i] in end_chars:
            end_pos = i + 1  # 包含结束符
            break
    else:
        raise ValueError("字符串中未找到有效的JSON结束符(]或})")
  
    # 截取有效结束位置前的内容
    s = s[:end_pos]
  
    return s

def extract_json_content(string: str) -> Dict[str, Any] | str:
    pattern = r'"([^"]+)":\s*("(?:[^"\\]*(?:\\.[^"\\]*)*)"|\{[^{}]*\}|\[[^\[\]]*\]|true|false|null|[-+]?\d*\.?\d+)'
    matches = re.findall(pattern, string)

    result_dict = {}
    for result in matches:
        key = result[0]
        value = result[1] if result[1] else result[2]  # 选择非空的值

        if value == 'null':
            result_dict[key] = None
        elif value.startswith('{') and value.endswith('}'):
            result_dict[key] = eval(value)  # 小心使用 eval，确保输入安全
        elif value.startswith('[') and value.endswith(']'):
            result_dict[key] = eval(value)  # 小心使用 eval，确保输入安全
        else:
            # 默认处理为字符串
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]  # 去掉外部引号
            result_dict[key] = value
    
    return result_dict if result_dict else string

def fix_newlines(text: Any) -> Optional[str]:
    """
    Replace '\\n' with '\n'
    """
    if text is None or not isinstance(text, str):
        return text
    
    return text.replace("\\n", "\n")

def add_prefix(query, prefix=""):
    """
    Input: (pi AND (D OR Dstar)) NOT (upsilon(4S) OR 4660)
    Output: (ti pi AND (ti D OR ti Dstar)) NOT (ti upsilon(4S) OR ti 4660)
    """
    words = query.split()
    operators = ['AND', 'OR', 'NOT']

    if not prefix:
        return query
    
    new_words = []
    for iword in words:
        """
        首先处理单词中的括号，如Zc(3900)拆分成(Zc AND 3900)，因为arxiv api会用OR连接括号内外的词
        支持泛化的情况，比如纯单词'pi'，或者带一个括号的单词'(pi'
        """
        tmp_s = ""
        output = ""
        flag = 0
        isProcessed = False

        for i, letter in enumerate(iword):
            if letter == '(':
                flag = 1
                output += tmp_s
                tmp_s = ""
            elif letter == ')':
                flag += 2
            
            if flag == 3:
                tmp_s += letter
                if i == len(iword) - 1 or iword[i:i+2] == '))' or iword[i:i+3] == ')))':
                    tmp_s = tmp_s.replace('(', ' AND ').replace(')', '')
                else:
                    tmp_s = tmp_s.replace('(', ' AND ').replace(')', ' AND ')
                output += tmp_s
                tmp_s = ""
                flag = 0
                isProcessed = True
                continue
            
            tmp_s += letter
        output += tmp_s
        if isProcessed:
            output = f"({output})"
        
        iiwords = output.split()
        
        ## 对处理过括号之后的，可能被进一步分割的单词列表进行处理
        for word in iiwords:
            if word: # 非空字符串才处理
                if word not in operators:
                    new_word = ""
                    isWord = False # 是否检测到单词
                    for char in word:
                        if char.isalnum() and not isWord: # 检测单词首字母/数字
                            new_word += prefix + char
                            isWord = True
                        else: # start with bracket or rest of the word
                            new_word += char
                    new_words.append(new_word)
                else:
                    new_words.append(word)

    return ' '.join(new_words)

# def parse_keywords(string):
#     '''
#     split the string with '|' and return a list of keywords and a dictionary of variants"
#     Example: "3770|Zc3900|hidden|quark:quarks|pi:pi,π,pions"
#     Output: keywords = ['3770', 'Zc3900', 'hidden', 'quark', 'pi'], variants = {'quark': ['quarks'], 'pi': ['pi', 'π', 'pions']}
#     '''
#     # 分割字符串为列表
#     parts = string.split('|')
    
#     keywords = []
#     variants = {}
    
#     for part in parts:
#         # 检查是否包含拼写变体
#         if ':' in part:
#             key, value = part.split(':')
#             variants[key] = value.split(',')
#         elif part: # 没有拼写变体且非空
#             keywords.append(part)

#     return keywords, variants

# def construct_searchquery(keys_and, keys_not, category=""):
#     if category:
#         category = category + " "
    
#     query = ""
#     keys_and_keys, keys_and_variants = parse_keywords(keys_and)
#     if keys_and_keys:
#         query = " AND ".join(category + key for key in keys_and_keys)
#     for key, value in keys_and_variants.items():
#         query += " AND (" + " OR ".join(category + variant for variant in value) + ")"
#     if query.startswith(" AND "): # remove the initial " AND "
#         query = query[5:]

#     keys_not_keys, keys_not_variants = parse_keywords(keys_not)
#     if keys_not_keys:
#         query += " AND NOT " + " AND NOT ".join(category + key for key in keys_not_keys)
#     for key, value in keys_not_variants.items():
#         query += " AND NOT (" + " OR ".join(category + variant for variant in value) + ")"
    
#     return query

def print_args(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 获取函数参数的名称和默认值
        arg_info = func.__code__.co_varnames[:func.__code__.co_argcount]
        
        # 创建一个字典用于保存参数名和实际传入值
        actual_args = {}
        
        # 将位置参数与参数名对应
        for i, arg in enumerate(arg_info):
            if i < len(args):
                actual_args[arg] = args[i]
        
        # 处理关键字参数
        for key in kwargs:
            actual_args[key] = kwargs[key]

        print("\033[92m" + f"Arguments passed to {func.__name__}: {actual_args}" + "\033[0m")
        rst = func(*args, **kwargs)
        return rst
    return wrapper

# def mathml2latex(text: str) -> str:
#     """ Find MathML codes and replace it with its LaTeX representations."""
#     mml_codes = re.findall(r"(<math.*?<\/math>)", text)
#     for mml_code in mml_codes:
#         mml_ns = mml_code.replace('<math>', '<math xmlns="http://www.w3.org/1998/Math/MathML">') #Required.
#         mml_dom = ET.fromstring(mml_ns)
#         xslt = ET.parse(f"{CONST.REPO_ROOT}/besiii/utils/xsltml_2.0/mmltex.xsl")  ## see http://xsltml.sourceforge.net/
#         transform = ET.XSLT(xslt)
#         mmldom = transform(mml_dom)
#         latex_code = str(mmldom)
#         text = text.replace(mml_code, latex_code)
#     return text

def get_strings_based_on_length(str_list: List[str], max_length: int = 2000) -> List[str]:
    # 检查列表是否为空
    if not str_list:
        return []

    # 计算前三个字符串的长度
    length = 0
    for s in str_list[:3]:
        length += len(s)

    if length > max_length:
        return str_list[:3]  # 如果超过2000字，返回前3个字符串
    else:
        return str_list[:5]  # 如果不超过2000字，返回前5个字符串

def chunk_string(text: str, chunk_size: int = 10, overlap: int = 0):
    """
    把文本分割成指定大小的小块，可选择设置重叠部分
    
    参数:
        text: 要分割的文本
        chunk_size: 每个小块的字符数量
        overlap: 相邻小块之间的重叠字符数
    
    返回:
        生成器，每次生成一个文本块
    """
    if chunk_size <= 0:
        raise ValueError("块大小必须是正整数")
    if overlap < 0:
        raise ValueError("重叠部分不能是负数")
    if overlap >= chunk_size:
        raise ValueError("重叠部分必须小于块大小")
    
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        yield text[start:end]
        if end == text_length:
            break
        start += chunk_size - overlap


def extract_specific_info(string: str) -> str:
    # 正则表达式模式，匹配 "- new generated files:" 和两个换行符之间的内容
    pattern = r'- new generated files:(.*?)\n\n'

    # 使用search方法找到第一个匹配的内容
    match = re.search(pattern, string, re.DOTALL)

    # 如果找到了匹配的内容，则提取位于两个标记之间的部分
    if match:
        content = match.group(1)
    else:
        return "No matching content found."
    
    # 正则表达式模式，匹配每一行的文件名和链接
    pattern = r'\|\ \d+ \|\ \[(.*?)\]\((.*?)\)'

    # 使用findall方法找到所有匹配的内容
    matches = re.findall(pattern, content, re.DOTALL)

    # 提取文件名和链接
    files_and_links = []
    for match in matches:
        # 从匹配的内容中提取文件名和链接
        file_name = match[0]  # 对应正则表达式中的第1个捕获组
        link = match[1]       # 对应正则表达式中的第2个捕获组
        files_and_links.append((file_name, link))

    output_string = "新生成的文件路径如下:\n"
    for file_name, link in files_and_links:
        output_string += f"{link}\n"
    return output_string.strip("\n")  # 去掉末尾的换行符

if __name__ == '__main__':
    # # 测试字符串
    # test_string = 'This is a test string with a MathML expression <math display="inline"><msup><mi>e</mi><mo>+</mo></msup><msup><mi>e</mi><mo>-</mo></msup></math>.'

    # # 检测并转换MathML字符串为LaTeX
    # output_string = mathml2latex(test_string)
    # print(output_string)

    # 示例使用
    # query = "(pi AND (D OR Dstar)) NOT (upsilon(4S) OR 4660)"
    # modified_query = add_prefix(query)
    # print(modified_query)  # 输出: "ti pi AND ti K"

    string = """
    - new generated files: \n| 序号 | 文件名 |\n|-----|-------|\n| 1 | [requirements](./runs/Psi4260PiPiJpsiAnalysis_DrSai/Psi4260PiPiJpsiAnalysis_DrSai-00-00-01/cmt/requirements) |\n| 2 | [ana.txt](./runs/Psi4260PiPiJpsiAnalysis_DrSai/Psi4260PiPiJpsiAnalysis_DrSai-00-00-01/run/ana.txt) |\n| 3 | [Psi4260PiPiJpsiAnalysis_DrSai.cxx](./runs/Psi4260PiPiJpsiAnalysis_DrSai/Psi4260PiPiJpsiAnalysis_DrSai-00-00-01/src/Psi4260PiPiJpsiAnalysis_DrSai.cxx) |\n| 4 | [Psi4260PiPiJpsiAnalysis_DrSai.h](./runs/Psi4260PiPiJpsiAnalysis_DrSai/Psi4260PiPiJpsiAnalysis_DrSai-00-00-01/src/Psi4260PiPiJpsiAnalysis_DrSai.h) |\n| 5 | [runs_job_2025-06-04_194622_098236.out](./logs/runs_job_2025-06-04_194622_098236.out) |\n| 6 | [runs_job_2025-06-04_194622_098236.err](./logs/runs_job_2025-06-04_194622_098236.err) |\n
    """
    print(extract_specific_info(string))