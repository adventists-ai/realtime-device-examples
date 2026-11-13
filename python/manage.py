"""HTTP 管理接口走一遍：模板 → 角色 → 记忆 → 推送 → 用量 → 清理。
A tour of the HTTP APIs: template → character → memory → push → usage → cleanup.

  python manage.py
"""
import json
import time

import adventists as a

api = a.Api()


def show(title, data):
    print(f"\n== {title}\n{json.dumps(data, ensure_ascii=False)[:300]}")


# 1. 创建模板（必填：name person style emotion_system mbti_type love_type）/ create a template
tpl = api.post("/v2/template", json={
    "action": "create_template", "name": "小安", "mbti_type": "ENFJ", "love_type": "Virgo",
    "person": "你是一个陪伴型桌面机器人，住在用户的书桌上。", "style": "简短、亲切、偶尔幽默",
    "emotion_system": "被夸奖时开心，被冷落时有点委屈", "start_speech": "你好呀，我是小安！", "temp": "0.5",
    "functions": ["get_weather"], "hotword": "小安"})
templateid = tpl["data"]["templateid"] if isinstance(tpl["data"], dict) else tpl["data"]
show("create_template", tpl)

# 2. 模板记忆：之后从这个模板创建的角色都会带上 / template memory, inherited by new characters
show("save_template_memory", api.post("/v2/template", json={
    "action": "save_template_memory", "templateid": templateid,
    "new_user_entry": "你的生日是哪天？", "new_assistant_entry": "我是 3 月 14 日被组装好的，跟圆周率同一天！"}))

# 3. 每个用户 / 设备创建一个角色 / one character per user or device
npcid = api.create_npc(templateid)
show("init (character from template)", npcid)

# 4. 修改这个角色（只影响它自己）/ customize this character only
show("modify_npc", api.post("/v2/npc", json={"action": "modify_npc", "npcid": npcid, "style": "说话带一点东北口音"}))

# 5. 写入、读取记忆 / write and read memory
api.post(f"/hippo/api/memory/{npcid}", json={"user_content": "我叫小明，喜欢游泳", "assistant_content": "记住啦，小明！", "timestamp": ""})
show("hippo memory", api.get(f"/hippo/api/memory/{npcid}", params={"page_size": 5}))

# 6. 给设备推一条播报（设备离线时会排队，上线后送达）/ push an announcement (queued while offline)
show("push", api.post("/push/api/push", json={"npcid": npcid, "type": "speak", "payload": {"text": "该喝水啦"}}))

# 7. 最近 7 天用量 / last 7 days of usage
now = int(time.time() * 1000)
show("statistics", api.get("/v2/statistics", params={"startTime": now - 7 * 86400000, "endTime": now, "granularity": "DAILY"}))

# 8. 清理 / cleanup
api.delete_npc(npcid)
api.post("/v2/template", json={"action": "delete_template", "templateid": templateid})
print("\n[cleaned up]")
