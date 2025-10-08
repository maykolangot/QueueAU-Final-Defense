# utils.py

import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta
from core.models import TransactionNF1

def get_date_range(time_filter):
    today = datetime.today().date()
    if time_filter == "last_7_days":
        return [today - timedelta(days=i) for i in reversed(range(7))]
    elif time_filter == "this_month":
        start = today.replace(day=1)
        return [start + timedelta(days=i) for i in range((today - start).days + 1)]
    elif time_filter == "today":
        return [today]
    else:
        raise ValueError("Invalid time filter")

def generate_statistics_chart(campus, department, course, time_filter):
    transactions = TransactionNF1.objects.filter(status=TransactionNF1.Status.COMPLETED)

    if campus:
        transactions = transactions.filter(campus__iexact=campus)
    if course:
        transactions = transactions.filter(course__id=course)
    if department:
        transactions = transactions.filter(course__department__id=department)

    date_range = get_date_range(time_filter)
    transactions = transactions.filter(created_at__date__in=date_range)

    # Group data
    data = {}
    for d in date_range:
        daily = transactions.filter(created_at__date=d)
        for campus_name in set(daily.values_list("campus", flat=True)):
            data.setdefault(d, {}).setdefault(campus_name, 0)
            data[d][campus_name] += daily.filter(campus=campus_name).count()

    campuses = sorted({c for v in data.values() for c in v})
    counts_by_campus = {c: [data.get(d, {}).get(c, 0) for d in date_range] for c in campuses}

    # Plotting
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

    # Render to base64 string
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    plt.close(fig)
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()

    base64_img = base64.b64encode(image_png).decode('utf-8')
    return f"data:image/png;base64,{base64_img}"
