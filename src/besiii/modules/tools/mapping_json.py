import os, sys
from typing import List, Dict, Tuple, Optional, Any, Literal, Callable
from typing_extensions import Annotated
import json
import random
import math

from besiii.utils import str_utils
from besiii.modules.tools.tools_algorithm import *

AlgorithmName_share = None

def calculate_BeamEnergySpread(ecms: float, n: int):
    "unit: GeV"
    result = (-2.147 + 0.9454 * ecms) / (1000 * math.sqrt(2))
    return round(result, n)

@str_utils.print_args
def create_DrawCard(
    dataFilePath: Annotated[str, "数据文件的路径，支持通配符*，例如'/data/data_*.root'。该参数为必填项"],
    type: Annotated[Literal["TH1", "TH2", "TH3", "Pull"], "绘制的图像类型。'TH1'、'TH2'、'TH3'分别表示一维、二维、三维直方图，'Pull'表示Pull分布图。默认值为'TH1'"] = "TH1",
    variable: Annotated[List[Dict[str, Any]], "需要绘制的变量列表。每个变量的字典中包含'name'、'nBins'、'low'、'up'四个键值对，分别表示变量名称、分箱数量、下限值、上限值。后三者默认值均为-1，仅在用户的任务请求中明确指定时使用非默认值"] = [],
    # name: Annotated[List[str], "需要绘制的变量名称列表。若不指定，则绘制数据文件中的所有变量"] = [],
    # nBins: Annotated[List[Optional[int]], "直方图的分箱数量列表。若用户未指定，则使用默认值"] = None,
    # low: Annotated[List[Optional[float]], "变量绘制的下限值列表。若用户未指定，则使用默认值"] = None,
    # up: Annotated[List[Optional[float]], "变量绘制的上限值列表。若用户未指定，则使用默认值"] = None,
    exmcFilePath: Annotated[Optional[str], "遍举/信号/signal蒙特卡罗模拟数据文件的路径，支持通配符*。若未指定，则默认使用dataFilePath的值"] = None,
    inmcFilePath: Annotated[Optional[str], "单举/背景/inclusive蒙特卡罗模拟数据文件的路径，支持通配符*。若未指定，则默认使用dataFilePath的值"] = None,
    treeName: Annotated[Optional[str], "ROOT文件中存放数据的树名称。若未指定，则默认使用给定ROOT文件中第一个树的名称"] = None,
    cut: Annotated[Optional[str], "对数据的约束条件。该参数为可选项，用于筛选数据"] = None,
) -> str:
    """The tool to generate CERN ROOT drawing scripts.
    PS: CERN ROOT画图脚本是基于C++语言和CERN ROOT语言编写的画图程序，可以读取ROOT类型文件中的变量，将其绘制在画布上保存成图片返回。"""
    # 检查 exmcFilePath 和 inmcFilePath，如果未指定则使用 dataFilePath
    if exmcFilePath is None:
        exmcFilePath = dataFilePath
    if inmcFilePath is None:
        inmcFilePath = dataFilePath
  
    # 构建变量卡
    variable_card = {
        "type": type,
        "dataFilePath": dataFilePath,
        "exmcFilePath": exmcFilePath,
        "inmcFilePath": inmcFilePath,
        "treeName": treeName if treeName is not None else "",
        "variable": variable,
        "cut": cut if cut is not None else ""
    }

    # 将变量卡转换为 JSON 字符串
    output = json.dumps(variable_card, ensure_ascii=False, indent=4)
    output = "```json\n"+output+"\n```"

    return output

