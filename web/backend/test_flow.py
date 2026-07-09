import urllib.request, json

BASE = "http://127.0.0.1:8000"

def api(path, data=None):
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    req.add_header("Content-Type", "application/json") if data else None
    return json.loads(urllib.request.urlopen(req).read())

def admin_api(path, method="GET"):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("X-Admin-Token", "123456")
    return json.loads(urllib.request.urlopen(req).read())

# === 测试1: 完整受理流程 ===
print("=" * 50)
print("测试1: 正常受理")
r = api("/api/chat/session")
sid = r["data"]["session_id"]
print(f"创建会话: {sid}")

r = api("/api/chat/message", {"session_id": sid, "content": "浙A12345"})
print(f"车牌: {r['data']['status']} [{r['data']['reply'][:20]}...]")

r = api("/api/chat/message", {"session_id": sid, "content": "是的"})
print(f"确认: {r['data']['status']} [{r['data']['reply'][:20]}...]")

r = api("/api/chat/message", {"session_id": sid, "content": "蓝牌"})
print(f"颜色: {r['data']['status']} [{r['data']['reply'][:20]}...]")

r = api("/api/chat/message", {"session_id": sid, "content": "杭州市西湖区"})
print(f"地址: {r['data']['status']} [{r['data']['reply'][:20]}...]")

r = api("/api/chat/message", {"session_id": sid, "content": "挡住我车了"})
print(f"原因受理: {r['data']['status']} finished={r['data']['is_finished']}")

# === 测试2: 交通事故 ===
print("\n" + "=" * 50)
print("测试2: 交通事故")
r = api("/api/chat/session")
sid2 = r["data"]["session_id"]
api("/api/chat/message", {"session_id": sid2, "content": "浙B66666"})
api("/api/chat/message", {"session_id": sid2, "content": "是的"})
api("/api/chat/message", {"session_id": sid2, "content": "是的"})
api("/api/chat/message", {"session_id": sid2, "content": "宁波市海曙区"})
r = api("/api/chat/message", {"session_id": sid2, "content": "他撞了我的车"})
print(f"事故: {r['data']['status']} {r['data']['reply'][:30]}...")

# === 测试3: 非浙牌 ===
print("\n" + "=" * 50)
print("测试3: 非浙牌")
r = api("/api/chat/session")
sid3 = r["data"]["session_id"]
r = api("/api/chat/message", {"session_id": sid3, "content": "沪A12345"})
print(f"非浙牌: {r['data']['status']}")

# === 测试4: 转人工 ===
print("\n" + "=" * 50)
print("测试4: 转人工")
r = api("/api/chat/session")
sid4 = r["data"]["session_id"]
api("/api/chat/message", {"session_id": sid4, "content": "浙D12345"})
r = api("/api/chat/message", {"session_id": sid4, "content": "转人工"})
print(f"转人工: {r['data']['status']}")

# === 测试5: 管理后台接口 ===
print("\n" + "=" * 50)
print("测试5: 管理后台")
try:
    r = admin_api("/api/admin/sessions?page=1&page_size=5")
    print(f"会话列表: total={r['data']['total']}")
except Exception as e:
    print(f"管理接口出错: {e}")

print("\n" + "=" * 50)
print("全部测试完成!")
