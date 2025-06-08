# Tools to process the analysis algorithm
import re, sys, os, json
from typing import *
from dotmap import DotMap
import textwrap

from pathlib import Path
here = Path(__file__).parent

STABLE_PARTICLES = ["e+", "e-", "mu+", "mu-", "pi+", "pi-", "K+", "K-", "p+", "anti-p-", "gamma"]
STABLE_PARTICLES_EX = ["pi0", "eta", "K_S0", "Lambda0", "anti-Lambda0"] ## TODO: 考虑Ks, Lambda(bar)的特殊性，拿到的track信息是错误的

RECVARS_CHARGED_PARTICLES = {
    "Charge": 1, # 电荷量
    "Emc": 1, # EMC沉积能量
    "Depth": 1, # MUC击中深度
    "P4": 4, # 4-momentum
    #"p4_KF": 4, # 运动学拟合的4-momentum
}
RECVARS_NEUTRAL_PARTICLES = {
    "P4": 4, # 4-momentum
}
RECVARS_INTERMEDIATE_STATES = {
    "Mass": 1, # mass
}

class Particle:
    def __init__(self, name: str, mother=None, children=None, id: int=0):
        
        # Decay chain variables
        self.name = name
        self.mother = mother
        self.children = children if children is not None else []
        self.id = id
        self.is_reconstructed = True if name in STABLE_PARTICLES else False
        
        # PDG variables
        is_find = self.get_particle_by_name(name)
        if not is_find:
            raise ValueError(f"Particle {name} not found in database")


    def load_database(self) -> json:
        # Load particle database
        with open(f"{here}/Particle_bes3.json", "r") as f:
            particle_database = json.load(f)
        return particle_database
        
    def get_particle_by_name(self, name: str) -> bool:
        dt = self.load_database()

        if name in dt.keys():
            self.mass = dt[name]['mass'] / 1000 # MeV/c^2 -> GeV/c^2
            self.mass_err = dt[name]['mass_error'] / 1000
            self.width = dt[name]['width'] / 1000 # MeV -> GeV
            self.width_err = dt[name]['width_error'] / 1000
            self.long_lifetime = dt[name]['long_lifetime'] # bool

            self.mcid = dt[name]['mcid']
            self.charge = dt[name]['charge']
            self.quantum_C = dt[name]['quantum_C']
            self.quantum_G = dt[name]['quantum_G']
            self.quantum_I = dt[name]['quantum_I']
            self.quantum_J = dt[name]['quantum_J']
            self.quantum_P = dt[name]['quantum_P']

            self.programmatic_name = dt[name]['programmatic_name']
            self.latex_name = dt[name]['latex_name']
            self.evtgen_name = dt[name]['evtgen_name']

            return True
        else:
            return False
        
class CustomDotMap(DotMap):
    def __getattr__(self, key):
        # 如果属性不存在，返回 None
        if key not in self:
            return None
        return super().__getattr__(key)

#######################################################################################################
## 字符串处理
def replace_keyword(string, old_key, new_key) -> str:
    if old_key in string:
        return string.replace(old_key, new_key)
    return string

def extract_elements(decay_chain) -> Tuple[str, List[str], List[str]]:
    """
    提取衰变链中所有元素，其中将中括号看做一个整体
    Input: R -> [A -> B C] D
    Output: 'R', ['A -> B C'], ['D']
    """
    mother_particle = ""
    intermediate_states = []
    stable_particles = []

    ## 处理衰变链的开头，提取母粒子
    split_parts = decay_chain.split(" -> ", 1)
    mother_particle = split_parts[0]
    daughter_particles = split_parts[1]

    stack = []
    start_index = 0
    non_res = ""
    in_bracket = False
    
    ## 遍历字符串，将中括号内的元素提取出来
    for index, char in enumerate(daughter_particles):
        if not in_bracket and char not in "[]":
            non_res += char
        
        if char == '[':
            stack.append(index)
            if not in_bracket:
                start_index = index
                in_bracket = True
        elif char == ']':
            if stack:
                stack.pop()
                if not stack:
                    content = daughter_particles[start_index:index + 1]
                    intermediate_states.append(content[1:-1]) # 去掉中括号
                    start_index = index + 1
                    in_bracket = False
            else:
                raise ValueError("括号不匹配")
    
    ## 处理非中括号内的元素
    stable_particles = re.findall(r'(\S+)', non_res)

    return mother_particle, intermediate_states, stable_particles

def handle_indentation(string: str, num_spaces: int = 4) -> str:
    """
    处理缩进，使每行代码缩进相同
    """
    string = textwrap.dedent(string)
    string = textwrap.indent(string, " " * num_spaces)
    return string

#######################################################################################################
## 粒子处理
def get_particles_from_decay_chain(decay_chain: str, particle_list: List = None, mother_particle: Particle = None) -> List[Particle]:
    """
    提取衰变链中的所有粒子，生成Particle对象，并返回Particle列表
    Input: R -> [A -> B C] D
    Output: ['R', 'D', 'A', 'B', 'C']
    """
    if particle_list is None:
        particle_list = []

    mother_particle_tmp, intermediate_states, stable_particles = extract_elements(decay_chain)
    
    idx = len(particle_list)
    mother = Particle(name=mother_particle_tmp, mother=mother_particle, children=[], id=idx)
    particle_list.append(mother)

    if mother_particle is not None:
        mother_particle.children.append(mother)

    for index, state in enumerate(stable_particles):
        idx = idx + 1
        stable_particle = Particle(name=state, mother=mother, children=[], id=idx)
        mother.children.append(stable_particle)
        particle_list.append(stable_particle)
    
    for index, chain in enumerate(intermediate_states):
        idx = idx + 1
        particle_list = get_particles_from_decay_chain(chain, particle_list, mother_particle=mother)

    return particle_list

def get_final_state(particle_list: List) -> Tuple[List, List]:
    """
    分类三种末态粒子：带电粒子、中性粒子、中间态(包含顶端的母粒子)
    同时按照稳定粒子、中间态的顺序更新粒子id。母粒子的id不更新，始终为0
    """
    charged_children = []
    neutral_children = []
    intermediate_states = []

    for particle in particle_list:
        if particle.name in STABLE_PARTICLES or particle.name in STABLE_PARTICLES_EX: # STABLE_PARTICLES_EX当成稳定粒子处理
            if "+" in particle.name or "-" in particle.name:
                charged_children.append(particle)
            else:
                neutral_children.append(particle)
        else:
            intermediate_states.append(particle)
    
    ## 添加先验的粒子id
    index = 0
    for particle in charged_children + neutral_children:
        index += 1
        particle.id = index
    for particle in intermediate_states[1:]: # 不更新root_particle的id
        index += 1
        particle.id = index

    return charged_children, neutral_children, intermediate_states

def get_final_state_VarNames(charged_particle_list: List[Particle], neutral_particle_list: List[Particle], intermediate_state_list: List[Particle]) -> Tuple[List, List, List]:
    """
    生成末态粒子的变量名，以粒子名+编号的方式命名
    """
    charged_final_state_VarNames = [get_VarName(particle) for particle in charged_particle_list]
    neutral_final_state_VarNames = [get_VarName(particle) for particle in neutral_particle_list]
    intermediate_state_VarNames = [get_VarName(particle) for particle in intermediate_state_list]
    
    return charged_final_state_VarNames, neutral_final_state_VarNames, intermediate_state_VarNames

def get_particle_from_VarName(particle_list: List, VarName: str) -> Particle:
    """
    根据名字获取Particle对象
    """
    assert "_" in VarName, "Error: Invalid particle name -- an example name = {particleName}_{id}"
    particle_id = int(VarName.split("_")[-1])

    for particle in particle_list:
        if particle.id == particle_id:
            return particle
    return None

def get_nGood_from_particle_list(charged_particle_list: List[Particle]) -> Tuple[int, int]:
    """
    对正负好径迹数进行计数
    """
    npGood = 0 #带正电的好径迹数
    nmGood = 0 #带负电的好径迹数
    
    for i, particle in enumerate(charged_particle_list):
        if particle.name in STABLE_PARTICLES and particle.mother.name not in STABLE_PARTICLES_EX:
            charge = int(particle.charge)
            if charge > 0:
                npGood += 1
            elif charge < 0:
                nmGood += 1
    return npGood, nmGood

def count_final_particles(particle_list: List) -> List[int]:
    """
    统计列表中各个末态粒子的数量
    """
    num_ep = 0
    num_em = 0
    num_mup = 0
    num_mum = 0
    num_pip = 0
    num_pim = 0
    num_Kp = 0
    num_Km = 0
    num_p = 0
    num_pbar = 0
    num_K_S0 = 0
    num_pi0 = 0
    num_eta = 0
    num_Lam = 0
    num_Lamb = 0

    for particle in particle_list:
        if particle.name == "e+":
            num_ep += 1
        elif particle.name == "e-":
            num_em += 1
        elif particle.name == "mu+":
            num_mup += 1
        elif particle.name == "mu-":
            num_mum += 1
        elif particle.name == "pi+":
            num_pip += 1
        elif particle.name == "pi-":
            num_pim += 1
        elif particle.name == "K+":
            num_Kp += 1
        elif particle.name == "K-":
            num_Km += 1
        elif particle.name == "p+":
            num_p += 1
        elif particle.name == "anti-p-":
            num_pbar += 1
        elif particle.name == "K_S0":
            num_K_S0 += 1
        elif particle.name == "pi0":
            num_pi0 += 1
        elif particle.name == "eta":
            num_eta += 1
        elif particle.name == "Lambda0":
            num_Lam += 1
        elif particle.name == "anti-Lambda0":
            num_Lamb += 1

    return [num_ep, num_em, num_mup, num_mum, num_pip, num_pim, num_Kp, num_Km, num_p, num_pbar, num_K_S0, num_pi0, num_eta, num_Lam, num_Lamb]

def get_final_particles(particle: Particle) -> List[Particle]:
    """
    获取粒子的末态粒子，如果没有末态粒子，则返回自身
    """
    stable_particles = []

    if not particle.children:
        return [particle]
    else:
        for particle in particle.children:
            stable_particles.extend(get_final_particles(particle))
            
    return stable_particles

#######################################################################################################
## 粒子名称处理
def get_CleanName(particle: Particle) -> str:
    """清理粒子名称，去除特殊字符。 -- 输出应为纯字母+数字的字符串"""
    name = particle.name
    if re.match(r"^[a-zA-Z0-9]+$", name):
        pass
    else:
        programmatic_name = particle.programmatic_name
        name = programmatic_name.split("_")[0]

    return name

def get_VarName(particle: Particle) -> str:
    """将粒子名称转换为变量名。"""
    VarName = ""

    stable_particles = get_final_particles(particle)
    if len(stable_particles) == 1:
        VarName = f"{particle.programmatic_name}_{particle.id}"
    else:
        for state in stable_particles:
            VarName += f"{get_CleanName(state)}"
        VarName += f"_{particle.id}"

    return VarName

# def to_OriginalName(VarName: str) -> str:
#     """将变量名转换为粒子名称。"""
#     id = VarName.split("_")[-1]
#     OriginalName = VarName.replace("_plus", "+").replace("_minus", "-")
#     return OriginalName

def get_particle_from_name(name: str) -> Particle:
    """根据名称获取Particle对象。"""
    return Particle(name=name, mother=None, children=None, id=-999)


