import boto3

MINIO_ENDPOINT = "http://localhost:9000"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"
BUCKET = "annapurna-sales"

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    region_name="us-east-1"
)


def get_stats(prefix):
    count = 0
    total_bytes = 0

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=BUCKET,
        Prefix=prefix
    ):
        for obj in page.get("Contents", []):
            count += 1
            total_bytes += obj["Size"]

    return count, total_bytes


# ------------------------------------------------------------
# ALL SALES FILES
# ------------------------------------------------------------

all_count, all_bytes = get_stats("sales/")


# ------------------------------------------------------------
# ONE STORE + ONE MONTH
# S01 October 2024
# ------------------------------------------------------------

target_prefix = "sales/S01/2024/10/"

target_count, target_bytes = get_stats(target_prefix)


# ------------------------------------------------------------
# RESULTS
# ------------------------------------------------------------

print("=" * 65)
print("MINIO PARTITIONING VERIFICATION")
print("=" * 65)

print("\nALL SALES FILES")
print(f"Files : {all_count:,}")
print(f"Bytes : {all_bytes:,}")

print("\nTARGET QUERY")
print(f"Prefix: {target_prefix}")
print(f"Files : {target_count:,}")
print(f"Bytes : {target_bytes:,}")

print("\nPARTITIONING BENEFIT")

if all_count > 0:

    file_reduction = (
        1 - (target_count / all_count)
    ) * 100

    byte_reduction = (
        1 - (target_bytes / all_bytes)
    ) * 100

    print(
        f"Files avoided : {file_reduction:.2f}%"
    )

    print(
        f"Bytes avoided : {byte_reduction:.2f}%"
    )

print("\nObject layout:")
print("sales/<store>/<year>/<month>/<filename>")

print("=" * 65)