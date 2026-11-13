"""Sophon Realtime API（裸模型，兼容 OpenAI Realtime 协议）：发一段录音，打印回复文字，保存回复音频。
Sophon Realtime API (bare model, OpenAI Realtime compatible): send a recording, print the reply, save its audio.

  pip install "websockets>=14" numpy soundfile
  export ADVENTISTS_API_KEY=sk-sophon-...
  python realtime_api.py question.wav [--model sophon-realtime-tag|sophon-realtime-flash|sophon-realtime-e2e]
"""
import argparse
import asyncio
import base64
import json
import os

import numpy as np
import soundfile as sf
import websockets

ap = argparse.ArgumentParser()
ap.add_argument("wav")
ap.add_argument("--model", default="sophon-realtime-tag")
ap.add_argument("--save", default="reply.wav")
args = ap.parse_args()

HOST = {"cn": "api.adventists.cn", "global": "api.adventists.ai"}[os.environ.get("ADVENTISTS_REGION", "cn")]
URL = f"wss://{HOST}/sophon/v1/realtime?model={args.model}"
KEY = os.environ["ADVENTISTS_API_KEY"]


async def main():
    x, sr = sf.read(args.wav, dtype="int16")
    if x.ndim > 1:
        x = x[:, 0]
    x = np.concatenate([x, np.zeros(sr * 6, np.int16)])          # 说完后继续推静音 / keep streaming silence
    out = []
    async with websockets.connect(URL, additional_headers={"Authorization": f"Bearer {KEY}"}, max_size=None) as ws:
        await ws.send(json.dumps({"type": "session.update", "session": {
            "voice": "chelsie", "input_audio_format": "pcm16", "output_audio_format": "pcm16",
            "turn_detection": {"type": "server_vad"}, "extra_body": {"language": "zh"}}}))

        async def receive():
            async for msg in ws:
                e = json.loads(msg)
                if e["type"] == "response.output_audio.delta":
                    out.append(np.frombuffer(base64.b64decode(e["delta"]), np.int16))
                elif e["type"] == "response.output_audio_transcript.delta":
                    print(e["delta"], end="", flush=True)
                elif e["type"] == "audio.cancelled":
                    out.clear()                                   # 被打断：丢掉排队的音频 / barge-in
                elif e["type"] == "error":
                    print("\nerror:", e["error"])

        rx = asyncio.create_task(receive())
        step = sr // 10                                           # 100 ms，按实时速度 / real time
        for i in range(0, len(x), step):
            await ws.send(json.dumps({"type": "input_audio_buffer.append",
                                      "audio": base64.b64encode(x[i:i + step].tobytes()).decode(),
                                      "sample_rate_hz": sr}))
            await asyncio.sleep(0.1)
        rx.cancel()
    print()
    if out:
        sf.write(args.save, np.concatenate(out), 24000)
        print(f"saved {args.save}")


asyncio.run(main())