#####################################################################################################
## 生成变量定义及条件字符串
def generate_VarDefinitions_in_tuple(charged_VarNames, neutral_VarNames, intermediate_state_VarNames, data: DotMap) -> Tuple[str, str, str, str]:
    """
    生成元组中各个变量的定义，用于保存事例信息
    分为MC truth变量和重建变量两部分
    源文件定义和头文件定义分别保存

    参数:
    - charged_VarNames (list): 带电粒子的变量名列表
    - neutral_VarNames (list): 中性粒子的变量名列表
    - intermediate_state_VarNames (list): 中间态粒子的变量名列表

    返回:
    - 源文件中MC truth变量 (str)
    - 源文件中重建变量 (str)
    - 头文件中MC truth变量 (str)
    - 头文件重建变量 (str)
    """
    line_truth_cxx = ""
    line_rec_cxx = ""
    line_truth_h = ""
    line_rec_h = ""
    
    fit_methods = data.Selection.KinematicFit
    if fit_methods:
        method = data.Selection.KinematicFit.Method.lower()

    ## Truth-level variables
    stable_VarNames = charged_VarNames + neutral_VarNames
    for i, name in enumerate(stable_VarNames):
        line_truth_cxx += f'status = m_tuple_truth->addItem ("{name}_p4_truth", 4, m_{name}_p4_truth);\n'
        line_truth_h += f"NTuple::Array<double>  m_{name}_p4_truth;\n"

    ## Reconstructed variables
    for i, name in enumerate(charged_VarNames):
        for varName, varLength in RECVARS_CHARGED_PARTICLES.items():
            combined_name = f"{name}_{varName}"
            varLength_tmp = str(varLength) + "," if varLength != 1 else ""
            line_rec_cxx += f'status = m_tuple_reco->addItem ("{combined_name}", {varLength_tmp} m_{combined_name});\n'
            
            if varLength == 1:
                line_rec_h += f"NTuple::Item<double>  m_{combined_name};\n"
            else:
                line_rec_h += f"NTuple::Array<double> m_{combined_name};\n"
            
        if method == "km_fit":
            line_rec_h += f"NTuple::Array<double> m_{name}_P4_KF;\n"
            line_rec_cxx += f'status = m_tuple_reco->addItem ("{name}_P4_KF", 4, m_{name}_P4_KF);\n'
    
    for i, name in enumerate(neutral_VarNames):
        for varName, varLength in RECVARS_NEUTRAL_PARTICLES.items():
            combined_name = f"{name}_{varName}"
            varLength_tmp = str(varLength) + "," if varLength != 1 else ""
            line_rec_cxx += f'status = m_tuple_reco->addItem ("{combined_name}", {varLength_tmp} m_{combined_name});\n'
            
            if varLength == 1:
                line_rec_h += f"NTuple::Item<double>  m_{combined_name};\n"
            else:
                line_rec_h += f"NTuple::Array<double> m_{combined_name};\n"
            
        if method == "km_fit":
            line_rec_h += f"NTuple::Array<double> m_{name}_P4_KF;\n"
            line_rec_cxx += f'status = m_tuple_reco->addItem ("{name}_P4_KF", 4, m_{name}_P4_KF);\n'

    for i, name in enumerate(intermediate_state_VarNames[1:]):
        for varName, varLength in RECVARS_INTERMEDIATE_STATES.items():
            combined_name = f"{name}_{varName}"
            varLength_tmp = str(varLength) + "," if varLength != 1 else ""
            line_rec_cxx += f'status = m_tuple_reco->addItem ("{combined_name}", {varLength_tmp} m_{combined_name});\n'
            
            if varLength == 1:
                line_rec_h += f"NTuple::Item<double>  m_{combined_name};\n"
            else:
                line_rec_h += f"NTuple::Array<double> m_{combined_name};\n"
            
        # if method == "km_fit":
        #     line_rec_h += f"NTuple::Array<double> m_{name}_P4_KF;\n"
        #     line_rec_cxx += f'status = m_tuple_reco->addItem ("{name}_P4_KF", 4, m_{name}_P4_KF);\n'

    line_truth_cxx = "\n" + handle_indentation(line_truth_cxx, 12)
    line_rec_cxx = "\n" + handle_indentation(line_rec_cxx, 12)
    line_truth_h = "\n" + handle_indentation(line_truth_h, 8)
    line_rec_h = "\n" + handle_indentation(line_rec_h, 8)

    return line_truth_cxx, line_rec_cxx, line_truth_h, line_rec_h

def generate_TruthSaveInfo_in_execute(particle_list: List[Particle], charged_VarNames: List[str], neutral_VarNames: List[str]) -> str:
    """
    生成execute()函数中保存MC truth信息的代码
    """
    line_truth_save = ""
    stable_VarNames = charged_VarNames + neutral_VarNames
    
    for i, name in enumerate(stable_VarNames):
        particle = get_particle_from_VarName(particle_list, name)
        
        nested_condition = generate_nested_condition(particle)
        line_truth_save += f"""
            if ({nested_condition}) {{
                HepLorentzVector p4_tmp = (*iter_mc)->initialFourMomentum();
                m_{name}_p4_truth[0] = p4_tmp.px();
                m_{name}_p4_truth[1] = p4_tmp.py();
                m_{name}_p4_truth[2] = p4_tmp.pz();
                m_{name}_p4_truth[3] = p4_tmp.e();
            }}
        """
    
    line_truth_save = handle_indentation(line_truth_save, 12)
    return line_truth_save

def generate_nested_condition(particle) -> str:
    """
    生成嵌套的条件语句，循环检查其母粒子mcid以精确定位目标粒子
    """
    condition = f"(*iter_mc)->particleProperty()=={particle.mcid} && "
    current_particle = particle.mother
    mother_count = 0
    while current_particle is not None:
        # 构建嵌套的母粒子条件
        condition += f"((*iter_mc)->mother())" + "".join([".mother()" for _ in range(mother_count)]) + f".particleProperty()=={current_particle.mcid} && "
        current_particle = current_particle.mother
        mother_count += 1
    return condition[:-4]  # 去除最后多余的 " && "

def generate_PID_condition(particle_list: List[Particle]) -> str:
    """
    根据decay_chain中的稳定末态粒子，生成相应的粒子鉴别C++代码块
    每个稳定末态粒子的信息均保存到以VarName命名的对应的C++变量中，方便后续调用
    """
    code_block = ""
    stable_particle_list = []
    for particle in particle_list:
        if particle.name in STABLE_PARTICLES or particle.name in STABLE_PARTICLES_EX:
            stable_particle_list.append(particle)

    num_list = count_final_particles(particle_list)

    ## 变量定义
    for particle in stable_particle_list:
        code_block += particle_identification(particle, 10, num_list)

    code_block = handle_indentation(code_block, 4)
    return code_block

