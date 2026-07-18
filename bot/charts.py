"""Генерация графиков расходов картинкой (PNG) для отправки в Telegram."""
from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # без графического дисплея (сервер)
import matplotlib.pyplot as plt  # noqa: E402

# Приятная палитра для категорий
PALETTE = [
    "#4C9AFF", "#FF7452", "#57D9A3", "#FFC400", "#B39DFF",
    "#FF8FB1", "#00C7E6", "#8CC152", "#F6B26B", "#A0AEC0",
    "#E57373", "#64B5F6", "#81C784", "#FFD54F", "#BA68C8",
]


def expense_pie(breakdown: list[tuple[str, float]], currency: str, title: str) -> bytes | None:
    """Круговая диаграмма расходов по категориям. Возвращает PNG или None."""
    data = [(c, a) for c, a in breakdown if a > 0]
    if not data:
        return None

    # Крупные категории показываем отдельно, мелкие сводим в «Прочее»
    total = sum(a for _, a in data)
    big = [(c, a) for c, a in data if a / total >= 0.03]
    small_sum = sum(a for c, a in data if a / total < 0.03)
    if small_sum > 0:
        big.append(("Прочее (мелкие)", small_sum))

    labels = [c for c, _ in big]
    values = [a for _, a in big]

    fig, ax = plt.subplots(figsize=(7, 6), dpi=130)
    wedges, _texts, autotexts = ax.pie(
        values,
        colors=PALETTE[: len(values)],
        autopct=lambda p: f"{p:.0f}%" if p >= 4 else "",
        startangle=90,
        pctdistance=0.78,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2),
    )
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(10)
        t.set_fontweight("bold")

    ax.set_title(title, fontsize=14, fontweight="bold", pad=16)
    # Легенда с суммами
    legend_labels = [
        f"{c} — {v:,.0f} {currency}".replace(",", " ") for c, v in zip(labels, values)
    ]
    ax.legend(
        wedges, legend_labels, loc="center left", bbox_to_anchor=(1.0, 0.5),
        fontsize=10, frameon=False,
    )
    # Сумма в центре
    ax.text(
        0, 0, f"{total:,.0f}\n{currency}".replace(",", " "),
        ha="center", va="center", fontsize=13, fontweight="bold",
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def daily_line(
    days: list[int], values: list[float], currency: str, title: str,
    avg: float | None = None,
) -> bytes | None:
    """Линия трат по дням месяца (с накоплением по дню)."""
    if not days or not any(values):
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=130)
    ax.fill_between(days, values, color="#4C9AFF", alpha=0.20)
    ax.plot(days, values, color="#4C9AFF", linewidth=2.2, marker="o", markersize=4)
    if avg:
        ax.axhline(avg, color="#FF7452", linestyle="--", linewidth=1.5,
                   label=f"Среднее: {avg:,.0f} {currency}".replace(",", " "))
        ax.legend(frameon=False, fontsize=10)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("День месяца", fontsize=10)
    ax.set_ylabel(currency, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.15)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def month_compare_bar(
    labels: list[str], prev_values: list[float], cur_values: list[float],
    currency: str, title: str,
) -> bytes | None:
    """Столбчатая диаграмма: прошлый месяц vs текущий по топ-категориям."""
    if not labels:
        return None
    import numpy as np

    x = np.arange(len(labels))
    width = 0.38
    fig, ax = plt.subplots(figsize=(8, 5), dpi=130)
    ax.bar(x - width / 2, prev_values, width, label="Прошлый месяц", color="#A0AEC0")
    ax.bar(x + width / 2, cur_values, width, label="Текущий месяц", color="#4C9AFF")
    ax.set_title(title, fontsize=14, fontweight="bold", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.legend(frameon=False, fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylabel(currency, fontsize=10)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
