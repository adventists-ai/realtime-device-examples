"""最简接入：建角色 → 拿令牌 → 全双工连上 → 推一段录音 → 存下回复。只依赖 requests，不需要麦克风。
The smallest integration: create a character, get a token, connect, send a recording, save the reply. Needs only requests.

  pip install requests
  export ADVENTISTS_API_KEY=sk-sophon-...
  python quickstart.py question_16k_mono.wav       # 输出 reply.wav / writes reply.wav
"""
import os
import socket
import sys
import threading
import time
import wave

import requests

REGION = os.environ.get("ADVENTISTS_REGION", "cn")
BASE = {"cn": "https://api.adventists.cn", "global": "https://api.adventists.ai"}[REGION]
TCP = {"cn": ("api.adventists.cn", 8009), "global": ("203.208.134.27", 8009)}[REGION]
H = {"Authorization": f"Bearer {os.environ['ADVENTISTS_API_KEY']}"}

npc = requests.post(f"{BASE}/v2/init", headers=H, json={}).json()["data"]                  # 1. 建角色
token = requests.post(f"{BASE}/v2/login", headers=H, data={"npcid": npc}).json()["token"]  # 2. 拿令牌（4 小时）


def frame(t, payload, tid=b"duplex00", seq=0):
    return b"##START" + bytes([t]) + tid + f"{seq % 10000:04d}".encode() + payload + b"##END"


s = socket.create_connection(TCP)                                                          # 3. 连接并认证
s.sendall(frame(1, f"{token}##mode:duplex##format:pcm##input_audio_format:pcm##engine:tag".encode(), b"00000000"))

listening, reply = threading.Event(), bytearray()


def reader():
    buf = b""
    while (d := s.recv(65536)):
        buf += d
        while (i := buf.find(b"##START")) >= 0 and (j := buf.find(b"##END", i + 20)) >= 0:
            t, body, buf = buf[i + 7], buf[i + 20:j], buf[j + 5:]
            if t == 2:
                reply.extend(body)                                      # AUDIO: 16 kHz PCM16
            elif t == 8:
                listening.set()                                         # LISTEN start
            elif t in (4, 5):
                print(t, body.decode(errors="replace"))                 # TEXT / STATUS


threading.Thread(target=reader, daemon=True).start()
assert listening.wait(10), "no LISTEN start"

w = wave.open(sys.argv[1] if len(sys.argv) > 1 else "question_16k_mono.wav")             # 4. 按实时速度推音频
pcm = w.readframes(w.getnframes())
n = 1920                                                                # 60 ms x 16 kHz x 2 bytes
frames = [b"\0" * n] * 16 + [pcm[i:i + n].ljust(n, b"\0") for i in range(0, len(pcm), n)] + [b"\0" * n] * 150
for k, f in enumerate(frames):                                          # 一直推，包括静音 / keep sending, silence included
    s.sendall(frame(2, f, seq=k))
    time.sleep(0.06)

s.sendall(frame(5, b"##DISCONNECT", b"00000000"))
time.sleep(1)
with wave.open("reply.wav", "wb") as o:
    o.setnchannels(1)
    o.setsampwidth(2)
    o.setframerate(16000)
    o.writeframes(bytes(reply))
requests.post(f"{BASE}/v2/npc", headers=H, json={"action": "delete_npc", "npcid": npc})  # 示例用完就删 / clean up
print(f"reply.wav: {len(reply) / 32000:.1f} s")
