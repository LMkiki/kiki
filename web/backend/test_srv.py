from fastapi import FastAPI
from dialog_engine import DialogEngine
import uvicorn

app = FastAPI()
engine = DialogEngine()

@app.get("/test")
def test():
    import uuid
    sid = uuid.uuid4().hex
    r1, s1, f1 = engine.handle_message(sid, "")
    r2, s2, f2 = engine.handle_message(sid, "浙A12345")
    info = engine.get_session_info(sid)
    return {
        "step1": {"state": s1, "reply": r1},
        "step2": {"state": s2, "reply": r2},
        "info": info["info"],
        "session_state": info["state"],
    }

if __name__ == "__main__":
    uvicorn.run("test_srv:app", host="0.0.0.0", port=8001)
