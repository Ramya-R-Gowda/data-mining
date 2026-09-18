import os
import re
import boto3
from botocore.exceptions import ClientError


# ============================================================
# CONFIGURATION
# ============================================================

# ORIGINAL EXAM DATA
# We READ from this folder.
# We DO NOT modify it.
SOURCE_DIR = r"C:\Users\ub02-glab-017\Downloads\data_2\data\sales"

# MinIO
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

# Bucket created in MinIO
BUCKET_NAME = "annapurna-sales"

# Object-store prefix
OBJECT_PREFIX = "sales"


# ============================================================
# EXPECTED SALES FILENAME FORMAT
# ============================================================
#
# SALES_S01_20240101.csv
# SALES_S01_20240101.parquet
# SALES_S01_20240101__R1.csv
# SALES_S01_20240101__R2.parquet
#

FILENAME_PATTERN = re.compile(
    r"^SALES_(S\d{2})_(\d{8})(?:__R\d+)?\.(csv|parquet)$",
    re.IGNORECASE
)


# ============================================================
# CONNECT TO MINIO
# ============================================================

print("=" * 70)
print("ANNAPURNA STORES - MINIO SALES UPLOAD")
print("=" * 70)

print("\nConnecting to MinIO...")

s3 = boto3.client(
    "s3",
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY,
    region_name="us-east-1"
)


# ============================================================
# CHECK BUCKET
# ============================================================

try:

    s3.head_bucket(Bucket=BUCKET_NAME)

    print(f"Connected successfully.")
    print(f"Bucket found: {BUCKET_NAME}")

except Exception as e:

    print("\nERROR: Could not access the MinIO bucket.")
    print(e)
    raise SystemExit(1)


# ============================================================
# CHECK SOURCE DIRECTORY
# ============================================================

if not os.path.isdir(SOURCE_DIR):

    print("\nERROR: Sales source folder was not found:")
    print(SOURCE_DIR)

    raise SystemExit(1)


print("\nSource folder:")
print(SOURCE_DIR)


# ============================================================
# COUNTERS
# ============================================================

files_found = 0
files_uploaded = 0
files_existing = 0
files_invalid = 0
files_failed = 0

bytes_uploaded = 0


# ============================================================
# SCAN AND UPLOAD
# ============================================================

print("\nScanning sales files...")
print("-" * 70)


for root, dirs, files in os.walk(SOURCE_DIR):

    for filename in files:

        # Only process CSV and Parquet
        if not filename.lower().endswith((".csv", ".parquet")):
            continue

        files_found += 1

        # ----------------------------------------------------
        # Validate filename
        # ----------------------------------------------------

        match = FILENAME_PATTERN.match(filename)

        if not match:

            print(f"INVALID FILENAME: {filename}")

            files_invalid += 1

            continue

        # ----------------------------------------------------
        # Extract store and business date
        # ----------------------------------------------------

        store_id = match.group(1).upper()
        business_date = match.group(2)

        year = business_date[:4]
        month = business_date[4:6]

        # ----------------------------------------------------
        # Local file
        # ----------------------------------------------------

        local_path = os.path.join(root, filename)

        file_size = os.path.getsize(local_path)

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Store -> Year -> Month -> File
        #
        # Example:
        #
        # sales/S01/2024/10/SALES_S01_20241001.csv
        #
        # ----------------------------------------------------

        object_key = (
            f"{OBJECT_PREFIX}/"
            f"{store_id}/"
            f"{year}/"
            f"{month}/"
            f"{filename}"
        )

        # ----------------------------------------------------
        # Check whether object already exists
        #
        # This prevents uploading the same object again.
        # ----------------------------------------------------

        try:

            s3.head_object(
                Bucket=BUCKET_NAME,
                Key=object_key
            )

            files_existing += 1

            continue

        except ClientError as e:

            error_code = str(
                e.response.get("Error", {}).get("Code", "")
            )

            if error_code not in (
                "404",
                "NoSuchKey",
                "NotFound"
            ):

                print(f"ERROR CHECKING: {object_key}")
                print(e)

                files_failed += 1

                continue

        # ----------------------------------------------------
        # Upload
        # ----------------------------------------------------

        try:

            s3.upload_file(
                local_path,
                BUCKET_NAME,
                object_key
            )

            files_uploaded += 1
            bytes_uploaded += file_size

            # Print progress every 100 files
            if files_uploaded % 100 == 0:

                print(
                    f"Uploaded {files_uploaded} files..."
                )

        except Exception as e:

            print(f"\nUPLOAD FAILED: {filename}")
            print(e)

            files_failed += 1


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 70)
print("UPLOAD COMPLETE")
print("=" * 70)

print(f"Files found       : {files_found}")
print(f"Files uploaded    : {files_uploaded}")
print(f"Files already exist: {files_existing}")
print(f"Invalid filenames : {files_invalid}")
print(f"Failed uploads    : {files_failed}")
print(f"Bytes uploaded    : {bytes_uploaded:,}")

print("\nMinIO bucket:")
print(BUCKET_NAME)

print("\nObject layout:")
print("sales/<store>/<year>/<month>/<filename>")

print("\nExample:")
print(
    "sales/S01/2024/10/SALES_S01_20241001.csv"
)

print("\nDone.")