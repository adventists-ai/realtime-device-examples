"""Adventists Harness 最小客户端 / minimal client.

Python 3.9+，依赖 requests；用麦克风 / 扬声器时另需 sounddevice。
Python 3.9+, needs requests; sounddevice only for microphone / speaker.

环境变量 / environment:
  ADVENTISTS_API_KEY   控制台创建的 key（sk-sophon-…）/ key from the console
  ADVENTISTS_REGION    cn（默认，国内）或 global（海外）/ cn (default) or global
"""
from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
import uuid
import wave

import requests

REGIONS = {
    "cn":     {"http": "https://api.adventists.cn", "tcp": ("api.adventists.cn", 8009), "ws": "wss://api.adventists.cn/ws-beta"},
    "global": {"http": "https://api.adventists.ai", "tcp": ("203.208.134.27", 8009), "ws": "wss://api.adventists.ai/ws-beta"},
}

# 消息类型 / message types
AUTH, AUDIO, END, TEXT, STATUS, MCP, SPEAK, LISTEN, EMOJI, IMAGE = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10

RATE = 16000                 # 16 kHz, mono, PCM16
FRAME_MS = 60
FRAME_BYTES = RATE * FRAME_MS // 1000 * 2      # 1920 bytes = 60 ms


def region() -> dict:
    name = os.environ.get("ADVENTISTS_REGION", "cn")
    if name not in REGIONS:
        raise SystemExit(f"ADVENTISTS_REGION must be one of {list(REGIONS)}")
    return REGIONS[name]


# ---------------------------------------------------------------- HTTP
class Api:
    """HTTP 接口。所有请求都带 Authorization: Bearer <key>。"""

    def __init__(self, key: str | None = None, base: str | None = None):
        self.key = key or os.environ.get("ADVENTISTS_API_KEY")
        if not self.key:
            raise SystemExit("set ADVENTISTS_API_KEY (create one at https://api.adventists.cn/console/)")
        self.base = (base or region()["http"]).rstrip("/")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.key}"

    def request(self, method: str, path: str, **kw):
        r = self.s.request(method, self.base + path, timeout=60, **kw)
        try:
            body = r.json()
        except ValueError:
            body = r.content
        if r.status_code >= 400 or (isinstance(body, dict) and str(body.get("status", "")).lower() == "failure"):
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {body}")
        return body

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    # 常用 / common calls
    def create_npc(self, templateid: str | None = None, **fields) -> str:
        body = dict(fields)
        if templateid:
            body["templateid"] = templateid
        return self.post("/v2/init", json=body)["data"]

    def delete_npc(self, npcid: str):
        return self.post("/v2/npc", json={"action": "delete_npc", "npcid": npcid})

    def token(self, npcid: str) -> str:
        """TCP / WebSocket 令牌，4 小时有效 / token for TCP or WebSocket, valid for 4 hours."""
        return self.post("/v2/login", data={"npcid": npcid})["token"]


# ---------------------------------------------------------------- frames
def frame(msg_type: int, payload: bytes = b"", task_id: str = "00000000", seq: int = 0) -> bytes:
    tid = task_id.encode()
    assert len(tid) == 8, "task_id must be exactly 8 bytes"
    return b"##START" + bytes([msg_type]) + tid + f"{seq % 10000:04d}".encode() + payload + b"##END"


class FrameParser:
    """把 TCP 字节流切成帧 / split a byte stream into frames: (type, task_id, seq, payload)."""

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(b"##START")
            if i < 0:
                self.buf = self.buf[-6:]
                break
            j = self.buf.find(b"##END", i + 20)
            if j < 0:
                self.buf = self.buf[i:]
                break
            h = self.buf[i + 7:i + 20]
            out.append((h[0], h[1:9].decode(errors="replace"), h[9:13].decode(errors="replace"), self.buf[i + 20:j]))
            self.buf = self.buf[j + 5:]
        return out


