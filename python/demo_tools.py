"""示例用的设备工具（MCP）：开关灯、查电量。把 run_tool 换成你的真实设备逻辑即可。
Demo device tools (MCP): lights and battery. Replace run_tool with your real device logic."""
import json

import adventists as a

TOOLS = {
    "light_control": {
        "description": "打开或关闭某个房间的灯 / Turn the lights in a room on or off",
        "parameters": {"type": "object", "properties": {
            "room": {"type": "string", "description": "房间，例如 客厅、卧室 / room name"},
            "state": {"type": "string", "enum": ["on", "off"]}},
            "required": ["room", "state"]},
    },
    "get_battery": {
        "description": "查询设备剩余电量 / Get the device's battery level",
        "parameters": {"type": "object", "properties": {}},
    },
}


def run_tool(method: str, params: dict) -> dict:
    if method == "light_control":
        print(f"  [device] light {params.get('room')} -> {params.get('state')}")
        return {"success": True, "data": f"{params.get('room')}的灯已{'打开' if params.get('state') == 'on' else '关闭'}"}
    if method == "get_battery":
        return {"success": True, "data": "电量 76%"}
    return {"success": False, "error": f"unknown tool {method}"}


def register(conn):
    """认证后注册（可以随时重新注册）/ register after auth (re-register any time)."""
    conn.send(a.MCP, json.dumps({"type": "register", "data": {"services": TOOLS}}, ensure_ascii=False).encode(), "mcp00001")


def handle(conn, task_id: str, body: str) -> bool:
    """处理一条 MCP 消息；是工具调用就执行并回结果。/ handle one MCP frame; run the tool and reply if it is a call."""
    msg = json.loads(body)
    if msg.get("type") != "call":
        print(f"  [mcp] {body[:120]}")
        return False
    d = msg["data"]
    result = run_tool(d["method"], d.get("params") or {})
    conn.send(a.MCP, json.dumps({"type": "result", "data": {"call_id": d["call_id"], "result": result}},
                                ensure_ascii=False).encode(), task_id)
    return True
