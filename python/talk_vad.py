"""自动（VAD）模式：服务端判断你什么时候说完，一问一答。
Auto (VAD) mode: the server detects when you finish speaking; turn by turn.

要点 / key points:
  - 每一轮由客户端发 LISTEN start（带这一轮的 task_id）/ the client starts each turn with LISTEN start + its task_id
  - 收到 LISTEN detecting（用户开始说话）时停止播放，实现打断 / on "detecting" stop playback to barge in
  - 收到这一轮的 END 后，换新 task_id 开始下一轮 / after the turn's END, start a new turn with a new task_id

  python talk_vad.py                      # 麦克风 + 扬声器 / microphone + speaker
  python talk_vad.py --wav two_questions.wav --save reply.wav
"""
import argparse
import json
import threading
import time

import adventists as a

ap = argparse.ArgumentParser()
ap.add_argument("--wav")
ap.add_argument("--save")
ap.add_argument("--seconds", type=float)
args = ap.parse_args()

api = a.Api()
mic, speaker = a.open_audio(args.wav, args.save)
conn = a.Connection(a.npc_token(api), {"mode": "auto", "format": "pcm", "input_audio_format": "pcm"},
                    on_audio=speaker.write)

state = {"task": None, "seq": 0}
lock = threading.Lock()


def new_turn(interrupt=False):
    with lock:
        state["task"], state["seq"] = a.new_task_id(), 0
        body = {"type": "listen", "state": "start"}
        if interrupt:
            body["interrupt"] = True
        conn.send(a.LISTEN, json.dumps(body).encode(), state["task"])


def show():
    while True:
        t, tid, text = conn.events.get()
        if t is None:
            return
        if t == a.LISTEN:
            st = json.loads(text).get("state")
            if st == "detecting":          # 用户开始说话：停掉正在播的回复 / user started talking: stop playback
                speaker.stop()
            print(f"  [listen: {st}]")
        elif t == a.END and tid == state["task"]:
            new_turn()                     # 这一轮回复完了，开始下一轮 / reply finished, next turn
        else:
            a.print_event(t, text)


threading.Thread(target=show, daemon=True).start()
new_turn()
print("[listening — speak; Ctrl+C to quit]")

seconds = args.seconds or (mic.duration + 15 if args.wav else None)
stop_at = time.monotonic() + seconds if seconds else None
try:
    while not conn.closed.is_set() and (stop_at is None or time.monotonic() < stop_at):
        f = mic.read()
        with lock:
            conn.send(a.AUDIO, f, state["task"], state["seq"])
            state["seq"] += 1
except KeyboardInterrupt:
    pass
finally:
    conn.close()
    mic.close()
    speaker.close()
