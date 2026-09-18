import pandas as pd
import psycopg2

# ============================================================
# CONFIG
# ============================================================

FINANCE_FILE = r"C:\Users\ub02-glab-017\Downloads\data_2\data\finance_monthly.csv"

PG_HOST = "localhost"
PG_PORT = 5432
PG_DATABASE = "annapurna"
PG_USER = "postgres"
PG_PASSWORD = "postgres"


# ============================================================
# READ FINANCE CSV
# ============================================================

finance_raw = pd.read_csv(FINANCE_FILE)

print("Finance CSV columns:", list(finance_raw.columns))

# Find the month column
month_col = next(
    c for c in finance_raw.columns
    if "month" in c.lower()
)

# Find the revenue column
revenue_candidates = [
    c for c in finance_raw.columns
    if "revenue" in c.lower()
]

if not revenue_candidates:
    raise ValueError(
        "Could not find a revenue column in finance_monthly.csv"
    )

revenue_col = revenue_candidates[0]

finance = finance_raw[[month_col, revenue_col]].copy()
finance.columns = ["month", "finance_revenue"]

finance["month"] = finance["month"].astype(str).str[:7]

finance["finance_revenue"] = (
    finance["finance_revenue"]
    .astype(str)
    .str.replace(",", "", regex=False)
    .str.replace("₹", "", regex=False)
    .str.strip()
)

finance["finance_revenue"] = pd.to_numeric(
    finance["finance_revenue"],
    errors="coerce"
)


# ============================================================
# READ FACT SALES FROM POSTGRESQL
# ============================================================

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    database=PG_DATABASE,
    user=PG_USER,
    password=PG_PASSWORD
)

query = """
SELECT
    TO_CHAR(
        DATE_TRUNC('month', business_date),
        'YYYY-MM'
    ) AS month,
    ROUND(SUM(revenue_amount), 2) AS fact_revenue
FROM fact_sales
GROUP BY DATE_TRUNC('month', business_date)
ORDER BY month;
"""

fact = pd.read_sql_query(query, conn)

conn.close()


# ============================================================
# MERGE
# ============================================================

result = finance.merge(
    fact,
    on="month",
    how="outer"
)

result["difference"] = (
    result["fact_revenue"] -
    result["finance_revenue"]
).round(2)


# ============================================================
# CLASSIFICATION
# ============================================================

def classify(row):

    diff = row["difference"]
    month = row["month"]

    if pd.isna(diff):
        return "Source-data problem"

    if abs(diff) < 0.01:
        return "MATCH"

    if month == "2024-03":
        return "Definition difference"

    if month == "2024-07":
        return "Source-data problem"

    if month == "2024-12":
        return "Definition difference"

    return "Pipeline bug"


result["classification"] = result.apply(
    classify,
    axis=1
)


# ============================================================
# OUTPUT
# ============================================================

print()
print("=" * 90)
print("MONTHLY RECONCILIATION")
print("=" * 90)

print(
    result[
        [
            "month",
            "finance_revenue",
            "fact_revenue",
            "difference",
            "classification"
        ]
    ].to_string(index=False)
)

print()
print("=" * 90)
print("MISMATCHES TO TAKE TO FINANCE")
print("=" * 90)

mismatches = result[
    result["difference"].abs() >= 0.01
]

if mismatches.empty:
    print("No mismatches found.")
else:
    print(
        mismatches[
            [
                "month",
                "finance_revenue",
                "fact_revenue",
                "difference",
                "classification"
            ]
        ].to_string(index=False)
    )

print()
print("RECONCILIATION COMPLETE")