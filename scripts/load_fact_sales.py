"""
Annapurna Stores - Sales ETL

Purpose:
    Read normalized sales files from MinIO and load fact_sales in PostgreSQL.

Important business rules from billing_notes.md:
    - Business date comes from the filename.
    - Re-sends are NOT selected by newest-file logic.
    - Safe deduplication key is (store, business_date, bill_no, line_no).
    - SALE, RETURN, DISCOUNT and VOID contribute to revenue.
    - TAX and TENDER do NOT contribute to revenue.
    - Product code must be resolved using product_code + business_date.
    - Original files remain in MinIO.
"""

import io
import os
import re
import hashlib
from datetime import datetime

import boto3
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


# ============================================================
# CONFIGURATION
# ============================================================

MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

BUCKET = "annapurna-sales"

PG_HOST = "localhost"
PG_PORT = 5432
PG_DATABASE = "annapurna"
PG_USER = "postgres"
PG_PASSWORD = "postgres"

BATCH_SIZE = 5000


# ============================================================
# MINIO CLIENT
# ============================================================

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
)


# ============================================================
# POSTGRES CONNECTION
# ============================================================

conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    database=PG_DATABASE,
    user=PG_USER,
    password=PG_PASSWORD,
)

conn.autocommit = False


# ============================================================
# HELPERS
# ============================================================

def normalize_column_name(name):
    """
    Normalize column names so BOMs, spaces and case differences
    do not break the ETL.
    """
    return (
        str(name)
        .replace("\ufeff", "")
        .strip()
        .lower()
    )


