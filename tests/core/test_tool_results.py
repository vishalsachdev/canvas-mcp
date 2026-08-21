import json
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ToolAnnotations

from canvas_mcp.core.tool_results import install_tool_result_contract

_EXPLICIT_TEXT_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "string"}},
    "required": ["result"],
    "x-fastmcp-wrap-result": True,
}


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

    @mcp.tool(
        output_schema=_EXPLICIT_TEXT_SCHEMA,
        annotations=ToolAnnotations(readOnlyHint=True),
    )
    async def explicit_text(value: str) -> str:
        return value

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


@pytest.mark.asyncio
async def test_string_result_has_one_text_surface_and_no_structured_duplicate():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "text_result", {"value": "single copy"}, raise_on_error=False
        )

    assert tools["text_result"].outputSchema is None
    assert result.structured_content is None
    assert len(result.content) == 1
    assert getattr(result.content[0], "text", None) == "single copy"


@pytest.mark.asyncio
async def test_dictionary_tool_retains_schema_and_structured_content():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "dict_result", {"fail": False}, raise_on_error=False
        )

    assert tools["dict_result"].outputSchema is not None
    assert result.structured_content == {
        "success": True,
        "detail": {"error": "quoted example"},
    }


@pytest.mark.asyncio
async def test_installing_contract_twice_does_not_double_wrap_registration():
    from canvas_mcp.core.tool_results import install_tool_result_contract

    mcp = FastMCP("double-install")
    install_tool_result_contract(mcp)
    install_tool_result_contract(mcp)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def once() -> str:
        return "one"

    async with Client(mcp) as client:
        result = await client.call_tool("once", raise_on_error=False)

    assert result.structured_content is None
    assert [getattr(block, "text", None) for block in result.content] == ["one"]


@pytest.mark.asyncio
async def test_explicit_string_schema_is_respected_and_legacy_wrapper_errors():
    async with Client(_result_server()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        result = await client.call_tool(
            "explicit_text",
            {"value": "Error: explicit schema failure"},
            raise_on_error=False,
        )

    assert tools["explicit_text"].outputSchema["x-fastmcp-wrap-result"] is True
    assert result.structured_content == {"result": "Error: explicit schema failure"}
    assert result.is_error is True


@pytest.mark.asyncio
async def test_register_all_tools_marks_existing_validation_failure_as_mcp_error():
    from canvas_mcp.server import register_all_tools

    mcp = FastMCP("full-contract")
    register_all_tools(mcp, role="all")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_syllabus",
            {
                "course_identifier": 60366,
                "output_format": "text",
                "max_chars": 0,
            },
            raise_on_error=False,
        )

    assert result.is_error is True
    assert getattr(result.content[0], "text", "").startswith("Error: max_chars")


@pytest.mark.asyncio
async def test_full_registry_suppresses_only_string_output_schemas():
    from canvas_mcp.server import register_all_tools

    mcp = FastMCP("full-schema-contract")
    register_all_tools(mcp, role="all")
    tools = {tool.name: tool for tool in await mcp.list_tools(run_middleware=False)}

    string_tools = [tool for tool in tools.values() if tool.return_type is str]
    assert string_tools
    assert all(tool.output_schema is None for tool in string_tools)
    assert tools["list_conversations"].output_schema is not None
