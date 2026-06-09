"""在运营商家诊断子图节点（贾丽婼 - Day 2）。

四个节点对应三个专家 Skill MD + 一个汇总节点：
- Checker     ← jingying_zhenduan.md（入口：体检 + 异常识别 + overlay 归属）
- Attributor  ← guiyin.md（归因：MECE 拆维度 + 跨场景 + 非数据信号）
- Advisor     ← xingdong_jianyi.md（建议：资源挂钩 + 准入校验 + 排序）
- Composer    ← markdown 报告组装

使用：from agent.nodes.diagnosis import Checker, Attributor, Advisor, Composer
"""
from .advisor import Advisor
from .attributor import Attributor
from .checker import Checker
from .composer import Composer

__all__ = ["Checker", "Attributor", "Advisor", "Composer"]
