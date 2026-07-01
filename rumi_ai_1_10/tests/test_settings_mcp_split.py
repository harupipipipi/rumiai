from core_runtime.mcp.models import MCPServerDefinition, MCPToolDefinition
from core_runtime.mcp.settings_adapter import mcp_server_to_setting
from core_runtime.settings.models import SettingSectionId


def test_mcp_server_setting_lives_under_tools_mcp():
    server = MCPServerDefinition(
        server_id="airtable",
        display_name="Airtable MCP",
        transport="http",
        endpoint="https://example.com/mcp",
        required_provider_id="airtable",
    )
    tools = [MCPToolDefinition("airtable.search", "airtable", "Search records", "Search records", "read")]
    setting = mcp_server_to_setting(server, tools)
    assert setting.section == SettingSectionId.TOOLS_MCP
    assert "connection.airtable" in setting.requires
    assert setting.status == "missing"
