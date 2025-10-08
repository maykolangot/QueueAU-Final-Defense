
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
from core.models import TransactionNF1, Course, Department
from django.db.models import Q
import uuid

def get_date_range(time_filter):
    today = datetime.today().date()
    if time_filter == "last_7_days":
        start = today - timedelta(days=6)
        return [start + timedelta(days=i) for i in range(7)]
    elif time_filter == "this_month":
        start = today.replace(day=1)
        delta = (today - start).days + 1
        return [start + timedelta(days=i) for i in range(delta)]
    elif time_filter == "today":
        return [today]
    else:
        raise ValueError("Invalid time filter")

def generate_statistics_chart(campus, department, course, time_filter):
    # Filter ORM
    transactions = TransactionNF1.objects.filter(status=TransactionNF1.Status.COMPLETED)

    if campus:
        transactions = transactions.filter(campus__iexact=campus)
    if course:
        transactions = transactions.filter(course__id=course)
    if department:
        transactions = transactions.filter(course__department__id=department)

    date_range = get_date_range(time_filter)
    transactions = transactions.filter(created_at__date__in=date_range)

    # Count by date and campus
    data = {}
    for d in date_range:
        daily = transactions.filter(created_at__date=d)
        for campus_name in set(daily.values_list("campus", flat=True)):
            data.setdefault(d, {}).setdefault(campus_name, 0)
            data[d][campus_name] += daily.filter(campus=campus_name).count()

    # Convert to matplotlib
    campuses = sorted({c for v in data.values() for c in v})
    counts_by_campus = {c: [data.get(d, {}).get(c, 0) for d in date_range] for c in campuses}

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = [0] * len(date_range)

    for campus_name in campuses:
        values = counts_by_campus[campus_name]
        ax.bar(date_range, values, label=campus_name, bottom=bottom)
        bottom = [sum(x) for x in zip(bottom, values)]

    ax.set_title(f"Completed Transactions - {time_filter.replace('_', ' ').title()}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Transactions")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save to static file
    filename = f"{uuid.uuid4().hex}.png"
    path = os.path.join("static", "charts", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path)
    plt.close()

    return f"/static/charts/{filename}"