@str_utils.print_args
def create_AlgorithmCard(
    # ----- MetaData 元数据部分 -----
    AlgorithmName: Annotated[str, "用于该实验或数据处理的算法名称，例如'PipiJpsiAnalysis'。该名称根据给定衰变链自主生成，具有唯一性"],
    DecayChain: Annotated[str, "描述衰变过程的字符串，格式为'母粒子 -> 子粒子 [中间态 -> 末态]'，例如'psi(4260) -> pi+ pi- [J/psi -> mu+ mu-]'"],
    #CreationDate: Annotated[str, "JSON文件的创建日期，格式为'YYYY-MM-DD'，例如'2024-12-17'"],
    #Author: Annotated[str, "创建该JSON文件的作者姓名，例如'John Doe'"],
    #Reference: Annotated[List[str], "相关参考文献的链接或引用信息列表，例如arXiv或DOI链接，如['https://arxiv.org/abs/1234.5678', 'doi:10.1234/abcde']"],

    # ----- Sample 样本部分 -----
    Ecms_value: Annotated[float, "样本对应的质心系能量值，单位为GeV，例如3.097"],

    # ----- Selection 选择条件部分 -----
    ConstrainedResonanceList: Annotated[List[str], "衰变链中需要进行质量约束的中间共振态名称列表。例如['J/psi', 'psi(2S)']"] = [],
    MissTrack: Annotated[str, "在分析中故意不重建的粒子名称。由于探测器性能限制，高能物理分析中有时会忽略某些粒子以提高事例挑选效率。如果没有需要忽略的粒子，则留空"] = "",
    Method: Annotated[Literal["km_fit"], "运动学拟合方法，目前仅支持'km_fit'"] = "km_fit",
    SaveType: Annotated[Literal["Event", "Candidate"], "事例保存类型。'Event'表示保存完整事例信息，'Candidate'表示仅保存候选事例信息"] = "Event",
) -> str:
    """A specialized tool for generating analysis algorithms/cards tailored to the BESIII high-energy physics experiment.
    PS: 分析算法程序是BESIII实验基于C++语言和Gaudi框架编写的，利用多探测器信息以得到鉴别粒子的物理量，同时组合末态粒子以得到中间态粒子的程序包。用户通常会提供一个衰变链，并给出具体分析的质心能量。用户同时还可能会有一些额外的限制要求，例如运动学拟合的要求等等。"""
    AlgorithmName_share = AlgorithmName
    # ====== 数据组装逻辑 ======
    # -- MetaData组装 --
    metaData = {
        "AlgorithmName": AlgorithmName,
        "DecayChain": DecayChain,
        "Type": "algorithm",
        #"CreationDate": CreationDate,
        #"Author": Author,
        #"Reference": Reference
    }
  
    # -- Sample组装 --
    sample = [{
        "Ecms": Ecms_value
    }]
  
    # -- Selection组装 --
    resonances = []
    for res in ConstrainedResonanceList:
        resonances.append(res)
    kinematic_fits = [{
        "Constrained_Resonance": resonances,
        "MissTrack": MissTrack if MissTrack is not None else "",
        "Method": Method
    }]
    
  
    selection = {
        "KinematicFit": kinematic_fits,
        "SaveType": SaveType
    }

    # ====== JSON生成 ======
    draw_card = {
        "MetaData": metaData,
        "Sample": sample,
        "Selection": selection
    }
    
    output = json.dumps(draw_card, ensure_ascii=False, indent=4)
    output = "```json\n"+output+"\n```"

    return output

