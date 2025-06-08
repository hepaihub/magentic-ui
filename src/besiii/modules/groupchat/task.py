from typing import Dict, List, Optional, Literal, Any
from dataclasses import dataclass, field
import time
import uuid

TaskStatus = Literal["queued", "in_progress", "completed", "paused"]

@dataclass
class Task():
    """Enhanced task management system with lifecycle tracking and validation"""
    # 核心任务信息（创建时必须提供）
    content: str
    source: str
  
    # 自动生成的元信息
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    updated_at: Optional[float] = None
  
    # 任务配置
    task_type: str = "add"
    status: TaskStatus = "queued"
    metadata: Dict[str, Any] = field(default_factory=dict)
  
    # 任务关系
    parent_task: Optional['Task'] = None  # 父任务的ID
    sub_tasks: List['Task'] = field(default_factory=list)
  
    # 完成信息
    completed_at: Optional[float] = None
    solution: Optional[str] = None

    def __post_init__(self):
        """初始化时自动设置更新时间"""
        self.updated_at = self.created_at
        if self.parent_task:
            self.parent_task.add_subtask(self)

    def update_content(self, new_content: str) -> None:
        """更新任务内容并记录修改时间"""
        self.content = new_content
        self.updated_at = time.time()
      
    def add_subtask(self, subtask: 'Task') -> None:
        """添加子任务并建立双向关联"""
        subtask.parent_task = self
        self.sub_tasks.append(subtask)

    def set_status(self, new_status: TaskStatus) -> None:
        """安全的状态转换方法"""
        valid_transitions = {
            "queued": ["in_progress", "paused"],
            "in_progress": ["paused", "completed"],
            "paused": ["in_progress", "queued", "completed"],
            "completed": []
        }
      
        if new_status not in valid_transitions[self.status]:
            raise ValueError(f"Cannot transition from {self.status} to {new_status}")
          
        self.status = new_status
        self.updated_at = time.time()
      
        if new_status == "completed":
            self.completed_at = time.time()

    def set_completed(self, solution: str = None) -> None:
        """完成任务并记录解决方案"""
        self.set_status("completed")
        self.solution = solution
      
    @property
    def age(self) -> float:
        """获取任务存活时间（秒）"""
        return time.time() - self.created_at

    @property
    def is_active(self) -> bool:
        """判断任务是否处于活动状态"""
        return self.status in ["in_progress"]