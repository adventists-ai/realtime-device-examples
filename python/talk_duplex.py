"""全双工语音对话：角色一直在听，你随时说话就能打断它。
Full-duplex voice chat: the character listens all the time and you can interrupt it just by talking.

  pip install requests sounddevice
  export ADVENTISTS_API_KEY=sk-sophon-...
  python talk_duplex.py                       # 麦克风 + 扬声器 / microphone + speaker（建议戴耳机 / headphones recommended）
  python talk_duplex.py --wav question.wav --save reply.wav    # 用文件代替麦克风，回复存成文件 / file in, file out
  python talk_duplex.py --tools --emoji true   # 端侧设备常用：注册设备工具（MCP）+ 表情帧 / device tools + emoji frames
  python talk_duplex.py --image cup.jpg        # 让角色看一张图：问"我手里拿的是什么" / show the character a picture
  python talk_duplex.py --camera               # 视频通话：摄像头每秒 1 帧（pip install opencv-python）/ webcam, 1 frame per second
"""
import argparse
import threading
import time

import adventists as a

ap = argparse.ArgumentParser()
ap.add_argument("--wav", help="16 kHz mono wav instead of the microphone")
ap.add_argument("--save", help="save reply audio to this wav instead of playing it")
ap.add_argument("--engine", default="tag", choices=["tag", "flash", "e2e"])
ap.add_argument("--tools", action="store_true", help="register the demo device tools (MCP) from demo_tools.py")
ap.add_argument("--emoji", choices=["true", "dimi", "dimi2", "jfb"], help="emoji_mode: get EMOJI frames with replies")
ap.add_argument("--image", help="send this picture (any format, resized to 448 px JPEG) right after connecting; re-sent every 8 s")
ap.add_argument("--camera", action="store_true", help="video call: send one webcam frame per second (needs opencv-python)")
ap.add_argument("--seconds", type=float, help="stop after N seconds (default: wav length + 12 s, or until Ctrl+C)")
args = ap.parse_args()

api = a.Api()
mic, speaker = a.open_audio(args.wav, args.save)
params = {"mode": "duplex", "format": "pcm", "input_audio_format": "pcm", "engine": args.engine}
if args.emoji:
    params["emoji_mode"] = args.emoji
conn = a.Connection(a.npc_token(api), params, on_audio=speaker.write)
if args.tools:
    import demo_tools
    demo_tools.register(conn)

# 等服务端的 LISTEN start（整场只有这一次），之后才能推音频
# wait for the server's single LISTEN start before streaming
while True:
    t, _, text = conn.events.get(timeout=10)
    if t == a.LISTEN:
        break
    a.print_event(t, text)
print("[listening — just talk; Ctrl+C to quit]")

# 图片走同一条连接（上行 IMAGE 帧），夹在音频帧之间发 / images ride the same connection, interleaved with audio
images = a.ImageSender(conn)
picture = a.to_jpeg(open(args.image, "rb").read()) if args.image else None
camera = a.CameraInput() if args.camera else None
last_pic = 0.0


def show():
    while True:
        t, tid, text = conn.events.get()
        if t is None:
            return
        if t == a.MCP and args.tools:
            demo_tools.handle(conn, tid, text)      # 角色调用设备工具 / the character calls a device tool
        else:
            a.print_event(t, text)


threading.Thread(target=show, daemon=True).start()

seconds = args.seconds or (mic.duration + 12 if args.wav else None)
stop_at = time.monotonic() + seconds if seconds else None
seq = 0
try:
    # 一直推 60 ms 的帧，没人说话也推（静音），task_id 固定 duplex00
    # stream 60 ms frames forever, silence included; task_id is always duplex00
    while not conn.closed.is_set() and (stop_at is None or time.monotonic() < stop_at):
        conn.send(a.AUDIO, mic.read(), "duplex00", seq)
        seq += 1
        if picture and time.monotonic() - last_pic > 8:      # 每张图 10 秒内有效 / an image counts for 10 s
            images.add(picture); last_pic = time.monotonic()
        if camera:
            shot = camera.poll()
            if shot:
                images.add(shot)
        images.pump()
except KeyboardInterrupt:
    pass
finally:
    conn.close()
    mic.close()
    speaker.close()
    if camera:
        camera.close()