def new_task_id() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- TCP
class Connection:
    """一条 TCP 会话。收到的帧放进 self.events 队列；音频交给 on_audio 回调。

    One TCP session. Incoming frames go to self.events; audio goes to on_audio.
    """

    def __init__(self, token: str, params: dict | None = None, address=None, on_audio=None):
        self.sock = socket.create_connection(address or region()["tcp"], timeout=15)
        self.sock.settimeout(None)
        self.events: queue.Queue = queue.Queue()
        self.on_audio = on_audio or (lambda b: None)
        self.npcid = None
        self.closed = threading.Event()
        self._authed = threading.Event()
        self._auth_error = None
        self._lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()
        args = "".join(f"##{k}:{v}" for k, v in (params or {}).items())
        self.send(AUTH, (token + args).encode())
        if not self._authed.wait(10) or self._auth_error:
            raise RuntimeError(f"auth failed: {self._auth_error or 'timeout'}")

    def send(self, msg_type: int, payload: bytes = b"", task_id: str = "00000000", seq: int = 0):
        with self._lock:
            self.sock.sendall(frame(msg_type, payload, task_id, seq))

    def _reader(self):
        p = FrameParser()
        try:
            while True:
                data = self.sock.recv(65536)
                if not data:
                    break
                for t, tid, seq, body in p.feed(data):
                    if t == AUDIO:
                        self.on_audio(body)
                        continue
                    text = body.decode(errors="replace")
                    if t == STATUS and not self._authed.is_set():
                        if "NPCID" in text:
                            self.npcid = text.split("NPCID:")[1].split(",")[0].strip()
                            self._authed.set()
                        elif text.startswith("##ERROR"):
                            self._auth_error = text
                            self._authed.set()
                    self.events.put((t, tid, text))
        except OSError:
            pass
        finally:
            self.closed.set()
            self.events.put((None, "", ""))

    def close(self):
        try:
            self.send(STATUS, b"##DISCONNECT")
            time.sleep(0.5)
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- images (duplex)
IMAGE_CHUNK = 1012          # 每片最多 1012 字节 / at most 1012 bytes per chunk


