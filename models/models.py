from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base
from models.datetime_types import LocalizedDateTime


class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    ic_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    employee_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    site_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    site: Mapped[Optional["Site"]] = relationship(back_populates="workers")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="worker",
        cascade="all, delete-orphan",
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="worker",
        cascade="all, delete-orphan",
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("worker_id", "attendance_date", name="uq_attendance_worker_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_at: Mapped[Optional[datetime]] = mapped_column(LocalizedDateTime(), nullable=True)
    check_out_at: Mapped[Optional[datetime]] = mapped_column(LocalizedDateTime(), nullable=True)
    source_chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    worker: Mapped[Worker] = relationship(back_populates="attendance_records")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, unique=True)
    telegram_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workers: Mapped[list[Worker]] = relationship(back_populates="site")
    public_holidays: Mapped[list["PublicHoliday"]] = relationship(back_populates="site")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id", ondelete="CASCADE"), index=True)
    leave_type: Mapped[str] = mapped_column(String(20), index=True)
    day_portion: Mapped[str] = mapped_column(String(10), default="full", server_default=text("'full'"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    telegram_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    worker: Mapped[Worker] = relationship(back_populates="leave_requests")


class BotFsmState(Base):
    __tablename__ = "bot_fsm_states"

    bot_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    state: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PublicHoliday(Base):
    __tablename__ = "public_holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    site_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    site: Mapped[Optional[Site]] = relationship(back_populates="public_holidays")
