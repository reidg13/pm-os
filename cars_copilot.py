#!/usr/bin/env python3
"""Product Copilot MCP Server — entry point."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