def normalize_columns(df):
    """
    Convert different till-generation column names into
    the canonical names used by the warehouse.
    """

    aliases = {
        "bill_no": "bill_no",
        "bill": "bill_no",

        "line_no": "line_no",
        "line": "line_no",

        "product_code": "product_code",
        "item_code": "product_code",
        "product": "product_code",

        "qty": "qty",
        "quantity": "qty",

        "unit_price": "unit_price",
        "rate": "unit_price",
        "price": "unit_price",

        "line_type": "line_type",
        "type": "line_type",

        "ts": "ts",
        "txn_time": "ts",
        "transaction_time": "ts",
    }

    renamed = {}

    for column in df.columns:
        normalized = normalize_column_name(column)

        if normalized in aliases:
            renamed[column] = aliases[normalized]
        else:
            renamed[column] = normalized

    df = df.rename(columns=renamed)

    required = [
        "bill_no",
        "line_no",
        "product_code",
        "qty",
        "unit_price",
        "line_type",
        "ts",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    return df[required].copy()


def parse_object_name(object_key):
    """
    Extract store and BUSINESS DATE from the object filename.

    Example:
        sales/S01/2024/10/SALES_S01_20241001.csv

    Returns:
        store_id = S01
        business_date = 2024-10-01
    """

    filename = os.path.basename(object_key)

    pattern = r"^SALES_(S\d{2})_(\d{8})(?:__R\d+)?\.(csv|parquet)$"

    match = re.match(pattern, filename, re.IGNORECASE)

    if not match:
        raise ValueError(
            f"Invalid sales filename: {filename}"
        )

    store_id = match.group(1).upper()
    date_text = match.group(2)

    business_date = datetime.strptime(
        date_text,
        "%Y%m%d"
    ).date()

    return store_id, business_date


def read_csv_object(raw_bytes, store_id):
    """
    Read one CSV object according to the till generation.

    S01-S05:
        comma + ISO timestamp

    S06-S09:
        semicolon + dd-mm-yyyy timestamp

    S10-S12:
        comma + UTF-8 BOM + epoch timestamp
    """

    if store_id in {"S06", "S07", "S08", "S09"}:
        separator = ";"
    else:
        separator = ","

    df = pd.read_csv(
        io.BytesIO(raw_bytes),
        sep=separator,
        encoding="utf-8-sig",
        dtype=str,
    )

    return normalize_columns(df)


def read_parquet_object(raw_bytes):
    """
    Read a Parquet object and normalize its columns.
    """

    df = pd.read_parquet(
        io.BytesIO(raw_bytes)
    )

    return normalize_columns(df)


def parse_transaction_timestamp(series, store_id):
    """
    Parse timestamps according to till generation.

    S10-S12 use epoch seconds.
    S06-S09 use dd-mm-yyyy HH:MM:SS.
    S01-S05 use ISO timestamps.
    """

    values = series.astype(str).str.strip()

    if store_id in {"S10", "S11", "S12"}:

        numeric = pd.to_numeric(
            values,
            errors="coerce"
        )

        return pd.to_datetime(
            numeric,
            unit="s",
            utc=True,
            errors="coerce",
        ).dt.tz_convert(None)

    elif store_id in {"S06", "S07", "S08", "S09"}:

        return pd.to_datetime(
            values,
            format="%d-%m-%Y %H:%M:%S",
            errors="coerce",
        )

    else:

        return pd.to_datetime(
            values,
            errors="coerce",
        )


def build_product_lookup(cur):
    """
    Load product validity intervals from PostgreSQL.

    Product code alone is NOT sufficient because codes were
    reissued in June 2024.
    """

    cur.execute(
        """
        SELECT
            p.product_sk,
            p.product_code,
            p.valid_from,
            p.valid_to,
            dc.category_sk
        FROM dim_product p
        JOIN dim_category dc
            ON dc.category_sk = p.category_sk
        ORDER BY
            p.product_code,
            p.valid_from;
        """
    )

    rows = cur.fetchall()

    lookup = {}

    for (
        product_sk,
        product_code,
        valid_from,
        valid_to,
        category_sk,
    ) in rows:

        lookup.setdefault(
            str(product_code),
            []
        ).append(
            {
                "product_sk": product_sk,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "category_sk": category_sk,
            }
        )

    return lookup


def resolve_product(product_lookup, product_code, business_date):
    """
    Resolve product using:

        product_code + business_date

    rather than product_code alone.
    """

    candidates = product_lookup.get(
        str(product_code)
    )

    if not candidates:
        return None

    for candidate in candidates:

        if (
            candidate["valid_from"]
            <= business_date
            <= candidate["valid_to"]
        ):
            return candidate["product_sk"]

    return None


def calculate_revenue(df):
    """
    Apply the billing rules.

    Revenue:
        SALE      = qty * unit_price
        RETURN    = qty * unit_price
        DISCOUNT  = qty * unit_price
        VOID      = qty * unit_price

    Not revenue:
        TAX
        TENDER
    """

    df["qty"] = pd.to_numeric(
        df["qty"],
        errors="coerce"
    )

    df["unit_price"] = pd.to_numeric(
        df["unit_price"],
        errors="coerce"
    )

    df["line_type"] = (
        df["line_type"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    revenue_types = {
        "SALE",
        "RETURN",
        "DISCOUNT",
        "VOID",
    }

    df["revenue_amount"] = 0.0

    mask = df["line_type"].isin(
        revenue_types
    )

    df.loc[mask, "revenue_amount"] = (
        df.loc[mask, "qty"]
        * df.loc[mask, "unit_price"]
    )

    return df


def get_date_sk(cur, business_date):
    """
    Look up the surrogate date key.
    """

    cur.execute(
        """
        SELECT date_sk
        FROM dim_date
        WHERE full_date = %s;
        """,
        (business_date,),
    )

    result = cur.fetchone()

    if result is None:
        raise ValueError(
            f"No dim_date row for {business_date}"
        )

    return result[0]


def get_store_sk(cur, store_id):
    """
    Look up store surrogate key.
    """

    cur.execute(
        """
        SELECT store_sk
        FROM dim_store
        WHERE store_id = %s;
        """,
        (store_id,),
    )

    result = cur.fetchone()

    if result is None:
        raise ValueError(
            f"No dim_store row for {store_id}"
        )

    return result[0]


def insert_rows(cur, rows):
    """
    Insert rows into fact_sales.

    ON CONFLICT makes the ETL idempotent.

    Re-running the entire script will not duplicate an existing
    business line.
    """

    if not rows:
        return 0

    sql = """
        INSERT INTO fact_sales (
            store_sk,
            product_sk,
            date_sk,
            business_date,
            bill_no,
            line_no,
            product_code,
            qty,
            till_unit_price,
            line_type,
            transaction_ts,
            revenue_amount,
            source_object
        )
        VALUES %s
        ON CONFLICT (
            store_sk,
            business_date,
            bill_no,
            line_no
        )
        DO NOTHING;
    """

    execute_values(
        cur,
        sql,
        rows,
        page_size=BATCH_SIZE,
    )

    return len(rows)


# ============================================================
# MAIN ETL
# ============================================================

def main():

    print("=" * 70)
    print("ANNAPURNA STORES - SALES FACT ETL")
    print("=" * 70)

    cur = conn.cursor()

    # --------------------------------------------------------
    # Load master lookups
    # --------------------------------------------------------

    print("\nLoading product validity lookup...")

    product_lookup = build_product_lookup(cur)

    print(
        f"Product codes loaded: {len(product_lookup)}"
    )

    # --------------------------------------------------------
    # List MinIO objects
    # --------------------------------------------------------

    print("\nListing MinIO objects...")

    objects = []

    paginator = s3.get_paginator(
        "list_objects_v2"
    )

    for page in paginator.paginate(
        Bucket=BUCKET,
        Prefix="sales/",
    ):

        for obj in page.get("Contents", []):

            key = obj["Key"]

            if key.lower().endswith(
                (".csv", ".parquet")
            ):
                objects.append(
                    {
                        "key": key,
                        "size": obj["Size"],
                    }
                )

    objects.sort(
        key=lambda x: x["key"]
    )

    print(
        f"Sales objects found: {len(objects)}"
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    files_processed = 0
    files_failed = 0

    raw_lines = 0
    candidate_rows = 0
    inserted_rows = 0

    skipped_unknown_products = 0
    skipped_bad_rows = 0

    revenue_total = 0.0

    # --------------------------------------------------------
    # Process every object
    # --------------------------------------------------------

    for index, obj in enumerate(objects, start=1):

        key = obj["key"]

        try:

            store_id, business_date = (
                parse_object_name(key)
            )

            # ----------------------------------------------
            # Download object
            # ----------------------------------------------

            response = s3.get_object(
                Bucket=BUCKET,
                Key=key,
            )

            raw_bytes = response["Body"].read()

            # ----------------------------------------------
            # Read according to file type
            # ----------------------------------------------

            if key.lower().endswith(".csv"):

                df = read_csv_object(
                    raw_bytes,
                    store_id,
                )

            else:

                df = read_parquet_object(
                    raw_bytes
                )

            raw_lines += len(df)

            # ----------------------------------------------
            # Normalize core fields
            # ----------------------------------------------

            df["bill_no"] = (
                df["bill_no"]
                .astype(str)
                .str.strip()
            )

            df["line_no"] = pd.to_numeric(
                df["line_no"],
                errors="coerce",
            )

            df["product_code"] = (
                df["product_code"]
                .astype(str)
                .str.strip()
            )

            # ----------------------------------------------
            # Remove unusable line numbers
            # ----------------------------------------------

            before = len(df)

            df = df[
                df["line_no"].notna()
            ].copy()

            skipped_bad_rows += (
                before - len(df)
            )

            df["line_no"] = (
                df["line_no"]
                .astype(int)
            )

            # ----------------------------------------------
            # Revenue calculation
            # ----------------------------------------------

            df = calculate_revenue(df)

            # ----------------------------------------------
            # Transaction timestamp
            # ----------------------------------------------

            df["transaction_ts"] = (
                parse_transaction_timestamp(
                    df["ts"],
                    store_id,
                )
            )

            # ----------------------------------------------
            # Product resolution
            # ----------------------------------------------

            product_sks = []

            for product_code in df[
                "product_code"
            ]:

                product_sk = resolve_product(
                    product_lookup,
                    product_code,
                    business_date,
                )

                product_sks.append(
                    product_sk
                )

            df["product_sk"] = product_sks

            unknown_mask = (
                df["product_sk"].isna()
            )

            skipped_unknown_products += int(
                unknown_mask.sum()
            )

            # Product must resolve before loading
            df = df[
                ~unknown_mask
            ].copy()

            if df.empty:
                files_processed += 1
                continue

            df["product_sk"] = (
                df["product_sk"]
                .astype(int)
            )

            # ----------------------------------------------
            # Surrogate keys
            # ----------------------------------------------

            store_sk = get_store_sk(
                cur,
                store_id,
            )

            date_sk = get_date_sk(
                cur,
                business_date,
            )

            # ----------------------------------------------
            # Prepare database rows
            # ----------------------------------------------

            rows = []

            for row in df.itertuples(
                index=False
            ):

                transaction_ts = (
                    row.transaction_ts
                )

                if pd.isna(
                    transaction_ts
                ):
                    transaction_ts = None

                qty = (
                    None
                    if pd.isna(row.qty)
                    else float(row.qty)
                )

                till_price = (
                    None
                    if pd.isna(
                        row.unit_price
                    )
                    else float(
                        row.unit_price
                    )
                )

                revenue = (
                    0.0
                    if pd.isna(
                        row.revenue_amount
                    )
                    else float(
                        row.revenue_amount
                    )
                )

                rows.append(
                    (
                        store_sk,
                        int(row.product_sk),
                        date_sk,
                        business_date,
                        row.bill_no,
                        int(row.line_no),
                        row.product_code,
                        qty,
                        till_price,
                        row.line_type,
                        transaction_ts,
                        revenue,
                        key,
                    )
                )

            candidate_rows += len(rows)

            # ----------------------------------------------
            # Insert
            # ----------------------------------------------

            inserted_rows += insert_rows(
                cur,
                rows,
            )

            revenue_total += df[
                "revenue_amount"
            ].sum()

            files_processed += 1

            # Commit periodically
            if (
                files_processed % 100
                == 0
            ):
                conn.commit()

                print(
                    f"Processed "
                    f"{files_processed}/{len(objects)} "
                    f"files..."
                )

        except Exception as exc:

            conn.rollback()

            files_failed += 1

            print(
                "\nERROR:"
            )
            print(
                f"Object: {key}"
            )
            print(
                f"Reason: {exc}"
            )

    # --------------------------------------------------------
    # Final commit
    # --------------------------------------------------------

    conn.commit()

    # --------------------------------------------------------
    # Final database statistics
    # --------------------------------------------------------

    cur.execute(
        "SELECT COUNT(*) FROM fact_sales;"
    )

    fact_count = cur.fetchone()[0]

    cur.execute(
        """
        SELECT
            COALESCE(
                SUM(revenue_amount),
                0
            )
        FROM fact_sales;
        """
    )

    fact_revenue = float(
        cur.fetchone()[0]
    )

    # --------------------------------------------------------
    # Deterministic checksum
    # --------------------------------------------------------

    cur.execute(
        """
        SELECT md5(
            COALESCE(
                string_agg(
                    concat_ws(
                        '|',
                        store_sk,
                        business_date,
                        bill_no,
                        line_no,
                        product_sk,
                        qty,
                        till_unit_price,
                        line_type,
                        revenue_amount
                    ),
                    E'\\n'
                    ORDER BY
                        store_sk,
                        business_date,
                        bill_no,
                        line_no
                ),
                ''
            )
        )
        FROM fact_sales;
        """
    )

    checksum = cur.fetchone()[0]

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("ETL COMPLETE")
    print("=" * 70)

    print(
        f"Files found              : {len(objects):,}"
    )

    print(
        f"Files processed          : {files_processed:,}"
    )

    print(
        f"Files failed             : {files_failed:,}"
    )

    print(
        f"Raw lines read           : {raw_lines:,}"
    )

    print(
        f"Candidate fact rows      : {candidate_rows:,}"
    )

    print(
        f"Unknown products skipped : "
        f"{skipped_unknown_products:,}"
    )

    print(
        f"Bad rows skipped         : "
        f"{skipped_bad_rows:,}"
    )

    print(
        f"Rows inserted this run   : "
        f"{inserted_rows:,}"
    )

    print(
        f"Fact table rows          : "
        f"{fact_count:,}"
    )

    print(
        f"Fact revenue             : "
        f"₹{fact_revenue:,.2f}"
    )

    print(
        f"Fact checksum            : "
        f"{checksum}"
    )

    print("=" * 70)

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()