@str_utils.print_args
def create_JobOptionsCard(
    # ======== MetaData 元数据 ========
    AlgorithmName: Annotated[str, "用于该实验或数据处理的算法名称，例如'PipiJpsiAnalysis'。该名称根据给定衰变链自主生成，具有唯一性"],
    DecayChain: Annotated[str, "描述衰变过程的字符串，格式为'母粒子 -> 子粒子 [中间态 -> 末态]'，例如'psi(4260) -> pi+ pi- [J/psi -> mu+ mu-]'"],
    #CreationDate: Annotated[str, "JSON文件的创建日期，格式为'YYYY-MM-DD'，例如'2024-12-17'"],
    #Author: Annotated[str, "创建该JSON文件的作者姓名，例如'John Doe'"],
    #Reference: Annotated[List[str], "相关参考文献的链接或引用信息列表，例如arXiv或DOI链接，如['https://arxiv.org/abs/1234.5678', 'doi:10.1234/abcde']"],
    # ======== DecayCard 衰变卡 ========
    Decay_type: Annotated[Literal["specific", "inclusive"], "衰变类型。'specific'表示仅考虑给定衰变链的末态，'inclusive'表示考虑衰变链中所有中间共振态。"],
    DecayCard_Path: Annotated[str, "衰变卡配置文件的路径，该文件指定衰变过程和相关设置"],
    Run_Id: Annotated[str, "run编号，即实验数据的唯一标识符，用于确保能够准确读取刻度文件。通常情况下，它是一个具体的数字；但在某些情况下，它也可能是一个区间，例如'36398-36588'"], # <-起始run号,0,-终止run号> 负run号表示模拟
    # ======== sim 模拟参数 ========
    Energy: Annotated[float, "模拟时质心系的能量值（GeV），例如3.097"],
    Threshold_Cut: Annotated[float, "系统通过辐射出一个或多个ISR光子所能达到的最低质心系能量阈值（GeV），例如2.0"] = 0.1,
    # 共振态参数分解
    is_res: Annotated[Literal["jpsi", "psip", "psipp", "xyz"], "模拟的共振态类型。'jpsi'代表J/ψ（3.097 GeV），'psip'代表ψ(2S)（3.686 GeV），'psipp'代表ψ(3770)（3.773 GeV），'xyz'代表XYZ奇特态粒子（E > 4 GeV）"] = "xyz",
    Radiative_Correction: Annotated[bool, "是否在模拟中应用辐射修正，以考虑光子发射的影响"] = True,
    Tag_FSR: Annotated[int, "是否在模拟中标记末态辐射（FSR）光子"] = True,
    Log_Level: Annotated[Literal[2,3,4,5,6], "日志文件的详细程度，数值越大输出越简洁。（2=DEBUG，3=INFO，4=WARNING，5=ERROR，6=FATAL）"] = 2,
    # ======== rec 重建参数 ========
    Rec_Type: Annotated[Literal["Dst", "Rec"], "重建数据的存储结构类型。'Dst'仅包含径迹级信息，'Rec'包含径迹和击中级信息"] = "Dst",
    # ======== 有默认值的可选参数 ========
    Opt_ISR: Annotated[Optional[float], "初态辐射（ISR）设置（可选），未定义时使用默认行为"] = None,
    Event_Num: Annotated[int, "需要生成/模拟/重建/分析的事例数量，默认值为10"] = 10,
    # ======== 新增参数 ========
    Data_Path: Annotated[Optional[str], "实验数据文件的路径"] = None,
    Inmc_Path: Annotated[Optional[str], "inclusive蒙特卡洛模拟数据文件的路径"] = None,
    submit_exmc: Annotated[bool, "是否提交exmc/exclusive蒙特卡洛模拟作业"] = False,
) -> str:
    """A specialized tool for generating joboption scripts/cards tailored to the BESIII high-energy physics experiment. 
    PS: BOSS作业控制脚本是利用BESIII实验离线软件框架进行数据分析的参数设置文件，用户将需求按格式写入这些脚本，再利用BOSS程序运行，可以产生对应的探测器模拟信号，track(径迹)或cluster(光子簇团)级别的物理信息，以及用户联合多探测器信息鉴别得到的粒子以及他们组成的中间态粒子的物理信息。"""
    ## 可以通过计算得到的参数
    Random_Seed = random.randint(1, 99999)
    rec_Random_Seed = random.randint(1, 99999)
    Energy_Spread = calculate_BeamEnergySpread(Energy, 5)
    Log_Level = 5
    try:
        my_particle_list = get_particles_from_decay_chain(DecayChain)
        charged_children, neutral_children, intermediate_states = get_final_state(my_particle_list)
    except Exception as e:  # 捕获异常对象 e
        print("Error: Decay chain is not valid. Error message:", e)
    
    # ====== 时间戳生成 ======
    from datetime import datetime
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # ====== 处理 Run_Id 格式 ======
    def extract_first_number(run_id: str) -> int:
        """
        提取 Run_Id 中的第一个数字。兼容单个数字和区间两种情况。
        """
        if "-" in run_id:
            # 区间情况，如 '36398-36588'
            numbers = run_id.split("-")
            first_number = numbers[0]
        else:
            # 单个数字情况
            first_number = run_id

        return int(first_number)
    Run_Id = extract_first_number(Run_Id)
    
    # ====== 衰变卡选项设置 ======
    if is_res in ["jpsi", "psip", "psipp"]:
        Skim_Option = {
            "IsSkim": True,
            "Num_Tracks_Min": len(charged_children),
            "Num_Tracks_Max": len(charged_children) + 1
        }
    else:
        Skim_Option = {}

    # ====== 数据结构组装 ======
    config = {
        "MetaData": {
            "AlgorithmName": AlgorithmName_share or AlgorithmName,
            "DecayChain": DecayChain,
            "Type": "joboption",
            # "CreationDate": CreationDate,
            # "Author": Author,
            # "Reference": Reference
        },
        "JobOptions": []
    }

    # ====== 根据是否提交data、inmc、exmc组装相应的配置 ======
    if Data_Path:
        config["JobOptions"].append({
            "Type": "data",
            "Alg_Option": {
                "IsSignalMC": False,
                "Ecms": Energy,
                "Other": None
            },
            "Data_ParentPath": Data_Path,
            "Skim_Option": Skim_Option,
            "Log_Level": Log_Level
        })
    if Inmc_Path:
        config["JobOptions"].append({
            "Type": "inmc",
            "Alg_Option": {
                "IsSignalMC": False,
                "Ecms": Energy,
                "Other": None
            },
            "Data_ParentPath": Inmc_Path,
            "Log_Level": Log_Level
        })
    if submit_exmc:
        config["JobOptions"].append({
            "Type": "exmc",
            "DecayCard": {
                "Opt_ISR": Opt_ISR,
                "Decay_type": Decay_type
            },
            "sim": {
                "Energy": Energy,
                "Energy_Spread": Energy_Spread,
                "Threshold_Cut": Threshold_Cut,
                "Resonance": {
                    "Is_Jpsi": is_res == "jpsi",
                    "Is_Psip": is_res == "psip",
                    "Is_Psipp": is_res == "psipp",
                    "Is_XYZ": is_res == "xyz"
                },
                "Radiative_Correction": Radiative_Correction,
                "Tag_FSR": Tag_FSR,
                "DecayCard_Path": DecayCard_Path,
                "Random_Seed": Random_Seed,
                "Run_Id": Run_Id,
                "Rtraw_Path": f"sim_{timestamp}.rtraw",
                "Log_Level": Log_Level,
                "Event_Num": Event_Num
            },
            "rec": {
                "Rec_Type": Rec_Type,
                "Random_Seed": rec_Random_Seed,
                "Rtraw_Path": f"sim_{timestamp}.rtraw",
                "Rec_Path": f"rec_{timestamp}.rec",
                "Log_Level": Log_Level,
                "Event_Num": -1
            },
            "ana": {
                "Alg_Option": {
                    "Ecms": Energy,
                },
                "Rec_Path": f"rec_{timestamp}.rec",
                "Root_Path": f"ana_{timestamp}.root",
                "Log_Level": Log_Level,
                "Event_Num": -1
            },
        })

    if config["JobOptions"]:
        output = json.dumps(config, ensure_ascii=False, indent=4)
        output = "```json\n"+output+"\n```"
    else:
        output = "You should specify at least one job option (data [path needed], inmc [path needed], or exmc)."

    return output

