import seaborn as sns
import sqlite3
import pandas as pd

import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Create a connection object
conn = sqlite3.connect('db.sqlite3')


# Query SQLite's metadata to list tables
df = pd.read_sql_query(
    "SELECT * from core_transactionnf1;", 
    conn
)
print(df)

# Normalize campus and created_at
df["campus"] = df["campus"].astype(str).str.strip().str.lower()
df["created_at"] = pd.to_datetime(df["created_at"].astype(str).str.strip(), format="mixed", errors="coerce")
df["date"] = df["created_at"].dt.date




# === Define Global Time Filter ===
def set_time_filter(filter_name='last_7_days'):
    global time_filter, start_date, date_range
    time_filter = filter_name
    today = datetime.today().date()

    if time_filter == "last_7_days":
        start_date = today - timedelta(days=6)
        date_range = pd.date_range(start=start_date, end=today).date
    elif time_filter == "this_month":
        start_date = today.replace(day=1)
        date_range = pd.date_range(start=start_date, end=today).date
    elif time_filter == "today":
        start_date = today
        date_range = [today]
    else:
        raise ValueError("Invalid time_filter. Use 'last_7_days', 'this_month', or 'today'.")


# === Centralized Filter Function ===
def get_filtered_transactions(department_name=None, course_name=None, campus_name=None):
    # Merge df with course and department info
    merged = df.merge(
        core_course.rename(columns={"id": "course_id", "name": "course_name"}),
        on="course_id", how="left"
    ).merge(
        core_department.rename(columns={"id": "department_id", "name": "department_name"}),
        on="department_id", how="left"
    )

    # Normalize
    merged["campus"] = merged["campus"].astype(str).str.strip().str.title()
    merged["department_name"] = merged["department_name"].astype(str).str.strip()
    merged["course_name"] = merged["course_name"].astype(str).str.strip()

    # Apply time filter
    filtered = merged[merged["date"] >= start_date]

    # Optional filters
    if department_name:
        filtered = filtered[filtered["department_name"].str.lower() == department_name.lower()]
    if course_name:
        filtered = filtered[filtered["course_name"].str.lower() == course_name.lower()]
    if campus_name:
        filtered = filtered[filtered["campus"].str.lower() == campus_name.lower()]

    return filtered


def plot_completed_transactions(department_name=None, course_name=None, campus_name=None):

        # Load course and department data
    core_course = pd.read_sql_query("SELECT id, name, department_id FROM core_course;", conn)
    core_department = pd.read_sql_query("SELECT id, name FROM core_department;", conn)


    # Use centralized filter function
    filtered_df = get_filtered_transactions(department_name, course_name, campus_name)

    # Filter further for completed only
    filtered_df = filtered_df[filtered_df["status"].str.lower() == "completed"]

    if filtered_df.empty:
        print(f"⚠️ No completed transactions found for {time_filter.replace('_', ' ')}.")
        return

    # Normalize campus values
    filtered_df["campus"] = filtered_df["campus"].astype(str).str.strip().str.lower()

    # Dynamically get all campuses that appear in the data
    campuses = sorted(filtered_df["campus"].dropna().unique())

    # Group by date and campus
    grouped = filtered_df.groupby(["date", "campus"]).size().unstack(fill_value=0)

    # Reindex to ensure all dates and campuses are represented
    grouped = grouped.reindex(index=date_range, columns=campuses, fill_value=0)

    # Plot
    ax = grouped.plot(kind="bar", stacked=True, figsize=(12, 6))
    plt.title(f"Completed Transactions ({time_filter.replace('_', ' ').title()})")
    plt.xlabel("Date")
    plt.ylabel("Number of Transactions")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.legend(title="Campus")
    plt.grid(True)
    plt.show()

set_time_filter("this_month")
plot_completed_transactions()

# === Usage Example ===
#set_time_filter("this_month")
#plot_completed_transactions()

#set_time_filter("last_7_days")
#plot_completed_transactions()

#set_time_filter("today")
#plot_completed_transactions()







# === Count + Plot with Zero Handling ===
def count_completed_by_transaction_type(show_plot=True, department_name=None, course_name=None, campus_name=None):
    # Use the central filter function
    filtered_df = get_filtered_transactions(department_name, course_name, campus_name)

    # Keep only completed
    filtered_df = filtered_df[filtered_df["status"].str.lower() == "completed"]

    counts = filtered_df.groupby("transactionType").size().sort_values(ascending=False)

    if counts.empty:
        print(f"⚠️ No completed transactions found for {time_filter.replace('_', ' ')}.")
        return pd.Series(dtype=int)

    if show_plot:
        color_palette = sns.color_palette("husl", len(counts))

        ax = counts.plot(
            kind='bar',
            figsize=(10, 6),
            color=color_palette
        )
        title_context = department_name or course_name or campus_name or "All"
        plt.title(f"Completed Transactions by Type ({title_context} — {time_filter.replace('_', ' ').title()})")
        plt.xlabel("Transaction Type")
        plt.ylabel("Number of Transactions")
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.grid(True)
        plt.show()

# === Example Usage ===
set_time_filter("today")
print("Today:")
print(count_completed_by_transaction_type())

set_time_filter("last_7_days")
print("\nLast 7 Days:")
print(count_completed_by_transaction_type(department_name="Engineering"))

set_time_filter("this_month")
print("\nThis Month:")
print(count_completed_by_transaction_type(course_name="BS Information Technology", campus_name="Main"))