def particle_identification(particle: Particle, max_num: int, num_list: List, mass_ll: float=None, mass_ul: float=None) -> str:
    """
    生成选择稳定粒子e, mu, pi, K, p以及固定重建模式的粒子Ks, gamma, pi0, eta的C++代码块
    """
    particle_name = get_VarName(particle)
    code_block = f"""
            Vtrack2 Trk_{particle_name};     Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name};    Trkp_{particle_name}.clear();
            Vint2   Id_{particle_name};      Id_{particle_name}.clear();
    """

    def generate_particle_count_condition(particle_name, num_value) -> str:
        condition = "==" if num_value == 0 else "<"
        return f"    if (Number_{particle_name} {condition} {num_value}) return StatusCode::SUCCESS;\n"

    if particle.name == "e+" or particle.name == "e-":
        code_block += f"""
            Vint   Charge_{particle_name};  Charge_{particle_name}.clear();
            Vdou   Emc_{particle_name};     Emc_{particle_name}.clear();
            Vdou   Depth_{particle_name};   Depth_{particle_name}.clear();
            Vp4    P4_{particle_name};      P4_{particle_name}.clear();
            for (int i=0; i<nGood; i++) {{
                EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + iGood[i];
                if(!(*itTrk)->isMdcKalTrackValid()) continue;
                RecMdcKalTrack *mdcKalTrk = (*itTrk)->mdcKalTrack();
                int charge = mdcKalTrk->charge();
                if ( charge != {int(particle.charge)} ) continue;

                WTrackParameter wtrkp_tmp(mass[0],mdcKalTrk->getZHelixE(),mdcKalTrk->getZErrorE());
                HepVector tmp_val = HepVector(7,0);
                tmp_val = wtrkp_tmp.w();
                HepLorentzVector P_tmp(tmp_val[0],tmp_val[1],tmp_val[2],tmp_val[3]);
                P_tmp.boost(-0.011,0,0);

                double emc = 0;
                double dpt = 0;
                if((*itTrk)->isEmcShowerValid()) {{
                    RecEmcShower *emcTrk = (*itTrk)->emcShower();
                    emc = emcTrk->energy();
                    double eop = Eop[i];
                    if(eop < 0.8 || eop > 1.2) continue;
                }}
                if ((*itTrk)->isMucTrackValid()){{
                    RecMucTrack* mucTrk = (*itTrk)->mucTrack();
                    dpt = mucTrk->depth();
                }}

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wtrkp_tmp);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);

                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}.push_back(wtrkp_tmp.p());
                Id_{particle_name}.push_back(tmp_id);
                Charge_{particle_name}.push_back(charge);
                Emc_{particle_name}.push_back(emc);
                Depth_{particle_name}.push_back(dpt);
                P4_{particle_name}.push_back(P_tmp);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        if particle.name == "e+":
            code_block += generate_particle_count_condition(particle_name, num_list[0])
        elif particle.name == "e-":
            code_block += generate_particle_count_condition(particle_name, num_list[1])
    elif particle.name == "mu+" or particle.name == "mu-":
        code_block += f"""
            Vint   Charge_{particle_name};  Charge_{particle_name}.clear();
            Vdou   Emc_{particle_name};     Emc_{particle_name}.clear();
            Vdou   Depth_{particle_name};   Depth_{particle_name}.clear();
            Vp4    P4_{particle_name};      P4_{particle_name}.clear();
            for (int i=0; i<nGood; i++) {{
                EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + iGood[i];
                if(!(*itTrk)->isMdcKalTrackValid()) continue;
                RecMdcKalTrack *mdcKalTrk = (*itTrk)->mdcKalTrack();
                int charge = mdcKalTrk->charge();
                if ( charge != {int(particle.charge)} ) continue;

                WTrackParameter wtrkp_tmp(mass[1],mdcKalTrk->getZHelixMu(),mdcKalTrk->getZErrorMu());
                HepVector tmp_val = HepVector(7,0);
                tmp_val = wtrkp_tmp.w();
                HepLorentzVector P_tmp(tmp_val[0],tmp_val[1],tmp_val[2],tmp_val[3]);
                P_tmp.boost(-0.011,0,0);

                double emc = 0;
                double dpt = 0;
                if((*itTrk)->isEmcShowerValid()) {{
                    RecEmcShower *emcTrk = (*itTrk)->emcShower();
                    emc = emcTrk->energy();
                    if(emc < 0.15 || emc > 0.23) continue; // ref. to BAM-00925 [https://docbes3.ihep.ac.cn/DocDB/0014/001475/005/memo_V4.pdf]
                }}
                if ((*itTrk)->isMucTrackValid()){{
                    RecMucTrack* mucTrk = (*itTrk)->mucTrack();
                    if( mucTrk->numHits()<3 ) continue; // ref. to BAM-00925 [https://docbes3.ihep.ac.cn/DocDB/0014/001475/005/memo_V4.pdf]
                    double mom_mu = P_tmp.rho();
                    dpt = mucTrk->depth();
                    if( (mom_mu>0.6 && mom_mu<1.1) && dpt < (68.*mom_mu-37.4) ) continue; // ref. to BAM-00925 [https://docbes3.ihep.ac.cn/DocDB/0014/001475/005/memo_V4.pdf]
                    if( mom_mu>1.1 && dpt < 42.0 ) continue; // ref. to BAM-00925 [https://docbes3.ihep.ac.cn/DocDB/0014/001475/005/memo_V4.pdf]
                }}

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wtrkp_tmp);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);

                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}.push_back(wtrkp_tmp.p());
                Id_{particle_name}.push_back(tmp_id);
                Charge_{particle_name}.push_back(charge);
                Emc_{particle_name}.push_back(emc);
                Depth_{particle_name}.push_back(dpt);
                P4_{particle_name}.push_back(P_tmp);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        if particle.name == "mu+":
            code_block += generate_particle_count_condition(particle_name, num_list[2])
        elif particle.name == "mu-":
            code_block += generate_particle_count_condition(particle_name, num_list[3])
    elif particle.name == "pi+" or particle.name == "pi-":
        code_block += f"""
            Vint   Charge_{particle_name};  Charge_{particle_name}.clear();
            Vdou   Emc_{particle_name};     Emc_{particle_name}.clear();
            Vdou   Depth_{particle_name};   Depth_{particle_name}.clear();
            Vp4    P4_{particle_name};      P4_{particle_name}.clear();
            for (int i=0; i<nGood; i++) {{
                EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + iGood[i];
                if(!(*itTrk)->isMdcKalTrackValid()) continue;
                RecMdcKalTrack *mdcKalTrk = (*itTrk)->mdcKalTrack();
                int charge = mdcKalTrk->charge();
                if ( charge != {int(particle.charge)} ) continue;

                // PID
                pid->init();
                pid->setMethod(pid->methodProbability());
                pid->setChiMinCut(4);
                pid->setRecTrack(*itTrk);
                pid->usePidSys(pid->useDedx() | pid->useTof1() | pid->useTof2() | pid->useTofE()); // use PID sub-system
                pid->identify(pid->onlyPion() | pid->onlyKaon() | pid->onlyProton()); // seperater Pion/Kaon/Proton
                pid->calculate();
                if (!( pid->probPion()>0.001 && pid->probPion()>pid->probKaon() && pid->probPion()>pid->probProton() )) continue;

                WTrackParameter wtrkp_tmp(mass[2],mdcKalTrk->getZHelix(),mdcKalTrk->getZError());
                HepVector tmp_val = HepVector(7,0);
                tmp_val = wtrkp_tmp.w();
                HepLorentzVector P_tmp(tmp_val[0],tmp_val[1],tmp_val[2],tmp_val[3]);
                P_tmp.boost(-0.011,0,0);

                double emc = 0;
                double dpt = 0;
                if((*itTrk)->isEmcShowerValid()) {{
                    RecEmcShower *emcTrk = (*itTrk)->emcShower();
                    emc = emcTrk->energy();
                }}
                if ((*itTrk)->isMucTrackValid()){{
                    RecMucTrack* mucTrk = (*itTrk)->mucTrack();
                    dpt = mucTrk->depth();
                }}

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wtrkp_tmp);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);

                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}.push_back(wtrkp_tmp.p());
                Id_{particle_name}.push_back(tmp_id);
                Charge_{particle_name}.push_back(charge);
                Emc_{particle_name}.push_back(emc);
                Depth_{particle_name}.push_back(dpt);
                P4_{particle_name}.push_back(P_tmp);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        if particle.name == "pi+":
            code_block += generate_particle_count_condition(particle_name, num_list[4])
        elif particle.name == "pi-":
            code_block += generate_particle_count_condition(particle_name, num_list[5])
    elif particle.name == "K+" or particle.name == "K-":
        code_block += f"""
            Vint   Charge_{particle_name};  Charge_{particle_name}.clear();
            Vdou   Emc_{particle_name};     Emc_{particle_name}.clear();
            Vdou   Depth_{particle_name};   Depth_{particle_name}.clear();
            Vp4    P4_{particle_name};      P4_{particle_name}.clear();
            for (int i=0; i<nGood; i++) {{
                EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + iGood[i];
                if(!(*itTrk)->isMdcKalTrackValid()) continue;
                RecMdcKalTrack *mdcKalTrk = (*itTrk)->mdcKalTrack();
                int charge = mdcKalTrk->charge();
                if ( charge != {int(particle.charge)} ) continue;

                // PID
                pid->init();
                pid->setMethod(pid->methodProbability());
                pid->setChiMinCut(4);
                pid->setRecTrack(*itTrk);
                pid->usePidSys(pid->useDedx() | pid->useTof1() | pid->useTof2() | pid->useTofE()); // use PID sub-system
                pid->identify(pid->onlyPion() | pid->onlyKaon() | pid->onlyProton()); // seperater Pion/Kaon/Proton
                pid->calculate();
                if (!( pid->probKaon()>0.001 && pid->probKaon()>pid->probPion() && pid->probKaon()>pid->probProton() )) continue;

                WTrackParameter wtrkp_tmp(mass[3],mdcKalTrk->getZHelixK(),mdcKalTrk->getZErrorK());
                HepVector tmp_val = HepVector(7,0);
                tmp_val = wtrkp_tmp.w();
                HepLorentzVector P_tmp(tmp_val[0],tmp_val[1],tmp_val[2],tmp_val[3]);
                P_tmp.boost(-0.011,0,0);

                double emc = 0;
                double dpt = 0;
                if((*itTrk)->isEmcShowerValid()) {{
                    RecEmcShower *emcTrk = (*itTrk)->emcShower();
                    emc = emcTrk->energy();
                }}
                if ((*itTrk)->isMucTrackValid()){{
                    RecMucTrack* mucTrk = (*itTrk)->mucTrack();
                    dpt = mucTrk->depth();
                }}

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wtrkp_tmp);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);

                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}.push_back(wtrkp_tmp.p());
                Id_{particle_name}.push_back(tmp_id);
                Charge_{particle_name}.push_back(charge);
                Emc_{particle_name}.push_back(emc);
                Depth_{particle_name}.push_back(dpt);
                P4_{particle_name}.push_back(P_tmp);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        if particle.name == "K+":
            code_block += generate_particle_count_condition(particle_name, num_list[6])
        elif particle.name == "K-":
            code_block += generate_particle_count_condition(particle_name, num_list[7])
    elif particle.name == "p+" or particle.name == "anti-p-":
        code_block += f"""
            Vint   Charge_{particle_name};  Charge_{particle_name}.clear();
            Vdou   Emc_{particle_name};     Emc_{particle_name}.clear();
            Vdou   Depth_{particle_name};   Depth_{particle_name}.clear();
            Vp4    P4_{particle_name};      P4_{particle_name}.clear();
            for (int i=0; i<nGood; i++) {{
                EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + iGood[i];
                if(!(*itTrk)->isMdcKalTrackValid()) continue;
                RecMdcKalTrack *mdcKalTrk = (*itTrk)->mdcKalTrack();
                int charge = mdcKalTrk->charge();
                if ( charge != {int(particle.charge)} ) continue;

                // PID
                pid->init();
                pid->setMethod(pid->methodProbability());
                pid->setChiMinCut(4);
                pid->setRecTrack(*itTrk);
                pid->usePidSys(pid->useDedx() | pid->useTof1() | pid->useTof2() | pid->useTofE()); // use PID sub-system
                pid->identify(pid->onlyPion() | pid->onlyKaon() | pid->onlyProton()); // seperater Pion/Kaon/Proton
                pid->calculate();
                if (!( pid->probProton()>0.001 && pid->probProton()>pid->probPion() && pid->probProton()>pid->probKaon() )) continue;

                WTrackParameter wtrkp_tmp(mass[4],mdcKalTrk->getZHelixP(),mdcKalTrk->getZErrorP());
                HepVector tmp_val = HepVector(7,0);
                tmp_val = wtrkp_tmp.w();
                HepLorentzVector P_tmp(tmp_val[0],tmp_val[1],tmp_val[2],tmp_val[3]);
                P_tmp.boost(-0.011,0,0);

                double emc = 0;
                double dpt = 0;
                if((*itTrk)->isEmcShowerValid()) {{
                    RecEmcShower *emcTrk = (*itTrk)->emcShower();
                    emc = emcTrk->energy();
                }}
                if ((*itTrk)->isMucTrackValid()){{
                    RecMucTrack* mucTrk = (*itTrk)->mucTrack();
                    dpt = mucTrk->depth();
                }}

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wtrkp_tmp);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);

                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}.push_back(wtrkp_tmp.p());
                Id_{particle_name}.push_back(tmp_id);
                Charge_{particle_name}.push_back(charge);
                Emc_{particle_name}.push_back(emc);
                Depth_{particle_name}.push_back(dpt);
                P4_{particle_name}.push_back(P_tmp);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        if particle.name == "p+":
            code_block += generate_particle_count_condition(particle_name, num_list[8])
        elif particle.name == "anti-p-":
            code_block += generate_particle_count_condition(particle_name, num_list[9])
    elif particle.name == "K_S0": # TODO: what is the valid name for particle K(S)0 in decay chain?
        if mass_ll is None and mass_ul is None:
            mass_ll = 0.487
            mass_ul = 0.511

        code_block = f"""
            Vtrack2 Trk_{particle_name};       Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name}_p1;   Trkp_{particle_name}_p1.clear();
            Vp4     Trkp_{particle_name}_p2;   Trkp_{particle_name}_p2.clear();
            Vint2   Id_{particle_name};        Id_{particle_name}.clear();
            Vdou    Chi2_{particle_name};      Chi2_{particle_name}.clear();
            Vdou    FlyLen_{particle_name};    FlyLen_{particle_name}.clear();
            Vdou    FlySig_{particle_name};    FlySig_{particle_name}.clear();
            Vp4     P4_{particle_name};        P4_{particle_name}.clear();
            Vp4     P4_{particle_name}_p1;     P4_{particle_name}_p1.clear();
            Vp4     P4_{particle_name}_p2;     P4_{particle_name}_p2.clear();
            Vint    Charge_{particle_name};    Charge_{particle_name}.clear();
            SmartDataPtr<EvtRecVeeVertexCol> recVeeVertexCol(eventSvc(), "/Event/EvtRec/EvtRecVeeVertexCol");                                                                       
            if(!recVeeVertexCol){{ log << MSG::FATAL << "Could not find EvtRecVeeVertexCol" << endreq; return StatusCode::FAILURE; }}
            EvtRecVeeVertexCol::iterator mom = recVeeVertexCol->begin();
            for (; mom!=recVeeVertexCol->end(); mom++) {{
                if ( (*mom)->vertexId() != 310 ) continue;
                WTrackParameter wtrkp_mom;
                wtrkp_mom.setW((*mom)->w());
                wtrkp_mom.setEw((*mom)->Ew());

                EvtRecTrack* veeTrackp1 = (*mom)->pairDaughters().first;
                RecMdcKalTrack* p1KalTrk = veeTrackp1->mdcKalTrack();
                p1KalTrk->setPidType(RecMdcKalTrack::pion);
                WTrackParameter p1 = WTrackParameter(mass[2], p1KalTrk->getZHelix(), p1KalTrk->getZError());

                EvtRecTrack* veeTrackp2 = (*mom)->pairDaughters().second;
                RecMdcKalTrack* p2KalTrk = veeTrackp2->mdcKalTrack();
                p2KalTrk->setPidType(RecMdcKalTrack::pion);
                WTrackParameter p2 = WTrackParameter(mass[2], p2KalTrk->getZHelix(), p2KalTrk->getZError());

                int i = veeTrackp1->trackId();
                int j = veeTrackp2->trackId();

                // vertex fit
                HepPoint3D vWideVertex(0., 0., 0.);
                HepSymMatrix evWideVertex(3, 0);
                evWideVertex[0][0] = 1.0e12;
                evWideVertex[1][1] = 1.0e12;
                evWideVertex[2][2] = 1.0e12;
                VertexParameter wideVertex;
                wideVertex.setVx(vWideVertex);
                wideVertex.setEvx(evWideVertex);
                vtxfit->init();
                vtxfit->AddTrack(0, p1);
                vtxfit->AddTrack(1, p2);
                vtxfit->AddVertex(0, wideVertex, 0, 1);
                if( !vtxfit->Fit(0) ) continue;
                vtxfit->Swim(0);
                vtxfit->BuildVirtualParticle(0);

                // secondary vertex fit
                HepPoint3D vBeamSpot(0., 0., 0.);
                HepSymMatrix evBeamSpot(3, 0);
                svtxfit->init();
                VertexParameter beamSpot;
                beamSpot.setVx(vBeamSpot);
                beamSpot.setEvx(evBeamSpot);
                VertexParameter primaryVertex(beamSpot);
                svtxfit->setPrimaryVertex(primaryVertex);
                svtxfit->setVpar(vtxfit->vpar(0));
                svtxfit->AddTrack(0, vtxfit->wVirtualTrack(0));
                if( !svtxfit->Fit() ) continue;
                double vfitlength = svtxfit->decayLength();
                double vfiterror  = svtxfit->decayLengthError();
                double vfitchi2   = svtxfit->chisq();
                double flightsig  = (vfiterror!=0) ? vfitlength/vfiterror : 0 ;

                if ( vfitchi2 > 100. ) continue;
                if ( flightsig < 2. ) continue;

                WTrackParameter wmom = vtxfit->wVirtualTrack(0);
                HepLorentzVector pmom = wmom.p();
                if ((pmom.m() <= {mass_ll}) || (pmom.m() >= {mass_ul})) continue;

                HepLorentzVector P_mom = wmom.p(); P_mom.boost(-0.011,0,0);  // from VertexFit wVirtualTrack (after B correction)
                HepVector mom_p1 = HepVector(7,0); mom_p1 = p1.w();
                HepLorentzVector P_p1(mom_p1[0],mom_p1[1],mom_p1[2],mom_p1[3]); P_p1.boost(-0.011,0,0);
                HepVector mom_p2 = HepVector(7,0); mom_p2 = p2.w();
                HepLorentzVector P_p2(mom_p2[0],mom_p2[1],mom_p2[2],mom_p2[3]); P_p2.boost(-0.011,0,0);

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wmom);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i); tmp_id.push_back(j);
                
                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}_p1.push_back(p1.p());
                Trkp_{particle_name}_p2.push_back(p2.p());
                Id_{particle_name}.push_back(tmp_id);
                Chi2_{particle_name}.push_back(vfitchi2);
                FlyLen_{particle_name}.push_back(vfitlength);
                FlySig_{particle_name}.push_back(flightsig);
                P4_{particle_name}.push_back(P_mom);
                P4_{particle_name}_p1.push_back(P_p1);
                P4_{particle_name}_p2.push_back(P_p2);
                Charge_{particle_name}.push_back(0);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        code_block += generate_particle_count_condition(particle_name, num_list[10])
    # elif particle.name == "gamma":
    #     code_block = f"""
    #         Vtrack2 Trk_{particle_name}_FSR;  Trk_{particle_name}_FSR.clear();
    #         Vp4     Trkp_{particle_name}_FSR; Trkp_{particle_name}_FSR.clear();
    #         Vint2   Id_{particle_name}_FSR;   Id_{particle_name}_FSR.clear();
    #         Vp4     P4_{particle_name}_FSR;   P4_{particle_name}_FSR.clear();
    #         Vtrack2 Trk_{particle_name};      Trk_{particle_name}.clear();
    #         Vp4     Trkp_{particle_name};     Trkp_{particle_name}.clear();
    #         Vint2   Id_{particle_name};       Id_{particle_name}.clear();
    #         Vp4     P4_{particle_name};       P4_{particle_name}.clear();
    #         for(int i=nCharged; i<nTotal; i++) {{
    #             EvtRecTrackIterator itTrk = evtRecTrkCol->begin() + i;
    #             if(!(*itTrk)->isEmcShowerValid()) continue;
    #             RecEmcShower *emcTrk = (*itTrk)->emcShower();
    #             HepLorentzVector shP4 = getP4(emcTrk);
    #             double cosThetaSh = shP4.vect().cosTheta();
    #             double eraw = shP4.e() ;
    #             bool inBarrelEndcap = false;
    #             if (fabs(cosThetaSh) < 0.8 && eraw > 0.025) inBarrelEndcap = true;
    #             if ((fabs(cosThetaSh) > 0.86) && (fabs(cosThetaSh) < 0.92) && eraw > 0.05 ) inBarrelEndcap = true;
    #             if ( !inBarrelEndcap ) continue;
    #             double Tdc = emcTrk->time();
    #             if( evtRecEvent->totalCharged() > 0 ) {{
    #                 if ( Tdc<0 || Tdc>14 ) continue;
    #             }}
    #             else {{
    #                 RecEmcShower* firstG = (*(evtRecTrkCol->begin()))->emcShower();
    #                 double deltaTime = fabs( Tdc - firstG->time() );
    #                 if ( deltaTime>10 ) continue ;
    #             }}
                
    #             Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i);
    #             Vtrack tmp_track; tmp_track.clear();

    #             Id_{particle_name}_FSR.push_back(tmp_id);
    #             HepLorentzVector ptrk_fsr = getP4(emcTrk);
    #             Trk_{particle_name}_FSR.push_back(tmp_track);
    #             Trkp_{particle_name}_FSR.push_back(ptrk_fsr);
    #             ptrk_fsr.boost(-0.011,0,0);
    #             P4_{particle_name}_FSR.push_back(ptrk_fsr);

    #             if(evtRecEvent->totalCharged()>0){{
    #                 Hep3Vector emcpos(emcTrk->x(), emcTrk->y(), emcTrk->z());
    #                 double dang = 200.;
    #                 for(int j=0; j<evtRecEvent->totalCharged(); j++) {{
    #                     EvtRecTrackIterator jtTrk = evtRecTrkCol->begin() + j;
    #                     if(!(*jtTrk)->isExtTrackValid()) continue;
    #                     RecExtTrack *extTrk = (*jtTrk)->extTrack();
    #                     if(extTrk->emcVolumeNumber() == -1) continue;
    #                     Hep3Vector extpos = extTrk->emcPosition();
    #                     double angd = extpos.angle(emcpos);
    #                     if(angd<dang) dang = angd;
    #                 }}
    #                 if(dang <200) {{
    #                     dang = dang * 180 / (CLHEP::pi);
    #                     if(dang <= 10.0) continue;
    #                 }}
    #             }}

    #             Id_{particle_name}.push_back(tmp_id);
    #             HepLorentzVector ptrk = getP4(emcTrk);
    #             Trk_{particle_name}.push_back(tmp_track);
    #             Trkp_{particle_name}.push_back(ptrk);
    #             ptrk.boost(-0.011,0,0);
    #             P4_{particle_name}.push_back(ptrk);
    #         }}
    #         int Number_{particle_name} = P4_{particle_name}.size();
    #         if (Number_{particle_name} > ({max_num}*2)) return StatusCode::SUCCESS; // 2 times pi0 / eta
    #     """
    elif particle.name == "pi0":
        if mass_ll is None and mass_ul is None:
            mass_ll = 0.115
            mass_ul = 0.15

        code_block = f"""
            Vtrack2 Trk_{particle_name};          Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name};         Trkp_{particle_name}.clear();
            Vp4     Trkp_{particle_name}_gam1;    Trkp_{particle_name}_gam1.clear();
            Vp4     Trkp_{particle_name}_gam2;    Trkp_{particle_name}_gam2.clear();
            Vdou    Chi2_{particle_name};         Chi2_{particle_name}.clear();
            Vp4     P4_{particle_name};           P4_{particle_name}.clear();
            Vp4     P4_{particle_name}_gam1;      P4_{particle_name}_gam1.clear();
            Vp4     P4_{particle_name}_gam2;      P4_{particle_name}_gam2.clear();
            Vint2   Id_{particle_name};           Id_{particle_name}.clear();
            Vint Charge_{particle_name};          Charge_{particle_name}.clear();
            for(int x=0; x<Number_gam-1; x++){{
                for(int y=x+1; y<Number_gam; y++){{
                    if( bothInEndcap(Trk_gam[x],Trk_gam[y]) ) continue; //use the gamma trk from shower to judge, do not in both endcap
                    HepLorentzVector p2g = Trk_gam[x] + Trk_gam[y];
                    if (p2g.m()<{mass_ll} || p2g.m()>{mass_ul}) continue;

                    RecEmcShower *g1Trk = (*(evtRecTrkCol->begin()+Id_gam[x]))->emcShower();
                    RecEmcShower *g2Trk = (*(evtRecTrkCol->begin()+Id_gam[y]))->emcShower();
                    kmfit->init();
                    kmfit->setIterNumber(5); 
                    kmfit->AddTrack(0, 0.0, g1Trk);
                    kmfit->AddTrack(1, 0.0, g2Trk);
                    kmfit->AddResonance(0, mpi0, 0, 1);
                    kmfit->Fit(0);
                    kmfit->BuildVirtualParticle(0);
                    WTrackParameter wvres = kmfit->wVirtualTrack(0);

                    double chisq = kmfit->chisq(0);
                    if( chisq>=200 ) continue;

                    p2g = kmfit->pfit(0) + kmfit->pfit(1); p2g.boost(-0.011,0,0);   
                    HepLorentzVector p_gam1 = Trk_gam[x]; p_gam1.boost(-0.011,0,0);
                    HepLorentzVector p_gam2 = Trk_gam[y]; p_gam2.boost(-0.011,0,0);

                    Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wvres);
                    Vint tmp_id; tmp_id.clear(); tmp_id.push_back(Id_gam[x]); tmp_id.push_back(Id_gam[y]);

                    Trk_{particle_name}.push_back(tmp_track);
                    Trkp_{particle_name}.push_back(wvres.p());
                    Trkp_{particle_name}_gam1.push_back(Trk_gam[x]);
                    Trkp_{particle_name}_gam2.push_back(Trk_gam[y]);
                    Chi2_{particle_name}.push_back(chisq);
                    P4_{particle_name}.push_back(p2g);
                    P4_{particle_name}_gam1.push_back(p_gam1);
                    P4_{particle_name}_gam2.push_back(p_gam2);
                    Id_{particle_name}.push_back(tmp_id);
                    Charge_{particle_name}.push_back(0);
                }}
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        code_block += generate_particle_count_condition(particle_name, num_list[11])
    elif particle.name == "eta":
        if mass_ll is None and mass_ul is None:
            mass_ll = 0.50
            mass_ul = 0.58

        code_block = f"""
            Vtrack2 Trk_{particle_name};          Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name};         Trkp_{particle_name}.clear();
            Vp4     Trkp_{particle_name}_gam1;    Trkp_{particle_name}_gam1.clear();
            Vp4     Trkp_{particle_name}_gam2;    Trkp_{particle_name}_gam2.clear();
            Vdou    Chi2_{particle_name};         Chi2_{particle_name}.clear();
            Vp4     P4_{particle_name};           P4_{particle_name}.clear();
            Vp4     P4_{particle_name}_gam1;      P4_{particle_name}_gam1.clear();
            Vp4     P4_{particle_name}_gam2;      P4_{particle_name}_gam2.clear();
            Vint2   Id_{particle_name};           Id_{particle_name}.clear();
            Vint Charge_{particle_name};          Charge_{particle_name}.clear();
            for(int x=0; x<Number_gam-1; x++){{
                for(int y=x+1; y<Number_gam; y++){{
                    if( bothInEndcap(Trk_gam[x],Trk_gam[y]) ) continue; //use the gamma trk from shower to judge, do not in both endcap
                    HepLorentzVector p2g = Trk_gam[x] + Trk_gam[y];
                    if (p2g.m()<{mass_ll} ||p2g.m()>{mass_ul}) continue;

                    RecEmcShower *g1Trk = (*(evtRecTrkCol->begin()+Id_gam[x]))->emcShower();
                    RecEmcShower *g2Trk = (*(evtRecTrkCol->begin()+Id_gam[y]))->emcShower();
                    kmfit->init();
                    kmfit->setIterNumber(5); 
                    kmfit->AddTrack(0, 0.0, g1Trk);
                    kmfit->AddTrack(1, 0.0, g2Trk);
                    kmfit->AddResonance(0, mEta, 0, 1);
                    kmfit->Fit(0);
                    kmfit->BuildVirtualParticle(0);
                    WTrackParameter wvres = kmfit->wVirtualTrack(0);

                    double chisq = kmfit->chisq(0);
                    if( chisq>=200 ) continue;

                    p2g = kmfit->pfit(0) + kmfit->pfit(1); p2g.boost(-0.011,0,0);   
                    HepLorentzVector p_gam1 = Trk_gam[x]; p_gam1.boost(-0.011,0,0);
                    HepLorentzVector p_gam2 = Trk_gam[y]; p_gam2.boost(-0.011,0,0);

                    Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wvres);
                    Vint tmp_id; tmp_id.clear(); tmp_id.push_back(Id_gam[x]); tmp_id.push_back(Id_gam[y]);

                    Trk_{particle_name}.push_back(tmp_track);
                    Trkp_{particle_name}.push_back(wvres.p());
                    Trkp_{particle_name}_gam1.push_back(Trk_gam[x]);
                    Trkp_{particle_name}_gam2.push_back(Trk_gam[y]);
                    Chi2_{particle_name}.push_back(chisq);
                    P4_{particle_name}.push_back(p2g);
                    P4_{particle_name}_gam1.push_back(p_gam1);
                    P4_{particle_name}_gam2.push_back(p_gam2);
                    Id_{particle_name}.push_back(tmp_id);
                    Charge_{particle_name}.push_back(0);
                }}
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        code_block += generate_particle_count_condition(particle_name, num_list[12])
    elif particle.name == "Lambda0": # TODO: what is the valid name for particle K(S)0 in decay chain?
        if mass_ll is None and mass_ul is None:
            mass_ll = 1.10
            mass_ul = 1.13

        code_block = f"""
            Vtrack2 Trk_{particle_name};       Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name}_p1;   Trkp_{particle_name}_p1.clear();
            Vp4     Trkp_{particle_name}_p2;   Trkp_{particle_name}_p2.clear();
            Vint2   Id_{particle_name};        Id_{particle_name}.clear();
            Vdou    Chi2_{particle_name};      Chi2_{particle_name}.clear();
            Vdou    FlyLen_{particle_name};    FlyLen_{particle_name}.clear();
            Vdou    FlySig_{particle_name};    FlySig_{particle_name}.clear();
            Vp4     P4_{particle_name};        P4_{particle_name}.clear();
            Vp4     P4_{particle_name}_p1;     P4_{particle_name}_p1.clear();
            Vp4     P4_{particle_name}_p2;     P4_{particle_name}_p2.clear();
            Vint    Charge_{particle_name};    Charge_{particle_name}.clear();
            SmartDataPtr<EvtRecVeeVertexCol> recVeeVertexCol(eventSvc(), "/Event/EvtRec/EvtRecVeeVertexCol");                                                                       
            if(!recVeeVertexCol){{ log << MSG::FATAL << "Could not find EvtRecVeeVertexCol" << endreq; return StatusCode::FAILURE; }}
            EvtRecVeeVertexCol::iterator mom = recVeeVertexCol->begin();
            for (; mom!=recVeeVertexCol->end(); mom++) {{
                if ( (*mom)->vertexId() != 3122 ) continue;
                WTrackParameter wtrkp_mom;
                wtrkp_mom.setW((*mom)->w());
                wtrkp_mom.setEw((*mom)->Ew());

                EvtRecTrack* veeTrackp1 = (*mom)->pairDaughters().first;
                RecMdcKalTrack* p1KalTrk = veeTrackp1->mdcKalTrack();
                p1KalTrk->setPidType(RecMdcKalTrack::proton);
                WTrackParameter p1 = WTrackParameter(mass[4], p1KalTrk->getZHelixP(), p1KalTrk->getZErrorP());

                EvtRecTrack* veeTrackp2 = (*mom)->pairDaughters().second;
                RecMdcKalTrack* p2KalTrk = veeTrackp2->mdcKalTrack();
                p2KalTrk->setPidType(RecMdcKalTrack::pion);
                WTrackParameter p2 = WTrackParameter(mass[2], p2KalTrk->getZHelix(), p2KalTrk->getZError());

                int i = veeTrackp1->trackId();
                int j = veeTrackp2->trackId();

                // vertex fit
                HepPoint3D vWideVertex(0., 0., 0.);
                HepSymMatrix evWideVertex(3, 0);
                evWideVertex[0][0] = 1.0e12;
                evWideVertex[1][1] = 1.0e12;
                evWideVertex[2][2] = 1.0e12;
                VertexParameter wideVertex;
                wideVertex.setVx(vWideVertex);
                wideVertex.setEvx(evWideVertex);
                vtxfit->init();
                vtxfit->AddTrack(0, p1);
                vtxfit->AddTrack(1, p2);
                vtxfit->AddVertex(0, wideVertex, 0, 1);
                if( !vtxfit->Fit(0) ) continue;
                vtxfit->Swim(0);
                vtxfit->BuildVirtualParticle(0);

                // secondary vertex fit
                HepPoint3D vBeamSpot(0., 0., 0.);
                HepSymMatrix evBeamSpot(3, 0);
                svtxfit->init();
                VertexParameter beamSpot;
                beamSpot.setVx(vBeamSpot);
                beamSpot.setEvx(evBeamSpot);
                VertexParameter primaryVertex(beamSpot);
                svtxfit->setPrimaryVertex(primaryVertex);
                svtxfit->setVpar(vtxfit->vpar(0));
                svtxfit->AddTrack(0, vtxfit->wVirtualTrack(0));
                if( !svtxfit->Fit() ) continue;
                double vfitlength = svtxfit->decayLength();
                double vfiterror  = svtxfit->decayLengthError();
                double vfitchi2   = svtxfit->chisq();
                double flightsig  = (vfiterror!=0) ? vfitlength/vfiterror : 0 ;

                if ( vfitchi2 > 100. ) continue;
                if ( flightsig < 2. ) continue;

                WTrackParameter wmom = vtxfit->wVirtualTrack(0);
                HepLorentzVector pmom = wmom.p();
                if ((pmom.m() <= {mass_ll}) || (pmom.m() >= {mass_ul})) continue;

                HepLorentzVector P_mom = wmom.p(); P_mom.boost(-0.011,0,0);  // from VertexFit wVirtualTrack (after B correction)
                HepVector mom_p1 = HepVector(7,0); mom_p1 = p1.w();
                HepLorentzVector P_p1(mom_p1[0],mom_p1[1],mom_p1[2],mom_p1[3]); P_p1.boost(-0.011,0,0);
                HepVector mom_p2 = HepVector(7,0); mom_p2 = p2.w();
                HepLorentzVector P_p2(mom_p2[0],mom_p2[1],mom_p2[2],mom_p2[3]); P_p2.boost(-0.011,0,0);

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wmom);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i); tmp_id.push_back(j);
                
                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}_p1.push_back(p1.p());
                Trkp_{particle_name}_p2.push_back(p2.p());
                Id_{particle_name}.push_back(tmp_id);
                Chi2_{particle_name}.push_back(vfitchi2);
                FlyLen_{particle_name}.push_back(vfitlength);
                FlySig_{particle_name}.push_back(flightsig);
                P4_{particle_name}.push_back(P_mom);
                P4_{particle_name}_p1.push_back(P_p1);
                P4_{particle_name}_p2.push_back(P_p2);
                Charge_{particle_name}.push_back(0);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        code_block += generate_particle_count_condition(particle_name, num_list[13])
    elif particle.name == "anti-Lambda0": # TODO: what is the valid name for particle K(S)0 in decay chain?
        if mass_ll is None and mass_ul is None:
            mass_ll = 1.10
            mass_ul = 1.13

        code_block = f"""
            Vtrack2 Trk_{particle_name};       Trk_{particle_name}.clear();
            Vp4     Trkp_{particle_name}_p1;   Trkp_{particle_name}_p1.clear();
            Vp4     Trkp_{particle_name}_p2;   Trkp_{particle_name}_p2.clear();
            Vint2   Id_{particle_name};        Id_{particle_name}.clear();
            Vdou    Chi2_{particle_name};      Chi2_{particle_name}.clear();
            Vdou    FlyLen_{particle_name};    FlyLen_{particle_name}.clear();
            Vdou    FlySig_{particle_name};    FlySig_{particle_name}.clear();
            Vp4     P4_{particle_name};        P4_{particle_name}.clear();
            Vp4     P4_{particle_name}_p1;     P4_{particle_name}_p1.clear();
            Vp4     P4_{particle_name}_p2;     P4_{particle_name}_p2.clear();
            Vint    Charge_{particle_name};    Charge_{particle_name}.clear();
            SmartDataPtr<EvtRecVeeVertexCol> recVeeVertexCol(eventSvc(), "/Event/EvtRec/EvtRecVeeVertexCol");                                                                       
            if(!recVeeVertexCol){{ log << MSG::FATAL << "Could not find EvtRecVeeVertexCol" << endreq; return StatusCode::FAILURE; }}
            EvtRecVeeVertexCol::iterator mom = recVeeVertexCol->begin();
            for (; mom!=recVeeVertexCol->end(); mom++) {{
                if ( (*mom)->vertexId() != -3122 ) continue;
                WTrackParameter wtrkp_mom;
                wtrkp_mom.setW((*mom)->w());
                wtrkp_mom.setEw((*mom)->Ew());

                EvtRecTrack* veeTrackp1 = (*mom)->pairDaughters().first;
                RecMdcKalTrack* p1KalTrk = veeTrackp1->mdcKalTrack();
                p1KalTrk->setPidType(RecMdcKalTrack::proton);
                WTrackParameter p1 = WTrackParameter(mass[4], p1KalTrk->getZHelixP(), p1KalTrk->getZErrorP());

                EvtRecTrack* veeTrackp2 = (*mom)->pairDaughters().second;
                RecMdcKalTrack* p2KalTrk = veeTrackp2->mdcKalTrack();
                p2KalTrk->setPidType(RecMdcKalTrack::pion);
                WTrackParameter p2 = WTrackParameter(mass[2], p2KalTrk->getZHelix(), p2KalTrk->getZError());

                int i = veeTrackp1->trackId();
                int j = veeTrackp2->trackId();

                // vertex fit
                HepPoint3D vWideVertex(0., 0., 0.);
                HepSymMatrix evWideVertex(3, 0);
                evWideVertex[0][0] = 1.0e12;
                evWideVertex[1][1] = 1.0e12;
                evWideVertex[2][2] = 1.0e12;
                VertexParameter wideVertex;
                wideVertex.setVx(vWideVertex);
                wideVertex.setEvx(evWideVertex);
                vtxfit->init();
                vtxfit->AddTrack(0, p1);
                vtxfit->AddTrack(1, p2);
                vtxfit->AddVertex(0, wideVertex, 0, 1);
                if( !vtxfit->Fit(0) ) continue;
                vtxfit->Swim(0);
                vtxfit->BuildVirtualParticle(0);

                // secondary vertex fit
                HepPoint3D vBeamSpot(0., 0., 0.);
                HepSymMatrix evBeamSpot(3, 0);
                svtxfit->init();
                VertexParameter beamSpot;
                beamSpot.setVx(vBeamSpot);
                beamSpot.setEvx(evBeamSpot);
                VertexParameter primaryVertex(beamSpot);
                svtxfit->setPrimaryVertex(primaryVertex);
                svtxfit->setVpar(vtxfit->vpar(0));
                svtxfit->AddTrack(0, vtxfit->wVirtualTrack(0));
                if( !svtxfit->Fit() ) continue;
                double vfitlength = svtxfit->decayLength();
                double vfiterror  = svtxfit->decayLengthError();
                double vfitchi2   = svtxfit->chisq();
                double flightsig  = (vfiterror!=0) ? vfitlength/vfiterror : 0 ;

                if ( vfitchi2 > 100. ) continue;
                if ( flightsig < 2. ) continue;

                WTrackParameter wmom = vtxfit->wVirtualTrack(0);
                HepLorentzVector pmom = wmom.p();
                if ((pmom.m() <= {mass_ll}) || (pmom.m() >= {mass_ul})) continue;

                HepLorentzVector P_mom = wmom.p(); P_mom.boost(-0.011,0,0);  // from VertexFit wVirtualTrack (after B correction)
                HepVector mom_p1 = HepVector(7,0); mom_p1 = p1.w();
                HepLorentzVector P_p1(mom_p1[0],mom_p1[1],mom_p1[2],mom_p1[3]); P_p1.boost(-0.011,0,0);
                HepVector mom_p2 = HepVector(7,0); mom_p2 = p2.w();
                HepLorentzVector P_p2(mom_p2[0],mom_p2[1],mom_p2[2],mom_p2[3]); P_p2.boost(-0.011,0,0);

                Vtrack tmp_track; tmp_track.clear(); tmp_track.push_back(wmom);
                Vint tmp_id; tmp_id.clear(); tmp_id.push_back(i); tmp_id.push_back(j);
                
                Trk_{particle_name}.push_back(tmp_track);
                Trkp_{particle_name}_p1.push_back(p1.p());
                Trkp_{particle_name}_p2.push_back(p2.p());
                Id_{particle_name}.push_back(tmp_id);
                Chi2_{particle_name}.push_back(vfitchi2);
                FlyLen_{particle_name}.push_back(vfitlength);
                FlySig_{particle_name}.push_back(flightsig);
                P4_{particle_name}.push_back(P_mom);
                P4_{particle_name}_p1.push_back(P_p1);
                P4_{particle_name}_p2.push_back(P_p2);
                Charge_{particle_name}.push_back(0);
            }}
            int Number_{particle_name} = P4_{particle_name}.size();
            if (Number_{particle_name} > {max_num}) return StatusCode::SUCCESS;
        """
        code_block += generate_particle_count_condition(particle_name, num_list[14])

    return code_block

def generate_nested_particle_combination_condition(particle: Particle, data: DotMap) -> str:
    """
    从稳定粒子开始，逐层向上重建潜在的中间态。重建终点为输入的particle实例(不包含该particle本身，只重建其子粒子)。
    输出的代码块的内容中保存了所有复合粒子的属性，详见combine_particle()函数
    """
    intermediate_state = []
    code_block = ""

    for child in particle.children:
        if child.name not in STABLE_PARTICLES and child.name not in STABLE_PARTICLES_EX:
            intermediate_state.append(child)
    
    while True:
        if not intermediate_state or all(state.is_reconstructed for state in intermediate_state): # 假如末态都是稳定粒子或者中间态都已经被重建
            if particle.id == 0: return code_block # 不重建root_particle，例如Y(4260)
            code_block += combine_particle(particle, data)
            particle.is_reconstructed = True
            return code_block
        else:
            for state in intermediate_state:
                code_block += generate_nested_particle_combination_condition(state, data)

def combine_particle(particle: Particle, data: DotMap) -> str:
    """
    根据子粒子的种类和数量，输出input粒子的重建代码块
    支持两体衰变，三体衰变，四体衰变

    存储内容：
        - 复合粒子的candidate数量
        - 复合粒子的四动量：二维数组，第二维定长为4，形如[[px1, py1, pz1, e1], [px2, py2, pz2, e2], ...]
        - 复合粒子的电荷
        - 复合粒子的末态粒子ID：二维数组，形如[[id1, id2, id3, id4, id5, id6], [id2, id3, id4, id5, id6, id7], ...]，表示该复合粒子有两个以上candidate。例如首个candidate包含6条track，id分别是id1, id2, ..., id6。
        - 复合粒子的末态粒子track
    """
    children = particle.children
    n_body = len(children)
    assert n_body >= 2, "Error: Too little final states to combine"
    
    particle_name = []
    particle_name.append(get_VarName(particle))
    for child in particle.children:
        particle_name.append(get_VarName(child))

    len_mass_window = round(5*particle.width, 6) if particle.width > 0.01 else 0.05 # to be optimized
    mother_mass = round(particle.mass, 6)
    code_block = f"""
            int Number_{particle_name[0]} = 0;
            Vint Charge_{particle_name[0]};   Charge_{particle_name[0]}.clear();
            Vdou Mass_{particle_name[0]};     Mass_{particle_name[0]}.clear();
            Vtrack2 Trk_{particle_name[0]};   Trk_{particle_name[0]}.clear();
            Vint2 Id_{particle_name[0]};      Id_{particle_name[0]}.clear();
            Vp4 P4_{particle_name[0]};        P4_{particle_name[0]}.clear();
            Vint2 Id_best_{particle_name[0]}; Id_best_{particle_name[0]}.clear();
        """

    if n_body == 2:
        code_block += f"""
            for(int i=0; i<Number_{particle_name[1]}; i++){{
                for(int j=0; j<Number_{particle_name[2]}; j++){{
                
                    Vint2 tmp_id;
                    tmp_id.push_back(Id_{particle_name[1]}[i]);
                    tmp_id.push_back(Id_{particle_name[2]}[j]);
                    if( Same(tmp_id) ) continue;

                    if( Charge_{particle_name[1]}[i] != {int(children[0].charge)} ) continue;
                    if( Charge_{particle_name[2]}[j] != {int(children[1].charge)} ) continue;

                    HepLorentzVector tmp_intermediate;
                    tmp_intermediate = P4_{particle_name[1]}[i] + P4_{particle_name[2]}[j];
                    mass_diff_tmp = abs( tmp_intermediate.m() - {mother_mass} );
                    if ( mass_diff_tmp > {len_mass_window} ) continue;

                    // save good intermediate state
                    Charge_{particle_name[0]}.push_back(Charge_{particle_name[1]}[i] + Charge_{particle_name[2]}[j]);
                    Mass_{particle_name[0]}.push_back(tmp_intermediate.m());
                    P4_{particle_name[0]}.push_back(tmp_intermediate);

                    // save id of good intermediate state's daughters
                    Vint Id_tmp; Id_tmp.clear();
                    Vtrack Trk_tmp; Trk_tmp.clear();
                    for (int ii=0; ii<Id_{particle_name[1]}[i].size(); ii++) {{
                        Id_tmp.push_back(Id_{particle_name[1]}[i][ii]);
                        Trk_tmp.push_back(Trk_{particle_name[1]}[i][ii]);
                    }}
                    for (int jj=0; jj<Id_{particle_name[2]}[j].size(); jj++) {{
                        Id_tmp.push_back(Id_{particle_name[2]}[j][jj]);
                        Trk_tmp.push_back(Trk_{particle_name[2]}[j][jj]);
                    }}
                    Id_{particle_name[0]}.push_back(Id_tmp);
                    Trk_{particle_name[0]}.push_back(Trk_tmp);

                    Vint Id_best_tmp; Id_best_tmp.clear();
                    Id_best_tmp.push_back(i); Id_best_tmp.push_back(j);
                    Id_best_{particle_name[0]}.push_back(Id_best_tmp);
                }}
            }}
            Number_{particle_name[0]} = P4_{particle_name[0]}.size();
            if (Number_{particle_name[0]} == 0) return StatusCode::SUCCESS;
        """
    elif n_body == 3:
        code_block += f"""
            for(int i=0; i<Number_{particle_name[1]}; i++){{
                for(int j=0; j<Number_{particle_name[2]}; j++){{
                    for(int k=0; k<Number_{particle_name[3]}; k++){{

                        Vint2 tmp_id;
                        tmp_id.push_back(Id_{particle_name[1]}[i]);
                        tmp_id.push_back(Id_{particle_name[2]}[j]);
                        tmp_id.push_back(Id_{particle_name[3]}[k]);
                        if( Same(tmp_id) ) continue;

                        if( Charge_{particle_name[1]}[i] != {int(children[0].charge)} ) continue;
                        if( Charge_{particle_name[2]}[j] != {int(children[1].charge)} ) continue;
                        if( Charge_{particle_name[3]}[k] != {int(children[2].charge)} ) continue;

                        HepLorentzVector tmp_intermediate;
                        tmp_intermediate = P4_{particle_name[1]}[i] + P4_{particle_name[2]}[j] + P4_{particle_name[3]}[k];
                        mass_diff_tmp = abs( tmp_intermediate.m() - {mother_mass} );
                        if ( mass_diff_tmp > {len_mass_window} ) continue;

                        // save good intermediate state
                        Charge_{particle_name[0]}.push_back(Charge_{particle_name[1]}[i] + Charge_{particle_name[2]}[j] + Charge_{particle_name[3]}[k]);
                        Mass_{particle_name[0]}.push_back(tmp_intermediate.m());
                        P4_{particle_name[0]}.push_back(tmp_intermediate);

                        // save id of good intermediate state's daughters
                        Vint Id_tmp; Id_tmp.clear();
                        Vtrack Trk_tmp; Trk_tmp.clear();
                        for (int ii=0; ii<Id_{particle_name[1]}[i].size(); ii++) {{
                            Id_tmp.push_back(Id_{particle_name[1]}[i][ii]);
                            Trk_tmp.push_back(Trk_{particle_name[1]}[i][ii]);
                        }}
                        for (int jj=0; jj<Id_{particle_name[2]}[j].size(); jj++) {{
                            Id_tmp.push_back(Id_{particle_name[2]}[j][jj]);
                            Trk_tmp.push_back(Trk_{particle_name[2]}[j][jj]);
                        }}
                        for (int kk=0; kk<Id_{particle_name[3]}[k].size(); kk++) {{
                            Id_tmp.push_back(Id_{particle_name[3]}[k][kk]);
                            Trk_tmp.push_back(Trk_{particle_name[3]}[k][kk]);
                        }}
                        Id_{particle_name[0]}.push_back(Id_tmp);
                        Trk_{particle_name[0]}.push_back(Trk_tmp);

                        Vint Id_best_tmp; Id_best_tmp.clear();
                        Id_best_tmp.push_back(i); Id_best_tmp.push_back(j); Id_best_tmp.push_back(k);
                        Id_best_{particle_name[0]}.push_back(Id_best_tmp);
                    }}
                }}
            }}
            Number_{particle_name[0]} = P4_{particle_name[0]}.size();
            if (Number_{particle_name[0]} == 0) return StatusCode::SUCCESS;
        """
    elif n_body == 4:
        code_block += f"""
            for(int i=0; i<Number_{particle_name[1]}; i++){{
                for(int j=0; j<Number_{particle_name[2]}; j++){{
                    for(int k=0; k<Number_{particle_name[3]}; k++){{
                        for(int l=0; l<Number_{particle_name[4]}; l++){{

                            Vint2 tmp_id;
                            tmp_id.push_back(Id_{particle_name[1]}[i]);
                            tmp_id.push_back(Id_{particle_name[2]}[j]);
                            tmp_id.push_back(Id_{particle_name[3]}[k]);
                            tmp_id.push_back(Id_{particle_name[4]}[l]);
                            if( Same(tmp_id) ) continue;

                            if( Charge_{particle_name[1]}[i] != {int(children[0].charge)} ) continue;
                            if( Charge_{particle_name[2]}[j] != {int(children[1].charge)} ) continue;
                            if( Charge_{particle_name[3]}[k] != {int(children[2].charge)} ) continue;
                            if( Charge_{particle_name[4]}[l] != {int(children[3].charge)} ) continue;
                            
                            HepLorentzVector tmp_intermediate;
                            tmp_intermediate = P4_{particle_name[1]}[i] + P4_{particle_name[2]}[j] + P4_{particle_name[3]}[k] + P4_{particle_name[4]}[l];
                            mass_diff_tmp = abs( tmp_intermediate.m() - {mother_mass} );
                            if ( mass_diff_tmp > {len_mass_window} ) continue;

                            // save good intermediate state
                            Charge_{particle_name[0]}.push_back(Charge_{particle_name[1]}[i] + Charge_{particle_name[2]}[j] + Charge_{particle_name[3]}[k] + Charge_{particle_name[4]}[l]);
                            Mass_{particle_name[0]}.push_back(tmp_intermediate.m());
                            P4_{particle_name[0]}.push_back(tmp_intermediate);

                            // save id of good intermediate state's daughters
                            Vint Id_tmp; Id_tmp.clear();
                            Vtrack Trk_tmp; Trk_tmp.clear();
                            for (int ii=0; ii<Id_{particle_name[1]}[i].size(); ii++) {{
                                Id_tmp.push_back(Id_{particle_name[1]}[i][ii]);
                                Trk_tmp.push_back(Trk_{particle_name[1]}[i][ii]);
                            }}
                            for (int jj=0; jj<Id_{particle_name[2]}[j].size(); jj++) {{
                                Id_tmp.push_back(Id_{particle_name[2]}[j][jj]);
                                Trk_tmp.push_back(Trk_{particle_name[2]}[j][jj]);
                            }}
                            for (int kk=0; kk<Id_{particle_name[3]}[k].size(); kk++) {{
                                Id_tmp.push_back(Id_{particle_name[3]}[k][kk]);
                                Trk_tmp.push_back(Trk_{particle_name[3]}[k][kk]);
                            }}
                            for (int ll=0; ll<Id_{particle_name[4]}[l].size(); ll++) {{
                                Id_tmp.push_back(Id_{particle_name[4]}[l][ll]);
                                Trk_tmp.push_back(Trk_{particle_name[4]}[l][ll]);
                            }}
                            Id_{particle_name[0]}.push_back(Id_tmp);
                            Trk_{particle_name[0]}.push_back(Trk_tmp);

                            Vint Id_best_tmp; Id_best_tmp.clear();
                            Id_best_tmp.push_back(i); Id_best_tmp.push_back(j); Id_best_tmp.push_back(k); Id_best_tmp.push_back(l);
                            Id_best_{particle_name[0]}.push_back(Id_best_tmp);
                        }}
                    }}
                }}
            }}
            Number_{particle_name[0]} = P4_{particle_name[0]}.size();
            if(Number_{particle_name[0]} == 0) return StatusCode::SUCCESS;
        """
    else:
        raise ValueError("暂不支持五体及更多体的衰变")
    
    code_block = handle_indentation(code_block, 4)
    return code_block 

def generate_best_candidate_condition(particle_list: List[Particle], data: DotMap, stable_particles: List[Particle]) -> str:
    """
    - 从combine_particle()函数中保存的中间态列表中寻找最佳的候选，判选依据为：质量差最小or拟合优度最小
    - 不兼容没有中间共振态的情况，需要在mapping函数中设置相应条件

    输出：对应的C++代码块，其中保存了best_candidate的标称质量，子粒子ID
    """
    children = particle_list[0].children
    n_body = len(children)
    assert n_body >= 2, "Error: Too little final states to combine"
    
    particle_name = [] # 第一层衰变的粒子名
    particle_name.append(get_VarName(particle_list[0]))
    for child in children:
        particle_name.append(get_VarName(child))
    
    track_name = [] # 所有track的粒子名
    for particle in stable_particles:
        track_name.append(get_VarName(particle))
    
    particle_name_EX = [] # 所有次级粒子的粒子名
    for particle in particle_list[1:]:
        particle_name_EX.append(get_VarName(particle))

    mother_mass = round(particle_list[0].mass, 6)
    fit_methods = data.Selection.KinematicFit
    if fit_methods:
        method = data.Selection.KinematicFit.Method.lower()
    save_type = data.Selection.SaveType.lower()
    iter = ["i", "j", "k", "l", "m", "n"]
    
    code_block = ""
    code_block_in = generate_RecSaveInfo_in_execute(particle_list, data) if save_type == "candidate" else ""
    idx_best_saveInfo = ""
    for i, child in enumerate(children):
        idx_best_saveInfo += f"""idx_best_{get_VarName(child)} = {iter[i]};\n                            """
        if child.children:
            for j, child2 in enumerate(child.children):
                idx_best_saveInfo += f"""idx_best_{get_VarName(child2)} = Id_best_{get_VarName(child)}[{iter[i]}][{j}];\n                            """

    kmfit_saveInfo = "if(chisq_min < 200){\n                            "
    for i, name in enumerate(track_name):
        kmfit_saveInfo += f"""P4_KF_{track_name[i]} = P4_KF_list[trk_count++];\n                            """
    kmfit_saveInfo += "}\n                            "

    if n_body == 2:
        if save_type == "event":
            if method == "mass_diff":
                code_block_in += f"""
                    mass_diff_tmp = abs( (P4_{particle_name[1]}[i]+P4_{particle_name[2]}[j]).m() - {mother_mass} );
                    if( mass_diff_tmp < mass_diff_min ){{
                        mass_diff_min = mass_diff_tmp;
                    }}
                """
            elif method == "km_fit":
                code_block_in += f"""
                    {generate_kinematic_fit_condition(particle_list, data)}
                    if ( chisq_tmp < chisq_min ) {{
                        chisq_min = chisq_tmp;

                        {idx_best_saveInfo}

                        int trk_count = 0;
                        {kmfit_saveInfo}
                    }}
                """

        for name in track_name:
            code_block += f"""        HepLorentzVector P4_KF_{name};\n"""
        for name in particle_name_EX:
            code_block += f"""        int idx_best_{name} = -1;\n"""
            
        code_block += f"""
        for (int i=0; i<Number_{particle_name[1]}; i++) {{
            for (int j=0; j<Number_{particle_name[2]}; j++) {{
            
                Vint2 Id_tmp; Id_tmp.clear();
                Id_tmp.push_back(Id_{particle_name[1]}[i]);
                Id_tmp.push_back(Id_{particle_name[2]}[j]);
                if ( Same( Id_tmp ) ) continue;
                {code_block_in}
            }}
        }}
        """
    elif n_body == 3:
        if save_type == "event":
            if method == "mass_diff":
                code_block_in += f"""
                    mass_diff_tmp = abs( (P4_{particle_name[1]}[i]+P4_{particle_name[2]}[j]).m()+P4_{particle_name[3]}[k].m() - {mother_mass} );
                    if( mass_diff_tmp < mass_diff_min ){{
                        mass_diff_min = mass_diff_tmp;
                    }}
                """
            elif method == "km_fit":
                code_block_in += f"""
                    {generate_kinematic_fit_condition(particle_list, data)}
                    if ( chisq_tmp < chisq_min ) {{
                        chisq_min = chisq_tmp;

                        {idx_best_saveInfo}

                        int trk_count = 0;
                        {kmfit_saveInfo}
                    }}
                """

        for name in track_name:
            code_block += f"""        HepLorentzVector P4_KF_{name};\n"""
        for name in particle_name_EX:
            code_block += f"""        int idx_best_{name} = -1;\n"""

        code_block += f"""
        for (int i=0; i<Number_{particle_name[1]}; i++) {{
            for (int j=0; j<Number_{particle_name[2]}; j++) {{
                for (int k=0; k<Number_{particle_name[3]}; k++) {{
                
                    Vint2 Id_tmp; Id_tmp.clear();
                    Id_tmp.push_back(Id_{particle_name[1]}[i]);
                    Id_tmp.push_back(Id_{particle_name[2]}[j]);
                    Id_tmp.push_back(Id_{particle_name[3]}[k]);
                    if ( Same( Id_tmp ) ) continue;
                    {code_block_in}
                }}
            }}
        }}
        """
    elif n_body == 4:
        if save_type == "event":
            if method == "mass_diff":
                code_block_in += f"""
                    mass_diff_tmp = abs( (P4_{particle_name[1]}[i]+P4_{particle_name[2]}[j]).m()+P4_{particle_name[3]}[k].m()+P4_{particle_name[4]}[l].m() - {mother_mass} );
                    if( mass_diff_tmp < mass_diff_min ){{
                        mass_diff_min = mass_diff_tmp;
                    }}
                """
            elif method == "km_fit":
                code_block_in += f"""
                    {generate_kinematic_fit_condition(particle_list, data)}
                    if ( chisq_tmp < chisq_min ) {{
                        chisq_min = chisq_tmp;

                        {idx_best_saveInfo}

                        int trk_count = 0;
                        {kmfit_saveInfo}
                    }}
                """

        for name in track_name:
            code_block += f"""        HepLorentzVector P4_KF_{name};\n"""
        for name in particle_name_EX:
            code_block += f"""        int idx_best_{name} = -1;\n"""

        code_block += f"""
        for (int i=0; i<Number_{particle_name[1]}; i++) {{
            for (int j=0; j<Number_{particle_name[2]}; j++) {{
                for (int k=0; k<Number_{particle_name[3]}; k++) {{
                    for (int l=0; l<Number_{particle_name[4]}; l++) {{
                    
                        Vint2 Id_tmp; Id_tmp.clear();
                        Id_tmp.push_back(Id_{particle_name[1]}[i]);
                        Id_tmp.push_back(Id_{particle_name[2]}[j]);
                        Id_tmp.push_back(Id_{particle_name[3]}[k]);
                        Id_tmp.push_back(Id_{particle_name[4]}[l]);
                        if ( Same( Id_tmp ) ) continue;
                        {code_block_in}
                    }}
                }}
            }}
        }}
        """
    else:
        raise ValueError("暂不支持五体及更多体的衰变")
    
    ## 由于best_candidate选择可能和kinematic fit有关
    if method == "km_fit":
        code_block += "        if (chisq_min>200 && chisq_min!=9999) return StatusCode::SUCCESS;\n"

    code_block = handle_indentation(code_block, 4)
    return code_block

def generate_kinematic_fit_condition(particle_list: List[Particle], data: DotMap) -> str:
    """
    - 输入衰变链的母粒子，对其第一层末态粒子进行拟合，若有共振态则向下寻找直至找到所有稳定末态粒子
    - 策略是同时对所有稳定末态粒子粒子进行拟合，中间态以质量约束的方式放入
    - 支持miss track

    输出：对应的C++代码块
    """
    children = particle_list[0].children
    n_body = len(children)
    assert n_body >= 2, "Error: Too little final states to combine"
    
    particle_name = []
    py_constraint_list = ["Placeholder"]
    particle_name.append(get_VarName(particle_list[0]))
    for child in particle_list[0].children:
        particle_name.append(get_VarName(child))
        py_constraint_list.append(get_all_constraint_list(child, data))

    fit_methods = data.Selection.KinematicFit
    m_miss = get_particle_from_name(fit_methods.MissTrack).mass if fit_methods.MissTrack else -1
    
    code_block = ""
    code_block_in = ""
    for i, constraint in enumerate(py_constraint_list):
        if i > 0 and constraint is not None:
            code_block_in += insert_constraint_list(constraint)

    if n_body == 2:
        code_block = f"""
            // Kinematic fit
            Vp4 P4_KF_list; P4_KF_list.clear();  
            Vtrack track_list; track_list.clear();
            Vdou2 constraint_list; constraint_list.clear();
            Vdou tmp_constraint;
            
            for(int x=0; x<Id_{particle_name[1]}[i].size(); x++){{
                track_list.push_back(Trk_{particle_name[1]}[i][x]);
            }}

            for (int x=0; x<Id_{particle_name[2]}[j].size(); x++){{
                track_list.push_back(Trk_{particle_name[2]}[j][x]);
            }}

            {code_block_in}

            chisq_tmp = doKinematicFit(kmfit, ecms, track_list, constraint_list, {m_miss}, P4_KF_list);
        """
    elif n_body == 3:
        code_block = f"""
            // Kinematic fit
            Vp4 P4_KF_list; P4_KF_list.clear();  
            Vtrack track_list; track_list.clear();
            Vdou2 constraint_list; constraint_list.clear();
            Vdou tmp_constraint;
            
            for(int x=0; x<Id_{particle_name[1]}[i].size(); x++){{
                track_list.push_back(Trk_{particle_name[1]}[i][x]);
            }}

            for (int x=0; x<Id_{particle_name[2]}[j].size(); x++){{
                track_list.push_back(Trk_{particle_name[2]}[j][x]);
            }}

            for (int x=0; x<Id_{particle_name[3]}[k].size(); x++){{
                track_list.push_back(Trk_{particle_name[3]}[k][x]);
            }}

            {code_block_in}

            chisq_tmp = doKinematicFit(kmfit, ecms, track_list, constraint_list, {m_miss}, P4_KF_list);
        """
    elif n_body == 4:
        code_block = f"""
            // Kinematic fit
            Vp4 P4_KF_list; P4_KF_list.clear();  
            Vtrack track_list; track_list.clear();
            Vdou2 constraint_list; constraint_list.clear();
            Vdou tmp_constraint;
            
            for(int x=0; x<Id_{particle_name[1]}[i].size(); x++){{
                track_list.push_back(Trk_{particle_name[1]}[i][x]);
            }}

            for (int x=0; x<Id_{particle_name[2]}[j].size(); x++){{
                track_list.push_back(Trk_{particle_name[2]}[j][x]);
            }}

            for (int x=0; x<Id_{particle_name[3]}[k].size(); x++){{
                track_list.push_back(Trk_{particle_name[3]}[k][x]);
            }}

            for (int x=0; x<Id_{particle_name[4]}[l].size(); x++){{
                track_list.push_back(Trk_{particle_name[4]}[l][x]);
            }}

            {code_block_in}

            chisq_tmp = doKinematicFit(kmfit, ecms, track_list, constraint_list, {m_miss}, P4_KF_list);
        """
    else:
        raise ValueError("暂不支持五体及更多体的衰变")
    
    code_block = handle_indentation(code_block, 20)
    return code_block

# TODO: 对于有末态粒子的中间态，需要递归生成质量约束列表
def get_all_constraint_list(particle: Particle, data: DotMap) -> List[dict]:
    """
    递归生成质量约束列表，直到末态稳定粒子
    """
    constraint_list = []

    ## TODO: change to the RESONANCE_KF_LIST
    if particle.name not in STABLE_PARTICLES and particle.name not in STABLE_PARTICLES_EX:
        is_need_mass_constraint = True
    else:
        is_need_mass_constraint = False

    if is_need_mass_constraint: # 假如末态都是稳定粒子或者中间态都已经被重建
        constraint_list.append(get_single_constraint_list(particle, data))
        particle.is_reconstructed = True
        return constraint_list
    else:
        for state in particle.children:
            constraint_list += get_all_constraint_list(state, data)

def get_single_constraint_list(particle: Particle, data: DotMap) -> dict:
    """
    输入衰变链的母粒子，生成质量约束列表
    """
    cons_list = {"mass": 0, "list": []}
 
    cons_list["mass"] = particle.mass
    for child in particle.children: # 递归得到所有稳定末态粒子的Final ID，插入到约束列表中
        if child.name in STABLE_PARTICLES:
            cons_list["list"].append(child.id)
        else:
            grandchild_cons_list = get_single_constraint_list(child, data)
            for i in grandchild_cons_list["list"]:
                cons_list["list"].append(i)
    return cons_list

def insert_constraint_list(py_constraint_list: list) -> str:
    """
    将质量约束列表插入到C++代码中
    """
    code_block = ""
    if py_constraint_list is None:
        return ""
    for cons in py_constraint_list:
        mass = round(cons["mass"], 6)
        index_list = cons["list"]
        code_block += f"tmp_constraint.clear();\n"
        for index in index_list:
            code_block += " "*12 + f"tmp_constraint.push_back({index}.0);\n"
        code_block += " "*12 + f"tmp_constraint.push_back({mass});\n"
    code_block += " "*12 + f"constraint_list.push_back(tmp_constraint);\n"
    
    return code_block

def generate_RecSaveInfo_in_execute(particle_list: List[Particle], data: DotMap) -> str:
    """
    生成能够保存重建粒子信息的C++代码块
    与变量定义函数generate_VarDefinitions_in_tuple()对应
    """

    children = particle_list[0].children
    code_block = """
        m_runNo_reco = runNo;
        m_evtNo_reco = evtNo;
        m_nCharged_reco = nCharged;
        m_nNeutral_reco = nNeutral;
        m_nGoodCharged_reco = nGood;

        m_idxmc_reco = idxmc;
        for(int i=0; i<idxmc; i++){
            m_pdgid_reco[i] = pdgid[i];
            m_motheridx_reco[i] = motheridx[i];
        }
    """
    code_block = handle_indentation(code_block, 0)

    for i, child in enumerate(children):
        code_block += generate_RecSaveInfo_singleParticle(child, data)
    
    fit_methods = data.Selection.KinematicFit
    if fit_methods:
        method = data.Selection.KinematicFit.Method.lower()
    if method == "km_fit":
        code_block += f"m_chisq_reco = chisq_min;\n"
    code_block += "m_tuple_reco->write();\n"
    
    code_block = handle_indentation(code_block, 4)
    return code_block

def generate_RecSaveInfo_singleParticle(particle: Particle, data: DotMap) -> str:
    """
    - 根据粒子类型，生成对应的存储变量赋值代码块
    - 支持charged、neutral、intermediate_states
    """
    fit_methods = data.Selection.KinematicFit
    if fit_methods:
        method = data.Selection.KinematicFit.Method.lower()
    save_type = data.Selection.SaveType.lower()
    code_block = ""
    particle_name = get_VarName(particle)

    if not particle.children: # 单个粒子
        if int(particle.charge) != 0:
            for varname, varlength in RECVARS_CHARGED_PARTICLES.items():
                if varlength != 1:
                    for i in range(varlength):
                        code_block += f"m_{particle_name}_{varname}[{i}] = {varname}_{particle_name}[idx_best_{particle_name}][{i}];\n"
                else:
                    code_block += f"m_{particle_name}_{varname} = {varname}_{particle_name}[idx_best_{particle_name}];\n"
        else:
            for varname, varlength in RECVARS_NEUTRAL_PARTICLES.items():
                if varlength != 1:
                    for i in range(varlength):
                        code_block += f"m_{particle_name}_{varname}[{i}] = {varname}_{particle_name}[idx_best_{particle_name}][{i}];\n"
                else:
                    code_block += f"m_{particle_name}_{varname} = {varname}_{particle_name}[idx_best_{particle_name}];\n"
        
        if method == "km_fit" and save_type != "candidate":
            code_block += f"m_{particle_name}_P4_KF[0] = P4_KF_{particle_name}.px();\n"
            code_block += f"m_{particle_name}_P4_KF[1] = P4_KF_{particle_name}.py();\n"
            code_block += f"m_{particle_name}_P4_KF[2] = P4_KF_{particle_name}.pz();\n"
            code_block += f"m_{particle_name}_P4_KF[3] = P4_KF_{particle_name}.e();\n"
    else: # 共振态
        for varname, varlength in RECVARS_INTERMEDIATE_STATES.items():
            code_block += f"m_{particle_name}_{varname} = {varname}_{particle_name}[idx_best_{particle_name}];\n"
        for child in particle.children:
            code_block += generate_RecSaveInfo_singleParticle(child, data)

    return code_block


#######################################################################################################
if __name__ == "__main__":
    decay_chain_1 = "Y(4260) -> pi+ [K*0 -> [Ks -> pi+ pi-] pi0] [jpsi -> e+ e-] pi-"
    decay_chain_2 = "Y(4260) -> pi+ [K*0 -> [Ks -> pi+ pi-] pi0] [jpsi -> e+ e-]"
    decay_chain_3 = "Y(4260) -> [K*0 -> [Ks -> pi+ pi-] pi0] [jpsi -> e+ e-]"
    decay_chain_4 = "Z0 -> [J/psi -> e+ e-] [psi(2S) -> pi+ pi- [J/psi -> e+ e-]]"
    decay_chain_5 = "Z0 -> [J/psi -> e+ e-] [J/psi -> e+ e-] [psi(2S) -> pi+ pi- [J/psi -> e+ e-]]"
    decay_chain_6 = "psi(2S) -> pi+ pi- [J/psi -> e+ e-]"
    decay_chain_7 = "psi(2S) -> pi0 pi0 [J/psi -> e+ e-]" # TODO: 未考虑pi0的情况
    decay_chain_8 = "J/psi -> e+ e-"
    decay_chain_9 = "psi(4260) -> pi+ pi- [J/psi -> mu+ mu-]"

    # aaa = get_particles_from_decay_chain(decay_chain_4)
    # print(aaa)

    # condition = generate_nested_condition(aaa[5])
    # print(condition)
    
    # for particle in aaa:
    #     print(particle.name)
    #     for dau_particle in get_final_particles(particle):
    #         print(f"  {dau_particle.name}")
            
    my_particle_list = get_particles_from_decay_chain(decay_chain_9)
    print(my_particle_list)
    a = get_final_state(my_particle_list)

    # aaa = generate_kinematic_fit_condition(my_particle_list, DotMap())
    # print(aaa)
    
