import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ToolAnnotations

from canvas_mcp.core.tool_results import install_tool_result_contract


def _result_server() -> FastMCP:
    mcp = FastMCP("tool-result-contract")
    install_tool_result_contract(mcp)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def text_result(value: str) -> str:
        return value

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def dict_result(fail: bool) -> dict[str, Any]:
        if fail:
            return {"error": "boom", "nothing_sent": True}
        return {"success": True, "detail": {"error": "quoted example"}}

    return mcp


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        "Error: invalid course",
        "❌ Submission blocked",
        json.dumps({"error": "invalid course"}),
    ],
)
async def test_text_error_conventions_set_mcp_error_without_rewriting(payload):
    async with Client(_result_server()) as client:
        result = await client.call_tool(
            "text_result", {"value": payload}, raise_on_error=False
        )

    assert result.is_error is True
    assert len(result.content) == 1
    assert getattr(result.content[0], "text", None) == payload


@pytest.mark.asyncio
async def test_top_level_dict_error_keeps_structured_payload_and_sets_mcp_error():
    async with Client(_result_server()) as client:
        result = await client.call_tool(
            "dict_result", {"fail": True}, raise_on_error=False
        )

    assert result.is_error is True
    assert result.structured_content == {"error": "boom", "nothing_sent": True}


@pytest.mark.asyncio
async def test_success_text_and_nested_error_field_remain_successful():
    async with Client(_result_server()) as client:
        text_result = await client.call_tool(
            "text_result", {"value": "No errors found"}, raise_on_error=False
        )
        dict_result = await client.call_tool(
            "dict_result", {"fail": False}, raise_on_error=False
        )

    assert text_result.is_error is False
    assert dict_result.is_error is False
