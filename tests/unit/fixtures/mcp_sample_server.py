from __future__ import annotations

import json
import os
import sys

REQUEST_COUNT = 0
SERVER_PID = os.getpid()


def main() -> None:
    global REQUEST_COUNT

    for line in sys.stdin:
        if not line.strip():
            continue

        REQUEST_COUNT += 1
        request = json.loads(line)
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "sample-mcp-server",
                        "version": "1.0.0",
                    },
                },
            }
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo",
                            "title": "MCP Echo",
                            "description": "Echo a message from the MCP sample server.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {
                                        "type": "string",
                                        "description": "Message to echo.",
                                    },
                                    "uppercase": {
                                        "type": "boolean",
                                        "description": "Uppercase the returned message.",
                                    },
                                },
                                "required": ["message"],
                            },
                            "annotations": {"readOnlyHint": True},
                        },
                        {
                            "name": "sum",
                            "title": "MCP Sum",
                            "description": "Add two integers on the MCP sample server.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "left": {
                                        "type": "integer",
                                        "description": "Left operand.",
                                    },
                                    "right": {
                                        "type": "integer",
                                        "description": "Right operand.",
                                    },
                                },
                                "required": ["left", "right"],
                            },
                            "annotations": {"readOnlyHint": True},
                        },
                    ],
                },
            }
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            if tool_name == "echo":
                message = str(arguments.get("message", ""))
                uppercase = bool(arguments.get("uppercase", False))
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": {
                            "message": message.upper() if uppercase else message,
                            "uppercase": uppercase,
                            "server_pid": SERVER_PID,
                            "request_count": REQUEST_COUNT,
                        },
                    },
                }
            elif tool_name == "sum":
                left = int(arguments.get("left", 0))
                right = int(arguments.get("right", 0))
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": {
                            "left": left,
                            "right": right,
                            "total": left + right,
                            "server_pid": SERVER_PID,
                            "request_count": REQUEST_COUNT,
                        },
                    },
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
