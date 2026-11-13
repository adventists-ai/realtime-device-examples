# Adventists 示例代码 / Examples

接入 Harness（带人设、记忆、工具的角色 + 设备实时语音）和 Sophon Realtime API 的示例。所有示例都在国内和海外两个入口实测过。

Examples for Harness (characters with persona, memory and tools, plus realtime device voice) and the Sophon Realtime API. Every example has been run against both the China and global endpoints.

文档 / Docs: https://api.adventists.cn/console/docs/harness · https://api.adventists.ai/console/docs/harness?lang=en

## 准备 / Setup

```bash
pip install requests                 # 所有示例 / all examples
pip install sounddevice              # 用麦克风和扬声器时 / for microphone and speaker
pip install pillow                   # 发图片时 / for sending images (opencv-python for --camera)
export ADVENTISTS_API_KEY=sk-sophon-...    # 在控制台创建 / create one in the console
export ADVENTISTS_REGION=cn                # cn（国内，默认）或 global（海外）/ cn (default) or global
```

key 只能放在服务端或你自己的电脑上，不要写进 App、网页或设备固件。设备和浏览器只用 `/v2/login` 换来的令牌。

Keep the key on your server or your own machine; never ship it in an app, web page or firmware. Devices and browsers only use the token from `/v2/login`.

音频统一是 16 kHz、单声道、16 bit PCM。带 `--wav` 参数时用文件代替麦克风，带 `--save` 时把回复存成文件、不播放，方便在没有声卡的服务器上测试。

Audio is always 16 kHz mono 16-bit PCM. `--wav` replaces the microphone with a file and `--save` writes the reply to a file instead of playing it, which is handy on servers without a sound card.

## Python（`python/`）

| 文件 / File | 内容 / What it shows |
|---|---|
| `quickstart.py` | 最简接入，只依赖 requests：建角色 → 拿令牌 → 全双工连接 → 推一段录音 → 存下回复 / smallest integration, requests only |
| `talk_duplex.py` | 全双工对话（推荐）：一直在听，随时打断；`--tools` 注册设备工具（MCP），`--emoji true` 收表情帧，`--image` / `--camera` 让角色看见（上行图片帧）/ full-duplex chat (recommended); `--tools` device tools (MCP), `--emoji true` emoji frames, `--image` / `--camera` let the character see (uplink image frames) |
| `talk_vad.py` | 自动（VAD）模式：每轮发 LISTEN start，收到 detecting 时停止播放 / auto (VAD) mode with barge-in |
| `push_to_talk.py` | 按键说话（manual）、文字输入、SPEAK、表情 / push-to-talk, text input, SPEAK, emoji |
| `device_tools.py` | 设备工具（MCP），文字对话版：注册开灯、查电量，角色对话中调用 / device tools (MCP), text chat |
| `demo_tools.py` | 示例工具定义和处理（注册、执行、回结果），换成你的设备逻辑即可 / tool definitions and handler; plug in your device logic |
| `meeting.py` | 会议模式：实时转写和字幕，结束后生成纪要 / meeting mode: live transcript, captions, minutes |
| `manage.py` | HTTP 接口走一遍：模板、角色、记忆、推送、用量 / tour of the HTTP APIs |
| `realtime_api.py` | Sophon Realtime API（裸模型，兼容 OpenAI Realtime）/ the bare-model Realtime API |
| `adventists.py` | 上面几个示例共用的小客户端：帧编解码、TCP 连接、音频输入输出 / shared mini client |

```bash
cd python
python talk_duplex.py                                   # 戴上耳机直接说话 / put on headphones and talk
python talk_duplex.py --wav question.wav --save reply.wav
python talk_duplex.py --tools --emoji true            # 端侧设备常用组合 / typical device setup
python talk_duplex.py --image cup.jpg                 # 让角色看一张图 / show the character a picture
pip install opencv-python pillow && python talk_duplex.py --camera   # 视频通话，每秒 1 帧 / video call, 1 frame per second
python push_to_talk.py --text "讲个笑话" --save reply.wav
python device_tools.py --say "帮我把客厅的灯关掉"
python meeting.py --wav meeting.wav --lang zh --caption bilingual
pip install "websockets>=14" numpy soundfile && python realtime_api.py question.wav
```

示例第一次运行时会创建一个角色，把 npcid 存在当前目录的 `.npcid` 里复用。正式产品里请给每个用户或每台设备各建一个角色。

On first run the examples create a character and keep its npcid in `.npcid`. In production create one character per user or device.

## 浏览器 / Browser（`web/`）

`server.py` 是一个很小的后端：key 留在服务端，浏览器向它要令牌；`index.html` 用 WebSocket 连 Harness，麦克风采集、实时播放、显示文字。App 接入也是同样的结构。

`server.py` is a tiny backend that keeps the key and hands the browser a token; `index.html` connects to Harness over WebSocket with microphone capture, playback and transcripts. Apps follow the same pattern.

```bash
cd web
python server.py           # 打开 / open http://localhost:8000
```

## 接入地址 / Endpoints

| | 国内 / China | 海外 / Global |
|---|---|---|
| HTTP | `https://api.adventists.cn` | `https://api.adventists.ai` |
| TCP | `api.adventists.cn:8009` | `203.208.134.27:8009` |
| WebSocket | `wss://api.adventists.cn/ws-beta` | `wss://api.adventists.ai/ws-beta` |
| Realtime API | `wss://api.adventists.cn/sophon/v1/realtime` | `wss://api.adventists.ai/sophon/v1/realtime` |

## License

MIT
