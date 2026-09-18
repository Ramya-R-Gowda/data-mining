import duckdb

con = duckdb.connect()

# Extensions required for federation
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")

con.execute("INSTALL postgres")
con.execute("LOAD postgres")

# MinIO connection
con.execute("""
CREATE OR REPLACE SECRET minio_secret (
    TYPE S3,
    KEY_ID 'minioadmin',
    SECRET 'minioadmin',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false
)
""")

# Connect DuckDB to PostgreSQL
con.execute("""
ATTACH 'postgresql://postgres:postgres@localhost:5432/annapurna'
AS pg (TYPE POSTGRES, READ_ONLY)
""")

# Query data directly from MinIO + PostgreSQL
query = """
SELECT
    'S01' AS store_id,
    s.store_name,
    COUNT(*) AS sales_lines,
    ROUND(SUM(qty * unit_price), 2) AS object_store_revenue
FROM read_csv_auto(
    's3://annapurna-sales/sales/S01/2024/10/*.csv'
) f
JOIN pg.public.stores s
    ON s.store_id = 'S01'
WHERE UPPER(line_type) IN ('SALE', 'RETURN', 'DISCOUNT', 'VOID')
GROUP BY s.store_name
"""

print("\n=== FEDERATED QUERY RESULT ===")
print(con.execute(query).fetchdf())

print("\n=== EXPLAIN PLAN ===")
print(con.execute("EXPLAIN " + query).fetchall()[0][1])

con.close()