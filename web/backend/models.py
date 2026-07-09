from sqlalchemy import Column, BigInteger, String, Text, SmallInteger, DateTime, Index, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "session"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    session_id = Column("id", String(32), primary_key=True)
    status = Column(SmallInteger, nullable=False, default=0, index=True)
    end_reason = Column(String(200))
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    ended_at = Column(DateTime)


class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("idx_session_sender", "session_id", "sender"),
        {"mysql_charset": "utf8mb4"},
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False, index=True)
    sender_type = Column("sender", SmallInteger, nullable=False, comment="1用户 2系统")
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)


class MoveCarApply(Base):
    __tablename__ = "move_car_apply"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False, index=True)
    plate_number = Column("plate_no", String(20), nullable=False, index=True)
    plate_color = Column(SmallInteger, nullable=False)
    address = Column(String(200), nullable=False)
    reason = Column(String(500))
    accept_status = Column("status", SmallInteger, nullable=False, default=0, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)


class TestCase(Base):
    __tablename__ = "test_case"
    __table_args__ = {"mysql_charset": "utf8mb4"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    case_name = Column("name", String(100), nullable=False, index=True)
    input_content = Column(Text, nullable=False)
    expect_reply = Column("expected_reply", Text)
    expect_status = Column("expected_status", SmallInteger)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
