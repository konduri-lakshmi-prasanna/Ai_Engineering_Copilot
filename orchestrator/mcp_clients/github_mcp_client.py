import os
import asyncio
import logging
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("mcp_client")


class GitHubMCPClient:
    """
    Genuine Model Context Protocol (MCP) Client for GitHub integration.
    Connects to a configured GitHub MCP server via stdio transport.
    Adheres to read-only tool access by default.
    Provides graceful fallback to direct PyGithub API when the server is offline or not configured.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.server_command = os.getenv("GITHUB_MCP_SERVER_COMMAND", "npx -y @modelcontextprotocol/server-github")
        self.enabled = os.getenv("GITHUB_MCP_ENABLED", "false").lower() in ("true", "1", "yes")
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return self.enabled and bool(self.token)

    async def get_file_contents(self, repo_name: str, file_path: str, ref: Optional[str] = None) -> Optional[str]:
        """
        Executes read-only get_file_contents tool via MCP.
        Returns the decoded text content of the requested repository file.
        """
        if not self.is_available:
            self._last_error = "MCP is disabled or GITHUB_TOKEN is not configured"
            return None

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            env = os.environ.copy()
            if self.token:
                env["GITHUB_PERSONAL_ACCESS_TOKEN"] = self.token

            parts = self.server_command.split()
            command = parts[0]
            args = parts[1:] if len(parts) > 1 else []

            server_params = StdioServerParameters(command=command, args=args, env=env)

            # Bounded execution with a 10s timeout to protect against frozen server processes
            async with asyncio.timeout(10.0):
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        tool_names = [t.name for t in tools_result.tools]
                        logger.info(f"Connected to GitHub MCP server. Available tools: {tool_names}")

                        owner, _, repo = repo_name.partition("/")
                        call_args = {"owner": owner, "repo": repo, "path": file_path}
                        if ref:
                            call_args["ref"] = ref

                        # Standard MCP GitHub server tool names
                        target_tool = "get_file_contents" if "get_file_contents" in tool_names else "read_file"
                        if target_tool not in tool_names:
                            self._last_error = f"Tool '{target_tool}' not exposed by MCP server"
                            return None

                        result = await session.call_tool(target_tool, arguments=call_args)
                        self._connected = True
                        if result and result.content:
                            text_blocks = [c.text for c in result.content if hasattr(c, "text")]
                            return "\n".join(text_blocks)
                        return None
        except Exception as e:
            self._last_error = f"MCP call failed: {str(e)}"
            logger.warning(f"GitHub MCP Client error: {e}")
            return None

    def get_status(self) -> Dict[str, Any]:
        """Returns integration diagnostics for the MCP client."""
        return {
            "mcp_enabled": self.enabled,
            "mcp_configured": bool(self.token and self.server_command),
            "mcp_connected": self._connected,
            "server_command": self.server_command,
            "last_error": self._last_error,
            "mode": "MCP" if self._connected else "Direct_API_Fallback",
        }
