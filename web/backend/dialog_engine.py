import os
import random
import re

from rule_engine import (
    validate_plate, check_accident, get_plate_city,
    check_address, need_human
)

INIT = "INIT"
WAIT_PLATE = "WAIT_PLATE"
CONFIRM_PLATE = "CONFIRM_PLATE"
WAIT_COLOR = "WAIT_COLOR"
WAIT_ADDRESS = "WAIT_ADDRESS"
WAIT_REASON = "WAIT_REASON"
VERIFYING = "VERIFYING"
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
TRANSFER_HUMAN = "TRANSFER_HUMAN"

# ---------- 固定回复（终态用） ----------

REPLY_INIT = "您好，这里是智能移车助手请用普通话清晰的报出您要移的车牌。"
REPLY_ACCIDENT = "抱歉，您的情况不在114移车服务范围，请直接拨打122进行处理。"
REPLY_TRANSFER = "已为您转接人工客服，请稍候。"
REPLY_NON_ZHE = "抱歉，目前仅支持浙江省内正式民用车牌的移车服务。"
REPLY_ACCEPTED = "好的，您反馈的在{地址}且车牌号为{车牌}的{颜色}车，因{原因}申请移车，我们马上为您联系车主，稍后通知您移车结果，请保持手机畅通，再见。"

# ---------- 预写自然回复（毫秒级，不走 LLM） ----------

_NATURAL = {
    CONFIRM_PLATE: [
        "好的，我记录到车牌是{plate}，是{region}牌照，请确认一下对吗？",
        "我看到您提供的车牌是{plate}（{region}），请问准确吗？",
    ],
    WAIT_COLOR: {
        "ask": [
            "好的，请问这辆车是蓝牌还是绿牌呢？",
            "收到啦，这辆车是蓝色车牌还是绿色车牌呢？",
        ],
        "retry": [
            "我没太明白，您直接告诉我车牌颜色是蓝牌还是绿牌就行。",
            "请说一下车牌是蓝色的还是绿色的呢？",
        ],
    },
    WAIT_ADDRESS: {
        "ask": [
            "好的，请问具体在什么位置？哪个区哪条路呢？",
            "麻烦告诉我具体的地址，比如杭州市西湖区这样的。",
        ],
        "invalid": [
            "这个地址好像不太对，请说一下具体在哪个区哪条路上。",
        ],
    },
    WAIT_REASON: {
        "ask": [
            "好的，最后一个问题，请问具体是什么情况需要移车呢？",
            "了解了，麻烦说一下移车的原因，我好帮您提交工单。",
        ],
    },
    # 用户确认后转向下一环节的过渡语
    "TRANSITION": {
        WAIT_COLOR: [
            "好的，那这辆车是蓝牌还是绿牌呢？",
            "收到，请问车牌是蓝色还是绿色的？",
        ],
        WAIT_ADDRESS: [
            "好的，请问具体在什么位置？哪个区哪条路呢？",
            "麻烦告诉我具体的地址。",
        ],
        WAIT_REASON: [
            "好的，最后一个问题，请问具体是什么情况需要移车？",
            "了解了，麻烦说一下移车的原因。",
        ],
    },
}

# ---------- 工具函数 ----------

_AFFIRMATIVE = re.compile(r"^(是|对|好|嗯|对的|是的|没错|确认|可以|行|确定|正确|1|y|yes)", re.IGNORECASE)
_NEGATIVE = re.compile(r"^(不|不是|不对|没有|错了|否|错误|不对的|不正确)", re.IGNORECASE)
_PLATE_PATTERN = re.compile(r'[浙][A-Za-z0-9][A-Za-z0-9]{4,5}')
_COLOR_PATTERNS = [
    (re.compile(r'蓝牌|蓝色|蓝的'), "蓝牌"),
    (re.compile(r'绿牌|绿色|绿的'), "绿牌"),
    (re.compile(r'黄牌|黄色|黄的'), "黄牌"),
    (re.compile(r'白牌|白色|白的'), "白牌"),
    (re.compile(r'黑牌|黑色|黑的'), "黑牌"),
]


