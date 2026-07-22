"""Состояния пошаговых сценариев (FSM)."""
from aiogram.fsm.state import State, StatesGroup


class AddPayment(StatesGroup):
    """Пошаговое добавление обязательного платежа кнопками."""

    title = State()   # ждём название (текст)
    amount = State()  # ждём сумму (текст) или кнопку «без суммы»
    month = State()   # ждём месяц (для квартальных и годовых)
    day = State()     # ждём день (кнопки или текст, зависит от частоты)


class AddLimit(StatesGroup):
    """Установка лимита по категории."""

    amount = State()  # ждём сумму лимита (категория уже выбрана кнопкой)


class AddIncome(StatesGroup):
    """Пошаговое добавление дохода кнопками (сумма → категория → описание)."""

    amount = State()
    category = State()
    description = State()
