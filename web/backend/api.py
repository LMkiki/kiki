import os
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session as DBSession

from dialog_engine import DialogEngine, ACCEPTED, REJECTED, TRANSFER_HUMAN
from database import get_session_factory
from models import Session as SessionModel, Message, MoveCarApply, TestCase

app = FastAPI()

_engine = DialogEngine()
_db_factory = get_session_factory()

STATE_STATUS_MAP = {
    "INIT": 0, "WAIT_PLATE": 1, "CONFIRM_PLATE": 2, "WAIT_COLOR": 3,
    "WAIT_ADDRESS": 4, "WAIT_REASON": 5, "VERIFYING": 6,
    "ACCEPTED": 7, "REJECTED": 8, "TRANSFER_HUMAN": 9,
}

PLATE_COLOR_MAP = {
    "蓝牌": 1, "绿牌": 2, "黄牌": 3, "白牌": 4, "黑牌": 5,
}

COLOR_CODE_MAP = {v: k for k, v in PLATE_COLOR_MAP.items()}


def resp(data=None, message="success"):
    return {"code": 0, "message": message, "data": data or {}}


def err_resp(message, code=-1):
    return {"code": code, "message": message, "data": {}}


def get_db():
    db = _db_factory()
    try:
        yield db
    finally:
        db.close()


def verify_admin(x_admin_token: str = Header(None)):
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token or x_admin_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ---------- request models ----------

class MessageRequest(BaseModel):
    session_id: str
    content: str

class CreateTestCaseRequest(BaseModel):
    case_name: str
    input_content: str
    expect_reply: str = None
    expect_status: int = None

class UpdateTestCaseRequest(BaseModel):
    case_name: str = None
    input_content: str = None
    expect_reply: str = None
    expect_status: int = None


# ---------- helpers ----------

def _handle_finished(db, session_id, status_str, engine_session, db_session):
    info = engine_session.get("info", {})
    now = datetime.now()
    db_session.ended_at = now

    if status_str == ACCEPTED:
        db_session.end_reason = "受理成功"
    elif status_str == REJECTED:
        db_session.end_reason = db_session.end_reason or "不予受理"
    elif status_str == TRANSFER_HUMAN:
        db_session.end_reason = "转人工处理"

    if status_str in (ACCEPTED, REJECTED, TRANSFER_HUMAN):
        plate_no = info.get("plate_number") or ""
        plate_color_str = info.get("plate_color") or ""
        apply = MoveCarApply(
            session_id=session_id,
            plate_number=plate_no,
            plate_color=PLATE_COLOR_MAP.get(plate_color_str, 0),
            address=info.get("address") or "",
            reason=info.get("reason") or "",
            accept_status=STATE_STATUS_MAP.get(status_str, 0),
        )
        db.add(apply)


def _session_to_dict(s):
    return {
        "session_id": s.session_id,
        "status": s.status,
        "end_reason": s.end_reason,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
    }


