#!/usr/bin/env python3
"""
Run the Moltbook MCP server in stdio mode for Claude Desktop.
This bypasses the HTTP transport and communicates directly via stdin/stdout.
"""
import sys
import os

# Add the project directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the server in stdio mode
from server import mcp

if __name__ == "__main__":
    mcp.run()  # stdio is the default transport
