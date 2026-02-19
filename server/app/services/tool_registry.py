"""
Tool Use 框架 (M5.1)

注册工具定义 → agent_runner 调用 LLM 时传入 tools 参数 → LLM 返回 tool_call → 执行工具 → 返回结果
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict  # JSON Schema
    handler: Callable[..., Awaitable[dict]]  # async (arguments, context) -> dict


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get_tools_for_llm(self) -> list[dict]:
        """返回 OpenAI function calling 格式的工具列表。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict, context: dict) -> dict:
        """执行工具，返回结果。"""
        tool = self._tools.get(name)
        if not tool:
            return {"ok": False, "error": f"未知工具: {name}"}
        try:
            result = await tool.handler(arguments, context)
            return {"ok": True, "result": result}
        except Exception as e:
            logger.error("Tool %s execution failed: %s", name, e)
            return {"ok": False, "error": str(e)}


# --- transfer_resource 工具 ---

async def _handle_transfer_resource(arguments: dict, context: dict) -> dict:
    """transfer_resource 工具的 handler。from_agent_id 从 context 取，Agent 不能伪造身份。"""
    from .city_service import transfer_resource
    db = context["db"]
    from_agent_id = context["agent_id"]
    to_agent_id = arguments["to_agent_id"]
    resource_type = arguments["resource_type"]
    quantity = arguments["quantity"]
    return await transfer_resource(from_agent_id, to_agent_id, resource_type, quantity, db)


TRANSFER_RESOURCE_TOOL = ToolDefinition(
    name="transfer_resource",
    description="将自己的资源转赠给另一个居民",
    parameters={
        "type": "object",
        "properties": {
            "to_agent_id": {"type": "integer", "description": "接收方居民 ID"},
            "resource_type": {"type": "string", "description": "资源类型，如 flour"},
            "quantity": {"type": "number", "description": "转赠数量"},
        },
        "required": ["to_agent_id", "resource_type", "quantity"],
    },
    handler=_handle_transfer_resource,
)

# 全局单例
tool_registry = ToolRegistry()
tool_registry.register(TRANSFER_RESOURCE_TOOL)


# --- M5.2 交易市场工具 ---

async def _handle_create_market_order(arguments: dict, context: dict) -> dict:
    """create_market_order handler。seller_id 从 context 取。"""
    from .market_service import create_order
    db = context["db"]
    seller_id = context["agent_id"]
    return await create_order(
        seller_id=seller_id,
        sell_type=arguments["sell_type"], sell_amount=arguments["sell_amount"],
        buy_type=arguments["buy_type"], buy_amount=arguments["buy_amount"],
        db=db,
    )


async def _handle_accept_market_order(arguments: dict, context: dict) -> dict:
    """accept_market_order handler。buyer_id 从 context 取。"""
    from .market_service import accept_order
    db = context["db"]
    buyer_id = context["agent_id"]
    return await accept_order(
        buyer_id=buyer_id,
        order_id=arguments["order_id"],
        buy_ratio=arguments.get("buy_ratio", 1.0),
        db=db,
    )


async def _handle_cancel_market_order(arguments: dict, context: dict) -> dict:
    """cancel_market_order handler。seller_id 从 context 取。"""
    from .market_service import cancel_order
    db = context["db"]
    seller_id = context["agent_id"]
    return await cancel_order(seller_id=seller_id, order_id=arguments["order_id"], db=db)


CREATE_MARKET_ORDER_TOOL = ToolDefinition(
    name="create_market_order",
    description="在交易市场挂单：卖出一种资源，换取另一种资源",
    parameters={
        "type": "object",
        "properties": {
            "sell_type": {"type": "string", "description": "卖出资源类型，如 wheat"},
            "sell_amount": {"type": "number", "description": "卖出数量"},
            "buy_type": {"type": "string", "description": "想买资源类型，如 flour"},
            "buy_amount": {"type": "number", "description": "想买数量"},
        },
        "required": ["sell_type", "sell_amount", "buy_type", "buy_amount"],
    },
    handler=_handle_create_market_order,
)

ACCEPT_MARKET_ORDER_TOOL = ToolDefinition(
    name="accept_market_order",
    description="接受交易市场上的挂单（可部分接单）",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "integer", "description": "挂单 ID"},
            "buy_ratio": {"type": "number", "description": "接单比例 0~1，默认 1.0（全额）"},
        },
        "required": ["order_id"],
    },
    handler=_handle_accept_market_order,
)

CANCEL_MARKET_ORDER_TOOL = ToolDefinition(
    name="cancel_market_order",
    description="撤销自己在交易市场上的挂单",
    parameters={
        "type": "object",
        "properties": {
            "order_id": {"type": "integer", "description": "挂单 ID"},
        },
        "required": ["order_id"],
    },
    handler=_handle_cancel_market_order,
)

tool_registry.register(CREATE_MARKET_ORDER_TOOL)
tool_registry.register(ACCEPT_MARKET_ORDER_TOOL)
tool_registry.register(CANCEL_MARKET_ORDER_TOOL)

# TODO: 假设所有模型支持 function calling，后续按需补降级逻辑
