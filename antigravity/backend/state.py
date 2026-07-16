"""进程级共享状态：项目库 + 病人库 + 配置管理器（单例，供各路由模块导入）。"""

from __future__ import annotations

from . import WORKSPACE
from .project import ProjectStore

from antigravity.engine.config_manager import ConfigManager  # noqa: E402

project_store = ProjectStore(WORKSPACE)

# 兼容旧代码：全局病人库（从第一个项目的病人恢复，或空）
from .patient import PatientStore, Patient
store = PatientStore(WORKSPACE / "_legacy_patients")

config = ConfigManager()


def find_patient(patient_id: str):
    """从全局 store 或所有项目 store 查找病人，返回 (Patient|None, Project|None)。"""
    p = store.get(patient_id)
    if p:
        return p, None
    for proj in project_store.all():
        p = proj.patient_store.get(patient_id)
        if p:
            return p, proj
    return None, None
