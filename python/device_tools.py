"""设备工具（MCP）：把设备自己的能力注册给角色，角色在对话中需要时会调用。
Device tools (MCP): register what your device can do; the character calls it when needed.

本例注册两个工具（见 demo_tools.py）：开关灯、查电量。全双工下的用法见 talk_duplex.py --tools。
This example registers two tools (see demo_tools.py): lights and battery. For duplex see talk_duplex.py --tools.

  python device_tools.py --say "帮我把客厅的灯关掉" --save reply.wav
  python device_tools.py                 # 交互：打字和角色对话 / interactive: type to chat
"""
import argparse

import adventists as a
import demo_tools

ap = argparse.ArgumentParser()
ap.add_argument("--say", help="send one text message and exit")
ap.add_argument("--save", help="save reply audio to this wav instead of playing it")
args = ap.parse_args()

api = a.Api()
speaker = a.WavOutput(args.save) if args.save else a.SpeakerOutput()
conn = a.Connection(a.npc_token(api), {"mode": "manual"}, on_audio=speaker.write)

demo_tools.register(conn)        # 认证后注册工具 / register tools after auth


def chat(text: str):
    task = a.new_task_id()
    conn.send(a.TEXT, text.encode(), task, 0)
    conn.send(a.END, b"", task, 1)
    while True:
        t, tid, body = conn.events.get(timeout=90)
        if t is None or (t == a.END and tid == task):
            return
        if t == a.MCP:
            demo_tools.handle(conn, tid, body)
        else:
            a.print_event(t, body)


try:
    if args.say:
        chat(args.say)
    else:
        print("[type a message, e.g. 帮我把客厅的灯关掉 / 还有多少电; Ctrl+C to quit]")
        while True:
            line = input("> ").strip()
            if line:
                chat(line)
except KeyboardInterrupt:
    pass
finally:
    conn.close()
    speaker.close()
