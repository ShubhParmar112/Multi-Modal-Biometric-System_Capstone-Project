"""
Visualization charts for personal finance analytics. Returns plain
matplotlib Figure objects (not pyplot) so callers can either embed them in
the Tkinter GUI via FigureCanvasTkAgg or save them to disk from the CLI.
"""

import os
from typing import Dict, List

from matplotlib.figure import Figure

from analytics.reports import FinanceAnalytics


def category_pie_chart(breakdown: Dict[str, float]) -> Figure:
    fig = Figure(figsize=(4.2, 4.2), dpi=100)
    ax = fig.add_subplot(111)
    if breakdown:
        ax.pie(list(breakdown.values()), labels=list(breakdown.keys()),
               autopct="%1.1f%%", startangle=90)
    else:
        ax.text(0.5, 0.5, "No expenses this month", ha="center", va="center")
        ax.axis("off")
    ax.set_title("Category Breakdown")
    fig.tight_layout()
    return fig


def trend_line_chart(spending_trend: List[dict], savings_trend: List[dict]) -> Figure:
    fig = Figure(figsize=(6, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    months = [row["month"] for row in spending_trend]
    spend = [row["total_spend"] for row in spending_trend]
    net = [row["net_savings"] for row in savings_trend]

    ax.plot(months, spend, marker="o", label="Spending")
    ax.plot(months, net, marker="o", label="Net Savings")
    ax.set_title("Spending & Savings Trend")
    ax.legend()
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return fig


def cash_flow_bar_chart(cash_flow: List[dict]) -> Figure:
    fig = Figure(figsize=(6, 4.2), dpi=100)
    ax = fig.add_subplot(111)

    months = [row["month"] for row in cash_flow]
    inflow = [row["inflow"] for row in cash_flow]
    outflow = [row["outflow"] for row in cash_flow]
    positions = range(len(months))
    width = 0.35

    ax.bar([p - width / 2 for p in positions], inflow, width, label="Inflow")
    ax.bar([p + width / 2 for p in positions], outflow, width, label="Outflow")
    ax.set_xticks(list(positions))
    ax.set_xticklabels(months, rotation=45)
    ax.set_title("Cash Flow")
    ax.legend()
    fig.tight_layout()
    return fig


def save_all_charts(user_id: str, analytics: FinanceAnalytics,
                    output_dir: str) -> List[str]:
    """Generate and save all 3 charts for a user; returns the saved file paths."""
    os.makedirs(output_dir, exist_ok=True)

    report = analytics.monthly_report(user_id)
    charts = [
        (category_pie_chart(report["category_breakdown"]), "category_breakdown.png"),
        (trend_line_chart(analytics.spending_trend(user_id),
                          analytics.savings_trend(user_id)),
         "spending_savings_trend.png"),
        (cash_flow_bar_chart(analytics.cash_flow(user_id)), "cash_flow.png"),
    ]

    paths = []
    for fig, filename in charts:
        path = os.path.join(output_dir, filename)
        fig.savefig(path, bbox_inches="tight")
        paths.append(path)

    return paths