@str_utils.print_args
def create_FoMCard(
    dataFilePath: Annotated[str, "数据文件路径"],
    exmcFilePath: Annotated[str, "exmc数据文件路径"],
    variable: Annotated[List[Dict[str, Any]], "需要绘制的变量列表。每个变量的字典中包含'name'、'nBins'、'low'、'up'四个键值对，分别表示变量名称、分箱数量、下限值、上限值。后三者默认值均为-1，仅在用户的任务请求中明确指定时使用非默认值"] = [],
    #name: Annotated[List[str], "需要绘制的变量名称列表。若不指定，则绘制数据文件中的所有变量"],
    type: Annotated[Literal["fom"], "脚本类型，目前仅支持'fom'"] = "fom",
    treeName: Annotated[str, "数据文件中树的名称"] = "",
    # nBins: Annotated[List[Optional[int]], "直方图的分箱数量列表。若不指定，则默认为None，表示在绘制时自动进行分箱"] = None,
    # low: Annotated[List[Optional[float]], "变量绘制的下限值列表。若nBins为None，则该值将被自动设定"] = None,
    # up: Annotated[List[Optional[float]], "变量绘制的上限值列表。若nBins为None，则该值将被自动设定"] = None,
    cut: Annotated[Optional[str], "对数据的约束条件。该参数为可选项，用于筛选数据"] = None,
) -> str:
    """The tool to generate FoM scripts.
    PS: FoM脚本是基于C++语言和CERN ROOT语言编写的，用于计算物理量的Figure of Merit（FoM），通常用于评估实验数据的信噪比，并给出最佳优化条件。"""
    # ====== 变量列表组装 ======
    # 确保 nBins、low、up 有默认值
    # processed_variable = []
    # for i in range(len(name)):
    #     processed_var = {
    #         "name": name[i],
    #         "nBins": nBins[i] if nBins[i] is not None else -1,
    #         "low": low[i] if low[i] is not None else -1,
    #         "up": up[i] if up[i] is not None else -1,
    #     }
    #     processed_variable.append(processed_var)

    if not variable:
        return "You should specify at least one variable."
    
    # ====== 数据结构组装 ======
    config = {
        "type": type,
        "dataFilePath": dataFilePath,
        "exmcFilePath": exmcFilePath,
        "treeName": treeName,
        "variable": variable,
        "cut": cut if cut is not None else ""
    }

    output = json.dumps(config, ensure_ascii=False, indent=4)
    output = "```json\n"+output+"\n```"

    return output