def _pick(replies):
    """从列表中随机选一条回复。"""
    return random.choice(replies)


def _fast_extract(text):
    """纯规则提取字段（无 LLM 调用）。"""
    result = {"plate_number": None, "plate_color": None}
    m = _PLATE_PATTERN.search(text)
    if m:
        result["plate_number"] = m.group().upper()
    for pattern, color in _COLOR_PATTERNS:
        if pattern.search(text):
            result["plate_color"] = color
            break
    return result


# ===================================================================


class DialogEngine:
    def __init__(self):
        self._sessions = {}

    def _new_session(self):
        return {
            "info": {"plate_number": None, "plate_color": None, "address": None, "reason": None},
            "state": INIT,
            "failures": 0,
            "is_finished": False,
            "_multi": None,  # 剩余原文，用于一句话多信息跳过
        }

    def _merge(self, info, extracted):
        for key in ("plate_number", "plate_color", "address", "reason"):
            if extracted.get(key) is not None:
                info[key] = extracted[key]

    def _is_affirmative(self, text):
        return bool(_AFFIRMATIVE.match(text.strip()))

    def _is_negative(self, text):
        return bool(_NEGATIVE.match(text.strip()))

    def _terminate(self, session, state, reply):
        session["state"] = state
        session["is_finished"] = True
        return (reply, state, True)

    def _natural(self, category, subkey=None, **kwargs):
        """取预写自然回复，支持模板变量。"""
        replies = _NATURAL
        if subkey:
            replies = replies.get(category, {}).get(subkey, [])
        else:
            replies = replies.get(category, [])
        if not replies:
            return ""
        text = _pick(replies)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError:
                pass
        return text

    # ---------- 多信息跳过 ----------

    @staticmethod
    def _strip_known(text, info):
        """去掉文本中已知的车牌和颜色字段。"""
        remaining = text
        for key in ("plate_number", "plate_color"):
            val = info.get(key)
            if val and val in remaining:
                remaining = remaining.replace(val, "", 1)
        return remaining.strip().strip("，,。. ")

    @staticmethod
    def _extract_color(text):
        """从文本中提取颜色，返回颜色名称或 None。"""
        for pattern, color in _COLOR_PATTERNS:
            if pattern.search(text):
                return color
        return None

    def _advance(self, session, text, extracted):
        """
        快速跳过已经提供信息的环节。
        在成功获取一个必填字段后调用，尝试一并提取其余字段。
        返回 (reply, state, finished) 或 None（无法前进）。
        """
        info = session["info"]
        self._merge(info, extracted)

        remaining = self._strip_known(text, info)

        # ---- 检查颜色 ----
        if not info.get("plate_color"):
            color = self._extract_color(remaining)
            if color:
                info["plate_color"] = color
                # 从剩余文本中去掉颜色关键词
                for pattern, _ in _COLOR_PATTERNS:
                    remaining = pattern.sub("", remaining).strip().strip("，,。. ")
            else:
                return None  # 让调用方进入 WAIT_COLOR

        # ---- 检查地址 & 原因 ----
        if not info.get("address") or not info.get("reason"):
            if not remaining:
                return None  # 没有更多文本可提取

            plate = info.get("plate_number") or ""
            plate_city = get_plate_city(plate) or ""

            # 尝试把剩余文本拆成 地址 + 原因（按"了"拆分）
            addr_text, reason_text = remaining, ""
            for sep in ("了", "，", ", "):
                if sep in remaining:
                    parts = remaining.split(sep, 1)
                    candidate = parts[0].strip()
                    # 检查前半段是否像地址
                    is_valid, _, _ = check_address(candidate, plate_city)
                    if is_valid:
                        addr_text = candidate
                        reason_text = parts[1].strip() if len(parts) > 1 else ""
                        break

            if not info.get("address"):
                is_valid, std_addr, _ = check_address(addr_text, plate_city)
                if is_valid:
                    info["address"] = std_addr
                    # 已找到地址，剩余文本作为原因
                    if reason_text:
                        pass  # 下面处理原因
                    elif addr_text != remaining:
                        reason_text = remaining.replace(addr_text, "", 1).strip().strip("，,。. ")
                else:
                    # 地址无效，尝试整段
                    is_valid, std_addr, _ = check_address(remaining, plate_city)
                    if is_valid:
                        info["address"] = std_addr
                        reason_text = ""
                    else:
                        return None  # 让调用方进入 WAIT_ADDRESS

            # 处理原因
            if not info.get("reason") and reason_text:
                is_acc, _ = check_accident(reason_text)
                if is_acc:
                    return self._terminate(session, REJECTED, REPLY_ACCIDENT)
                info["reason"] = reason_text

        # ---- 全部就绪？ ----
        if info.get("plate_color") and info.get("address") and info.get("reason"):
            return self._verifying(session)

        return None

    # ---------- 各状态处理器 ----------

    def _wait_plate(self, session, user_input, extracted):
        info = session["info"]
        plate = info["plate_number"] or extracted.get("plate_number")
        if not plate:
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            return (REPLY_INIT, WAIT_PLATE, False)

        is_valid, msg = validate_plate(plate)
        if not is_valid:
            if "仅支持浙江省" in msg:
                return self._terminate(session, REJECTED, REPLY_NON_ZHE)
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            return (msg, WAIT_PLATE, False)

        # 有效车牌 → 更新信息 + 保存剩余文本（后续多信息跳过用）
        info["plate_number"] = plate
        session["failures"] = 0
        session["_multi"] = user_input  # 保存完整的原始输入
        session["state"] = CONFIRM_PLATE
        city = get_plate_city(plate) or ""
        reply = self._natural(CONFIRM_PLATE, plate=plate, region=city)
        return (reply, CONFIRM_PLATE, False)

    def _confirm_plate(self, session, user_input, extracted):
        info = session["info"]
        old_plate = info.get("plate_number")
        new_plate = extracted.get("plate_number")

        if self._is_affirmative(user_input):
            session["failures"] = 0
            # 用之前保存的原文推进到下一个缺失信息环节
            multi_text = session.pop("_multi", None) or user_input
            result = self._advance(session, multi_text, extracted)
            if result is not None:
                return result
            # fallback: 问颜色
            session["state"] = WAIT_COLOR
            reply = self._natural("TRANSITION", WAIT_COLOR)
            return (reply, WAIT_COLOR, False)

        if self._is_negative(user_input):
            # 用户否认，检查是否给了新车牌
            if new_plate and (not old_plate or new_plate != old_plate):
                is_valid, msg = validate_plate(new_plate)
                if not is_valid:
                    if "仅支持浙江省" in msg:
                        return self._terminate(session, REJECTED, REPLY_NON_ZHE)
                    session["failures"] += 1
                    if session["failures"] >= 3:
                        return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
                    return (msg, CONFIRM_PLATE, False)
                info["plate_number"] = new_plate
                session["failures"] = 0
                city = get_plate_city(new_plate) or ""
                reply = self._natural(CONFIRM_PLATE, plate=new_plate, region=city)
                return (reply, CONFIRM_PLATE, False)
            # 没给新车牌 → 回到待车牌
            session["state"] = WAIT_PLATE
            info["plate_number"] = None
            session["failures"] = 0
            return (REPLY_INIT, WAIT_PLATE, False)

        session["failures"] += 1
        if session["failures"] >= 3:
            return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
        plate = info["plate_number"] or ""
        city = get_plate_city(plate) or ""
        reply = self._natural(CONFIRM_PLATE, plate=plate, region=city)
        return (reply, CONFIRM_PLATE, False)

    def _wait_color(self, session, user_input, extracted):
        info = session["info"]
        color = extracted.get("plate_color")

        if color:
            info["plate_color"] = color
            session["failures"] = 0
            # 看用户是否同时提供了地址/原因
            result = self._advance(session, user_input, extracted)
            if result is not None:
                return result
            session["state"] = WAIT_ADDRESS
            reply = self._natural("WAIT_ADDRESS", "ask")
            return (reply, WAIT_ADDRESS, False)

        if self._is_affirmative(user_input):
            info["plate_color"] = "蓝牌"
            session["failures"] = 0
            result = self._advance(session, user_input, extracted)
            if result is not None:
                return result
            session["state"] = WAIT_ADDRESS
            reply = self._natural("WAIT_ADDRESS", "ask")
            return (reply, WAIT_ADDRESS, False)

        if self._is_negative(user_input):
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            reply = self._natural("WAIT_COLOR", "retry")
            return (reply, WAIT_COLOR, False)

        session["failures"] += 1
        if session["failures"] >= 3:
            return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
        reply = self._natural("WAIT_COLOR", "ask")
        return (reply, WAIT_COLOR, False)

    def _wait_address(self, session, user_input):
        info = session["info"]
        # 用户当前输入就是地址
        addr = user_input.strip()
        if not addr:
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            reply = self._natural("WAIT_ADDRESS", "ask")
            return (reply, WAIT_ADDRESS, False)

        plate = info.get("plate_number") or ""
        plate_city = get_plate_city(plate)
        is_valid, standard_addr, msg = check_address(addr, plate_city)

        if not is_valid:
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            return (msg, WAIT_ADDRESS, False)

        info["address"] = standard_addr
        session["failures"] = 0
        # 看用户是否同时提供了原因
        result = self._advance(session, user_input, {})
        if result is not None:
            return result
        session["state"] = WAIT_REASON
        reply = self._natural("WAIT_REASON", "ask")
        return (reply, WAIT_REASON, False)

    def _wait_reason(self, session, user_input):
        info = session["info"]
        reason = user_input.strip()
        if not reason:
            session["failures"] += 1
            if session["failures"] >= 3:
                return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
            reply = self._natural("WAIT_REASON", "ask")
            return (reply, WAIT_REASON, False)

        is_acc, _ = check_accident(reason)
        if is_acc:
            return self._terminate(session, REJECTED, REPLY_ACCIDENT)

        info["reason"] = reason
        session["failures"] = 0
        session["state"] = VERIFYING
        return self._verifying(session)

    def _verifying(self, session):
        info = session["info"]
        plate = info.get("plate_number") or ""
        is_valid, msg = validate_plate(plate)
        if not is_valid:
            return self._terminate(session, REJECTED, msg)

        addr = info.get("address") or ""
        plate_city = get_plate_city(plate)
        is_valid, standard_addr, msg = check_address(addr, plate_city)
        if not is_valid:
            return self._terminate(session, REJECTED, msg)
        info["address"] = standard_addr

        reply = REPLY_ACCEPTED.format(
            地址=info["address"] or "",
            车牌=plate,
            颜色=info.get("plate_color") or "",
            原因=info.get("reason") or "",
        )
        return self._terminate(session, ACCEPTED, reply)

    # ---------- 对外入口 ----------

    def handle_message(self, session_id, user_input):
        session = self._sessions.setdefault(session_id, self._new_session())
        if session["is_finished"]:
            return ("", session["state"], True)

        # 转人工 / 事故检测（基于原始文本，无 LLM）
        if need_human(user_input, 0):
            return self._terminate(session, TRANSFER_HUMAN, REPLY_TRANSFER)
        if check_accident(user_input)[0]:
            return self._terminate(session, REJECTED, REPLY_ACCIDENT)

        # 开场
        if session["state"] == INIT:
            session["state"] = WAIT_PLATE
            return (REPLY_INIT, WAIT_PLATE, False)

        # 规则提取字段（无 LLM）
        extracted = _fast_extract(user_input)

        # 分派到各状态处理器
        state = session["state"]
        if state == WAIT_PLATE:
            return self._wait_plate(session, user_input, extracted)
        if state == CONFIRM_PLATE:
            return self._confirm_plate(session, user_input, extracted)
        if state == WAIT_COLOR:
            return self._wait_color(session, user_input, extracted)
        if state == WAIT_ADDRESS:
            return self._wait_address(session, user_input)
        if state == WAIT_REASON:
            return self._wait_reason(session, user_input)
        if state == VERIFYING:
            return self._verifying(session)

        return ("", state, True)

    def get_session_info(self, session_id):
        return self._sessions.get(session_id)