def image_chunks(jpeg: bytes, image_no: int) -> list[tuple[str, int, bytes]]:
    """把一张 JPEG 切成上行 IMAGE 帧的分片：同一张图同一个 task_id，seq 递增，最后一片以 FF D9 结尾。

    Split one JPEG into uplink IMAGE frame chunks: one task_id per image, seq counting up, the last chunk ends with FF D9.
    Interleave the chunks between audio frames (see ImageSender) so they never hold up the audio.
    """
    if not (jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9")):
        raise ValueError("not a complete JPEG")
    tid = f"img{image_no % 100000:05d}"
    return [(tid, k, jpeg[i:i + IMAGE_CHUNK]) for k, i in enumerate(range(0, len(jpeg), IMAGE_CHUNK))]


def to_jpeg(data: bytes, max_side: int = 448, quality: int = 70) -> bytes:
    """缩到长边 448 px、质量 70（约 20–40 KB）；需要 Pillow / resize to 448 px, quality 70 (needs Pillow)."""
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((max_side, max_side))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()


class ImageSender:
    """排队要发的图，每推一帧音频就顺带发 2 片，不会一口气挤住上行。

    Queues images and sends two chunks after each audio frame, so images never block the uplink audio.
    """

    def __init__(self, conn: "Connection"):
        self.conn = conn
        self.pending: list[tuple[str, int, bytes]] = []
        self.n = 0
        self.lock = threading.Lock()

    def add(self, jpeg: bytes):
        with self.lock:
            self.n += 1
            self.pending = image_chunks(jpeg, self.n)      # 只留最新一张 / keep only the newest image

    def pump(self, per_frame: int = 2):
        with self.lock:
            out, self.pending = self.pending[:per_frame], self.pending[per_frame:]
        for tid, seq, chunk in out:
            self.conn.send(IMAGE, chunk, tid, seq)


class CameraInput:
    """摄像头，每 interval 秒取一张 JPEG；需要 opencv-python / webcam, one JPEG every interval seconds (needs opencv-python)."""

    def __init__(self, index: int = 0, interval: float = 1.0):
        import cv2
        self.cv2, self.cap, self.interval, self.t = cv2, cv2.VideoCapture(index), interval, 0.0

    def poll(self) -> bytes | None:
        if time.monotonic() - self.t < self.interval:
            return None
        self.t = time.monotonic()
        ok, img = self.cap.read()
        if not ok:
            return None
        h, w = img.shape[:2]
        k = 448 / max(h, w)
        if k < 1:
            img = self.cv2.resize(img, (int(w * k), int(h * k)))
        ok, buf = self.cv2.imencode(".jpg", img, [self.cv2.IMWRITE_JPEG_QUALITY, 70])
        return buf.tobytes() if ok else None

    def close(self):
        self.cap.release()


# ---------------------------------------------------------------- audio in / out
class WavInput:
    """用 wav 文件模拟麦克风：先静音，再按实时速度放文件，之后一直给静音。

    Simulates a microphone from a wav file (16 kHz mono PCM16): silence, the file in real time, then silence forever.
    """

    def __init__(self, path: str, lead_s: float = 1.0):
        w = wave.open(path)
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (RATE, 1, 2):
            raise SystemExit("wav must be 16 kHz, mono, 16-bit")
        pcm = w.readframes(w.getnframes())
        silence = b"\0" * FRAME_BYTES
        self.frames = [silence] * int(lead_s * 1000 / FRAME_MS) + \
                      [pcm[i:i + FRAME_BYTES].ljust(FRAME_BYTES, b"\0") for i in range(0, len(pcm), FRAME_BYTES)]
        self.duration = len(self.frames) * FRAME_MS / 1000
        self.i, self.t0 = 0, None

    def read(self) -> bytes:
        """阻塞到下一个 60 ms / blocks until the next 60 ms frame is due."""
        if self.t0 is None:
            self.t0 = time.monotonic()
        due = self.t0 + self.i * FRAME_MS / 1000
        time.sleep(max(0.0, due - time.monotonic()))
        f = self.frames[self.i] if self.i < len(self.frames) else b"\0" * FRAME_BYTES
        self.i += 1
        return f

    def close(self):
        pass


class MicInput:
    """麦克风，每次 read() 返回 60 ms PCM16 / microphone; read() returns 60 ms of PCM16."""

    def __init__(self):
        import sounddevice as sd
        self.q: queue.Queue = queue.Queue()
        self.stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                        blocksize=FRAME_BYTES // 2, callback=lambda d, n, t, s: self.q.put(bytes(d)))
        self.stream.start()

    def read(self) -> bytes:
        return self.q.get()

    def close(self):
        self.stream.stop()
        self.stream.close()


class SpeakerOutput:
    """扬声器；stop() 立即清掉没播完的音频（打断用）/ speaker; stop() drops queued audio (for barge-in)."""

    def __init__(self):
        import sounddevice as sd
        self.buf = bytearray()
        self.lock = threading.Lock()

        def cb(out, n, t, s):
            want = n * 2
            with self.lock:
                chunk = bytes(self.buf[:want])
                del self.buf[:want]
            out[:] = chunk.ljust(want, b"\0")

        self.stream = sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", callback=cb)
        self.stream.start()

    def write(self, pcm: bytes):
        with self.lock:
            self.buf.extend(pcm)

    def stop(self):
        with self.lock:
            self.buf.clear()

    def close(self):
        self.stream.stop()
        self.stream.close()


class WavOutput:
    """把收到的音频存成 wav（测试用）/ save received audio to a wav file (for testing)."""

    def __init__(self, path: str):
        self.path, self.buf = path, bytearray()

    def write(self, pcm: bytes):
        self.buf.extend(pcm)

    def stop(self):
        pass

    def close(self):
        with wave.open(self.path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(self.buf))
        print(f"[saved {len(self.buf) / RATE / 2:.1f} s of reply audio to {self.path}]")


def open_audio(wav_in: str | None, wav_out: str | None):
    """--wav 给了就用文件，否则用麦克风和扬声器 / file if given, else microphone and speaker."""
    return (WavInput(wav_in) if wav_in else MicInput()), (WavOutput(wav_out) if wav_out else SpeakerOutput())


def get_npc(api: Api, cache: str = ".npcid") -> str:
    """每台设备 / 每个用户一个角色；第一次创建后存在本地文件里复用。

    One character per device / user: create it once and reuse it (stored in a local file).
    """
    if os.path.exists(cache):
        return open(cache).read().strip()
    npcid = api.create_npc()
    open(cache, "w").write(npcid)
    print(f"[created character {npcid}]")
    return npcid


def npc_token(api: Api, cache: str = ".npcid") -> str:
    """拿本地角色的令牌；角色已被删除（404）就重新创建一个。/ token for the cached character; recreate it if it was deleted."""
    try:
        return api.token(get_npc(api, cache))
    except RuntimeError as e:
        if "404" not in str(e):
            raise
        os.remove(cache)
        return api.token(get_npc(api, cache))


def print_event(t, text):
    if t == TEXT:
        print(f"  AI: {text}")
    elif t == STATUS and text.startswith("##INFO:prompt:"):
        print(f"YOU: {text[len('##INFO:prompt:'):].strip()}")
    elif t == STATUS and text.startswith("##INFO:MCP"):
        print(f"  [{text[7:]}]")
    elif t == STATUS and text.startswith("##ERROR"):
        print(f"[error] {text}")
    elif t == EMOJI:
        print(f"  [emoji] {json.loads(text).get('emoji')}")
    elif t == IMAGE:
        print(f"  [image] {json.loads(text).get('url')}")
