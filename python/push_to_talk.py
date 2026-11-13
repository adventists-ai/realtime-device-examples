"""按键说话（manual 模式）：按回车开始录音，再按回车结束；也可以直接打字。
Push-to-talk (manual mode): Enter to start recording, Enter again to stop; or just type a message.

  python push_to_talk.py                          # 交互 / interactive
  python push_to_talk.py --wav question.wav --save reply.wav    # 发一段录音 / send one recording
  python push_to_talk.py --text "讲个笑话" --save reply.wav      # 发一句文字 / send one text message
  python push_to_talk.py --speak "欢迎回家" --save hello.wav     # SPEAK：不经过模型，直接用角色音色念 / read verbatim
"""
import argparse
import threading
import wave

import adventists as a

ap = argparse.ArgumentParser()
ap.add_argument("--wav")
ap.add_argument("--text")
ap.add_argument("--speak")
ap.add_argument("--save")
ap.add_argument("--emoji", action="store_true", help="emoji_mode:true — get EMOJI frames with replies")
args = ap.parse_args()

api = a.Api()
speaker = a.WavOutput(args.save) if args.save else a.SpeakerOutput()
params = {"mode": "manual", "format": "pcm", "input_audio_format": "pcm"}
if args.emoji:
    params["emoji_mode"] = "true"
conn = a.Connection(a.npc_token(api), params, on_audio=speaker.write)


def wait_reply(task_id):
    """打印这一轮的识别结果和回复，直到 END / print transcript and reply until this turn's END."""
    while True:
        t, tid, text = conn.events.get(timeout=60)
        if t is None:
            return
        if t == a.END and tid == task_id:
            return
        a.print_event(t, text)


def send_audio(pcm: bytes):
    task = a.new_task_id()
    n = a.FRAME_BYTES
    chunks = [pcm[i:i + n] for i in range(0, len(pcm), n)]
    for seq, c in enumerate(chunks):
        conn.send(a.AUDIO, c, task, seq)
    conn.send(a.END, b"", task, len(chunks))      # 说完了 / end of utterance
    wait_reply(task)


def send_text(text: str):
    task = a.new_task_id()
    conn.send(a.TEXT, text.encode(), task, 0)
    conn.send(a.END, b"", task, 1)
    wait_reply(task)


def send_speak(text: str):
    task = a.new_task_id()
    conn.send(a.SPEAK, text.encode(), task, 0)
    wait_reply(task)


try:
    if args.wav:
        w = wave.open(args.wav)
        send_audio(w.readframes(w.getnframes()))
    elif args.text:
        send_text(args.text)
    elif args.speak:
        send_speak(args.speak)
    else:
        mic = a.MicInput()
        print("[Enter = start / stop recording; or type a message and press Enter; Ctrl+C to quit]")
        while True:
            line = input("> ").strip()
            if line:
                send_text(line)
                continue
            rec, stop = bytearray(), threading.Event()
            while not mic.q.empty():
                mic.q.get()

            def record():
                while not stop.is_set():
                    rec.extend(mic.read())

            th = threading.Thread(target=record)
            th.start()
            input("[recording… press Enter to send]")
            stop.set()
            th.join()
            speaker.stop()
            send_audio(bytes(rec))
except KeyboardInterrupt:
    pass
finally:
    conn.close()
    speaker.close()