def _msg_to_dict(m):
    return {
        "id": m.id,
        "session_id": m.session_id,
        "sender_type": m.sender_type,
        "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _apply_to_dict(a):
    return {
        "id": a.id,
        "session_id": a.session_id,
        "plate_number": a.plate_number,
        "plate_color": a.plate_color,
        "address": a.address,
        "reason": a.reason,
        "accept_status": a.accept_status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _test_case_to_dict(t):
    return {
        "id": t.id,
        "case_name": t.case_name,
        "input_content": t.input_content,
        "expect_reply": t.expect_reply,
        "expect_status": t.expect_status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ---------- C 端对话接口 ----------

@app.post("/api/chat/session")
def create_session(db: DBSession = Depends(get_db)):
    session_id = uuid4().hex
    reply, _, _ = _engine.handle_message(session_id, "")
    s = SessionModel(session_id=session_id, status=STATE_STATUS_MAP.get("WAIT_PLATE", 1))
    db.add(s)
    db.commit()
    return resp({"session_id": session_id, "reply": reply})


@app.post("/api/chat/message")
def send_message(body: MessageRequest, db: DBSession = Depends(get_db)):
    db_session = db.query(SessionModel).filter(SessionModel.session_id == body.session_id).first()
    if not db_session:
        return err_resp("会话不存在")

    user_msg = Message(session_id=body.session_id, sender_type=1, content=body.content)
    db.add(user_msg)

    reply, status_str, is_finished = _engine.handle_message(body.session_id, body.content)

    sys_msg = Message(session_id=body.session_id, sender_type=2, content=reply)
    db.add(sys_msg)

    db_session.status = STATE_STATUS_MAP.get(status_str, 0)

    if is_finished:
        engine_session = _engine.get_session_info(body.session_id)
        if engine_session:
            _handle_finished(db, body.session_id, status_str, engine_session, db_session)

    db.commit()
    return resp({
        "reply": reply,
        "status": status_str,
        "is_finished": is_finished,
    })


# ---------- B 端管理接口 ----------

@app.get("/api/admin/sessions")
def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: int = Query(None),
    start_time: str = Query(None),
    end_time: str = Query(None),
    plate_number: str = Query(None),
    _=Depends(verify_admin),
    db: DBSession = Depends(get_db),
):
    q = db.query(SessionModel)
    if status is not None:
        q = q.filter(SessionModel.status == status)
    if start_time:
        q = q.filter(SessionModel.created_at >= datetime.fromisoformat(start_time))
    if end_time:
        q = q.filter(SessionModel.created_at <= datetime.fromisoformat(end_time))
    if plate_number:
        q = q.join(MoveCarApply).filter(MoveCarApply.plate_number == plate_number)

    total = q.count()
    items = q.order_by(desc(SessionModel.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return resp({
        "items": [_session_to_dict(s) for s in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@app.get("/api/admin/sessions/{session_id}")
def get_session_detail(session_id: str, _=Depends(verify_admin), db: DBSession = Depends(get_db)):
    s = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
    if not s:
        return err_resp("会话不存在")

    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.created_at).all()
    apply = db.query(MoveCarApply).filter(MoveCarApply.session_id == session_id).first()

    data = _session_to_dict(s)
    data["messages"] = [_msg_to_dict(m) for m in messages]
    data["move_car_apply"] = _apply_to_dict(apply) if apply else None
    return resp(data)


@app.get("/api/admin/test-cases")
def list_test_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _=Depends(verify_admin),
    db: DBSession = Depends(get_db),
):
    total = db.query(TestCase).count()
    items = db.query(TestCase).order_by(desc(TestCase.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return resp({
        "items": [_test_case_to_dict(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@app.post("/api/admin/test-cases")
def create_test_case(body: CreateTestCaseRequest, _=Depends(verify_admin), db: DBSession = Depends(get_db)):
    t = TestCase(
        case_name=body.case_name,
        input_content=body.input_content,
        expect_reply=body.expect_reply,
        expect_status=body.expect_status,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return resp(_test_case_to_dict(t))


@app.put("/api/admin/test-cases/{case_id}")
def update_test_case(case_id: int, body: UpdateTestCaseRequest, _=Depends(verify_admin), db: DBSession = Depends(get_db)):
    t = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not t:
        return err_resp("测试用例不存在")

    update_data = {}
    if body.case_name is not None:
        update_data["case_name"] = body.case_name
    if body.input_content is not None:
        update_data["input_content"] = body.input_content
    if body.expect_reply is not None:
        update_data["expect_reply"] = body.expect_reply
    if body.expect_status is not None:
        update_data["expect_status"] = body.expect_status

    if update_data:
        db.query(TestCase).filter(TestCase.id == case_id).update(update_data)
        db.commit()
    db.refresh(t)
    return resp(_test_case_to_dict(t))


@app.delete("/api/admin/test-cases/{case_id}")
def delete_test_case(case_id: int, _=Depends(verify_admin), db: DBSession = Depends(get_db)):
    t = db.query(TestCase).filter(TestCase.id == case_id).first()
    if not t:
        return err_resp("测试用例不存在")
    db.delete(t)
    db.commit()
    return resp()

