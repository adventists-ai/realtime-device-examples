"""会议模式：实时转写，结束后生成纪要。
Meeting mode: live transcription, then minutes when the meeting ends.

  python meeting.py --wav meeting.wav           # 用录音文件 / from a recording (16 kHz mono)
  python meeting.py                             # 用麦克风，Ctrl+C 结束会议 / microphone, Ctrl+C ends the meeting
  python meeting.py --lang zh --caption bilingual   # 实时字幕翻译成中文 / live captions translated to Chinese
"""
import argparse
import json
import threading
import time

import adventists as a

ap = argparse.ArgumentParser()
ap.add_argument("--wav")
ap.add_argument("--lang", help="caption target language, e.g. zh / en")
ap.add_argument("--caption", choices=["original", "translated", "bilingual"])
ap.add_argument("--topic", help="meeting topic / proper nouns (<=500 chars, no #)")
args = ap.parse_args()

api = a.Api()
mic = a.WavInput(args.wav) if args.wav else a.MicInput()
params = {"session_type": "meeting", "mode": "vad", "input_audio_format": "pcm", "device_id": "example-device"}
if args.lang:
    params["caption_target_lang"] = args.lang
if args.caption:
    params["caption_mode"] = args.caption
if args.topic:
    params["meeting_topic"] = args.topic
conn = a.Connection(a.npc_token(api), params)

# 等 meeting_started，拿到 meeting_id 后才能开始推音频 / wait for meeting_started before streaming
meeting_id = None
while meeting_id is None:
    t, _, text = conn.events.get(timeout=15)
    if t == a.TEXT and "meeting_started" in text:
        meeting_id = json.loads(text)["meeting_id"]
print(f"[meeting {meeting_id} started]")
task = a.new_task_id()
conn.send(a.LISTEN, b'{"state":"start"}', task)


def show():
    while True:
        t, _, text = conn.events.get()
        if t is None:
            return
        for tag in ("##TRANSCRIPT:", "##CAPTION_FINAL:"):
            if text.startswith(tag):
                d = json.loads(text[len(tag):])
                if tag == "##TRANSCRIPT:":
                    print(f"[{d.get('timestamp')}] {d.get('text')}")
                else:
                    print(f"    caption: {d.get('source_text')} | {d.get('translated_text')}")


threading.Thread(target=show, daemon=True).start()

seq = 0
stop_at = time.monotonic() + mic.duration + 6 if args.wav else None
try:
    while not conn.closed.is_set() and (stop_at is None or time.monotonic() < stop_at):
        conn.send(a.AUDIO, mic.read(), task, seq)
        seq += 1
except KeyboardInterrupt:
    pass
mic.close()

# 结束会议并生成纪要（幂等，可重复调用），然后轮询 / end the meeting, then poll for the minutes
print("[ending meeting, generating minutes…]")
api.post(f"/v2/meeting/{meeting_id}/stop-and-summarize")
deadline = time.monotonic() + 600
while time.monotonic() < deadline:
    s = api.get(f"/v2/meeting/{meeting_id}/summary")
    if s.get("status") in ("done", "failed"):
        print(s.get("summary") or s)
        break
    time.sleep(5)
conn.close()
