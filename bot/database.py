"""Слой доступа к БД: модели SQLAlchemy и вспомогательные функции."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram id
    full_name: Mapped[str] = mapped_column(String(255), default="")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    daily_report: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )

    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # 'income' | 'expense'
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    category: Mapped[str] = mapped_column(String(64), default="Прочее")
    description: Mapped[str] = mapped_column(String(255), default="")
    op_date: Mapped[dt.date] = mapped_column(Date, default=dt.date.today, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )
    raw_text: Mapped[str] = mapped_column(String(500), default="")

    user: Mapped["User"] = relationship(back_populates="transactions")


class Reminder(Base):
    """Обязательный / регулярный платёж.

    frequency: 'weekly' | 'monthly' | 'yearly'
      - weekly:  используется weekday (0=Пн .. 6=Вс)
      - monthly: используется day_of_month (1..28)
      - yearly:  используются month (1..12) и day_of_month (1..28)
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[str] = mapped_column(String(16), default="monthly")
    day_of_month: Mapped[int] = mapped_column(Integer, default=1)  # 1..28
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0..6
    month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1..12
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )


class Db:
    """Обёртка над движком и сессиями."""

    def __init__(self, database_path: str):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(
            f"sqlite+aiosqlite:///{database_path}", echo=False
        )
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    # ---- Пользователи ----
    async def get_or_create_user(
        self, telegram_id: int, full_name: str, currency: str, timezone: str
    ) -> User:
        async with self.session_factory() as session:
            user = await session.get(User, telegram_id)
            if user is None:
                user = User(
                    id=telegram_id,
                    full_name=full_name,
                    currency=currency,
                    timezone=timezone,
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user

    async def get_user(self, telegram_id: int) -> Optional[User]:
        async with self.session_factory() as session:
            return await session.get(User, telegram_id)

    async def update_user(self, telegram_id: int, **fields) -> None:
        async with self.session_factory() as session:
            user = await session.get(User, telegram_id)
            if user is None:
                return
            for key, value in fields.items():
                setattr(user, key, value)
            await session.commit()

    async def users_with_daily_report(self) -> list[User]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(User).where(User.daily_report.is_(True))
            )
            return list(result.scalars().all())

    # ---- Транзакции ----
    async def add_transaction(self, **fields) -> Transaction:
        async with self.session_factory() as session:
            tx = Transaction(**fields)
            session.add(tx)
            await session.commit()
            await session.refresh(tx)
            return tx

    async def delete_last_transaction(self, user_id: int) -> Optional[Transaction]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.id.desc())
                .limit(1)
            )
            tx = result.scalar_one_or_none()
            if tx is None:
                return None
            await session.delete(tx)
            await session.commit()
            return tx

    async def balance(self, user_id: int) -> float:
        async with self.session_factory() as session:
            income = await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                    Transaction.user_id == user_id, Transaction.kind == "income"
                )
            )
            expense = await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                    Transaction.user_id == user_id, Transaction.kind == "expense"
                )
            )
            return float(income or 0) - float(expense or 0)

    async def period_totals(
        self, user_id: int, start: dt.date, end: dt.date
    ) -> tuple[float, float]:
        """Возвращает (доходы, расходы) за период [start, end]."""
        async with self.session_factory() as session:
            income = await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                    Transaction.user_id == user_id,
                    Transaction.kind == "income",
                    Transaction.op_date >= start,
                    Transaction.op_date <= end,
                )
            )
            expense = await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                    Transaction.user_id == user_id,
                    Transaction.kind == "expense",
                    Transaction.op_date >= start,
                    Transaction.op_date <= end,
                )
            )
            return float(income or 0), float(expense or 0)

    async def category_breakdown(
        self, user_id: int, kind: str, start: dt.date, end: dt.date
    ) -> list[tuple[str, float]]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(
                    Transaction.category,
                    func.coalesce(func.sum(Transaction.amount), 0.0),
                )
                .where(
                    Transaction.user_id == user_id,
                    Transaction.kind == kind,
                    Transaction.op_date >= start,
                    Transaction.op_date <= end,
                )
                .group_by(Transaction.category)
                .order_by(func.sum(Transaction.amount).desc())
            )
            return [(row[0], float(row[1])) for row in result.all()]

    async def recent_transactions(
        self, user_id: int, limit: int = 10
    ) -> list[Transaction]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.id.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def all_transactions(self, user_id: int) -> list[Transaction]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.op_date.asc(), Transaction.id.asc())
            )
            return list(result.scalars().all())

    # ---- Обязательные платежи / напоминания ----
    async def add_reminder(
        self,
        user_id: int,
        title: str,
        amount: Optional[float],
        frequency: str = "monthly",
        day_of_month: int = 1,
        weekday: Optional[int] = None,
        month: Optional[int] = None,
    ) -> Reminder:
        async with self.session_factory() as session:
            rem = Reminder(
                user_id=user_id,
                title=title,
                amount=amount,
                frequency=frequency,
                day_of_month=max(1, min(28, day_of_month)),
                weekday=weekday,
                month=month,
            )
            session.add(rem)
            await session.commit()
            await session.refresh(rem)
            return rem

    async def list_reminders(self, user_id: int) -> list[Reminder]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(Reminder)
                .where(Reminder.user_id == user_id, Reminder.active.is_(True))
                .order_by(Reminder.day_of_month.asc())
            )
            return list(result.scalars().all())

    async def delete_reminder(self, user_id: int, reminder_id: int) -> bool:
        async with self.session_factory() as session:
            rem = await session.get(Reminder, reminder_id)
            if rem is None or rem.user_id != user_id:
                return False
            await session.delete(rem)
            await session.commit()
            return True

    async def reminders_due(self, today: dt.date) -> list[Reminder]:
        """Все активные платежи, которые должны сработать сегодня."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(Reminder).where(Reminder.active.is_(True))
            )
            due: list[Reminder] = []
            for rem in result.scalars().all():
                if rem.frequency == "weekly":
                    if rem.weekday == today.weekday():
                        due.append(rem)
                elif rem.frequency == "yearly":
                    if rem.month == today.month and rem.day_of_month == today.day:
                        due.append(rem)
                else:  # monthly
                    if rem.day_of_month == today.day:
                        due.append(rem)
            return due
