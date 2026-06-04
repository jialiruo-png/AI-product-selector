"""工具协议层基类（PRD 5.1）。

提供：
    - BaseTool：抽象基类，定义 name/description/input_schema/output_schema 与 run()。
    - TOOL_REGISTRY：模块级注册表，工具在 import 时通过 register() 自动注册。
    - register()：注册函数 / 装饰器。

设计要点：
    - 不引入 jsonschema 依赖，run() 只做"必填键存在"的轻校验（纯标准库）。
    - run() 捕获所有异常并返回 {"error": ..., "ok": False}，保证 graph 不被单个工具炸掉。
    - to_openai_schema / to_anthropic_schema：把 input_schema 转成两家 function-calling 格式。
"""
from __future__ import annotations

from typing import Any


class BaseTool:
    """所有工具的抽象基类。子类实现 _run()，外部统一调用 run()。"""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    output_schema: dict[str, Any] = {"type": "object", "properties": {}}

    # ---- 子类需实现 ----
    def _run(self, **kwargs: Any) -> dict:
        raise NotImplementedError(f"{type(self).__name__} 未实现 _run()")

    # ---- 对外统一入口 ----
    def run(self, **kwargs: Any) -> dict:
        """轻校验必填键 -> 调 _run -> 返回结果；任何异常转成 {"ok": False, "error": ...}。"""
        try:
            missing = self._missing_required(kwargs)
            if missing:
                return {"ok": False,
                        "error": f"缺少必填参数: {', '.join(missing)}"}
            return self._run(**kwargs)
        except Exception as exc:  # noqa: BLE001 — 工具层兜底，绝不向上抛
            return {"ok": False, "error": str(exc)}

    # ---- 轻量校验（纯标准库，不依赖 jsonschema）----
    def _missing_required(self, kwargs: dict) -> list[str]:
        required = self.input_schema.get("required") or []
        return [k for k in required if k not in kwargs or kwargs[k] is None]

    # ---- function-calling 格式转换 ----
    def to_openai_schema(self) -> dict:
        """OpenAI tools 格式：{"type":"function","function":{name,description,parameters}}。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def to_anthropic_schema(self) -> dict:
        """Anthropic tools 格式：{name, description, input_schema}。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Tool {self.name}>"


# ---- 模块级注册表 + 自动注册 ----
TOOL_REGISTRY: dict[str, BaseTool] = {}


def register(tool: BaseTool) -> BaseTool:
    """注册一个工具实例到 TOOL_REGISTRY。可当函数用，也可当装饰器（作用于实例）。"""
    if not getattr(tool, "name", ""):
        raise ValueError(f"工具 {tool!r} 缺少 name，无法注册")
    TOOL_REGISTRY[tool.name] = tool
    return tool
