"""浏览器 / App 示例的后端。key 只放在服务端：浏览器向这里要一个令牌，再自己用 WebSocket 连 Harness。
Backend for the browser / app example. The key stays on the server: the browser asks here for a token and then
connects to Harness over WebSocket by itself.

  pip install requests
  export ADVENTISTS_API_KEY=sk-sophon-...
  python server.py            # 打开 / open http://localhost:8000 （麦克风需要 localhost 或 https / mic needs localhost or https）

正式产品里请把 /api/session 放在你自己的登录之后，并给每个用户（或设备）各建一个角色。
In production, put /api/session behind your own login and create one character per user (or device).
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

REGION = os.environ.get("ADVENTISTS_REGION", "cn")
BASE = {"cn": "https://api.adventists.cn", "global": "https://api.adventists.ai"}[REGION]
WS_URL = {"cn": "wss://api.adventists.cn/ws-beta", "global": "wss://api.adventists.ai/ws-beta"}[REGION]
H = {"Authorization": f"Bearer {os.environ['ADVENTISTS_API_KEY']}"}
HERE = os.path.dirname(os.path.abspath(__file__))
NPC_FILE = os.path.join(HERE, ".npcid")


def npcid_for_demo() -> str:
    """示例里所有访客共用一个角色；正式产品请按用户分别创建并保存 npcid。
    The demo shares one character; in production create and store one per user."""
    if os.path.exists(NPC_FILE):
        return open(NPC_FILE).read().strip()
    r = requests.post(f"{BASE}/v2/init", headers=H, json={}, timeout=30).json()
    open(NPC_FILE, "w").write(r["data"])
    return r["data"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = open(os.path.join(HERE, "index.html"), "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/session":
            return self.send_error(404)
        npcid = npcid_for_demo()
        token = requests.post(f"{BASE}/v2/login", headers=H, data={"npcid": npcid}, timeout=30).json()["token"]
        body = json.dumps({"token": token, "ws_url": WS_URL, "npcid": npcid}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"open http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