TMVAMethod = Literal[
    "Cuts", "CutsD", "CutsPCA", "CutsGA", "CutsSA",
    "Likelihood", "LikelihoodD", "LikelihoodPCA", "LikelihoodKDE", "LikelihoodMIX",
    "PDERS", "PDERSD", "PDERSPCA", "PDEFoam", "PDEFoamBoost", "KNN",
    "LD", "Fisher", "FisherG", "BoostedFisher", "HMatrix",
    "FDA_GA", "FDA_SA", "FDA_MC", "FDA_MT", "FDA_GAMT", "FDA_MCMT",
    "MLP", "MLPBFGS", "MLPBNN", "CFMlpANN", "TMlpANN",
    "SVM",
    "BDT", "BDTG", "BDTB", "BDTD", "BDTF",
    "RuleFit"
]

@str_utils.print_args
def create_TMVACard(
    sig_path: Annotated[str, "信号MC样本文件路径"],
    bkg_path: Annotated[str, "背景样本文件路径"],
    output_path: Annotated[str, "输出文件名称，以.root 结尾"] = "TMVA.root",
    treename: Annotated[str, "ROOT文件中树的名称"] = "",
    method: Annotated[TMVAMethod, """
    TMVA 方法的选择，具体说明如下：
    - Cuts: 基于简单切割的分类方法。
    - CutsD: 基于去相关变量的切割方法。
    - CutsPCA: 基于 PCA 变换的切割方法。
    - CutsGA: 基于遗传算法的切割优化方法。
    - CutsSA: 基于模拟退火的切割优化方法。
    - Likelihood: 一维似然估计（朴素贝叶斯估计器）。
    - LikelihoodD: 基于去相关变量的似然估计。
    - LikelihoodPCA: 基于 PCA 变换的似然估计。
    - LikelihoodKDE: 基于核密度估计的似然方法。
    - LikelihoodMIX: 混合似然估计方法。
    - PDERS: 多维似然和最近邻方法。
    - PDERSD: 基于去相关变量的多维似然方法。
    - PDERSPCA: 基于 PCA 变换的多维似然方法。
    - PDEFoam: 基于 Foam 的多维似然方法。
    - PDEFoamBoost: 使用广义 MVA 方法增强的 Foam 方法。
    - KNN: K 最近邻方法。
    - LD: 线性判别分析（与 Fisher 方法相同）。
    - Fisher: Fisher 线性判别方法。
    - FisherG: 广义 Fisher 方法。
    - BoostedFisher: 使用广义 MVA 方法增强的 Fisher 方法。
    - HMatrix: 基于 HMatrix 的判别方法。
    - FDA_GA: 使用遗传算法优化用户定义函数的判别分析。
    - FDA_SA: 使用模拟退火优化用户定义函数的判别分析。
    - FDA_MC: 使用蒙特卡洛优化用户定义函数的判别分析。
    - FDA_MT: 使用多线程优化用户定义函数的判别分析。
    - FDA_GAMT: 使用遗传算法和多线程优化用户定义函数的判别分析。
    - FDA_MCMT: 使用蒙特卡洛和多线程优化用户定义函数的判别分析。
    - MLP: 推荐的多层感知器（ANN）。
    - MLPBFGS: 使用 BFGS 训练方法的多层感知器。
    - MLPBNN: 使用 BFGS 训练方法和贝叶斯正则化的多层感知器。
    - CFMlpANN: 来自 ALEPH 的已弃用 ANN。
    - TMlpANN: ROOT 自带的 ANN。
    - SVM: 支持向量机方法。
    - BDT: 使用自适应增强的决策树方法。
    - BDTG: 使用梯度增强的决策树方法。
    - BDTB: 使用 Bagging 的决策树方法。
    - BDTD: 基于去相关变量和自适应增强的决策树方法。
    - BDTF: 允许使用 Fisher 判别进行节点分割的决策树方法。
    - RuleFit: Friedman 的 RuleFit 方法，即一系列优化的切割规则。
    """] = "BDTG",
) -> str:
    """The tool to generate TMVA scripts."""
    # ====== 数据结构组装 ======
    config = {
        "type": "TMVA",
        "sig_path": sig_path,
        "bkg_path": bkg_path,
        "output_path": output_path,
        "treename": treename,
        "method": method
    }

    output = json.dumps(config, ensure_ascii=False, indent=4)
    output = "```json\n"+output+"\n```"

    return output
