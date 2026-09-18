# Annapurna Stores – Sales Data Engineering Pipeline

## Question 1

This project implements an end-to-end data engineering and analytics pipeline for Annapurna Stores' daily sales data.

## Tools Used

- **MinIO** – Object storage
- **PostgreSQL** – Relational database and warehouse
- **DuckDB** – Analytical query engine and federation
- **Python / Pandas** – ETL and data processing
- **Docker Compose** – Infrastructure

## Architecture

```text
Daily Sales Files
       ↓
     MinIO
       ↓
   Python ETL
       ↓
  PostgreSQL
   Star Schema
       ↓
    DuckDB
       ↓
Analytics & Finance Reconciliation

1. Object Storage & Partitioning

Sales files were stored in MinIO using:

sales/<store_id>/<year>/<month>/<filename>

Example:

sales/S01/2024/10/SALES_S01_20241001.csv
Results
Metric	Result
Total files	4,457
Total bytes	68,706,877
S01 October files	31
S01 October bytes	846,899
Files avoided	99.30%
Bytes avoided	98.77%

This partitioning avoids scanning unrelated stores and months.

2. ETL Pipeline

The Python ETL:

Reads CSV and Parquet sales files
Handles different file formats and delimiters
Uses the filename date as the business date
Resolves historical product versions using product code and date
Applies SALE, RETURN, DISCOUNT and VOID revenue rules
Loads processed data into PostgreSQL
Prevents duplicate business lines using:
(store_sk, business_date, bill_no, line_no)
3. Star Schema

The warehouse contains:

dim_store
dim_category
dim_product
dim_date
fact_sales

fact_sales stores one valid sales transaction line.

The schema supports revenue analysis by:

Store
Product
Product category
Day of week
Month

Product reissues are handled using product_code together with validity dates.

4. Historical Pricing

Historical prices are obtained from price_revisions using the applicable product_sk and effective date.

Example for product P100005:

Period	Selling Price
March 2024	₹103.45
October 2024	₹114.37

This demonstrates historical price selection based on the reporting period.

5. DuckDB Federation

DuckDB was used as the analytical query engine to query data across PostgreSQL and MinIO.

EXPLAIN was used to inspect the query plan and demonstrate filtering, projection and aggregation operations.

6. ETL Results
Metric	Result
Files found	4,457
Files processed	4,457
Files failed	0
Raw lines read	1,137,585
Candidate fact rows	778,145
Unknown products skipped	359,440
Bad rows skipped	0
Final fact rows	766,796
Fact revenue	₹528,135,952.13
7. Idempotency

The ETL uses ON CONFLICT DO NOTHING with the business-line uniqueness key.

The pipeline is executed three times to verify that repeated execution does not create duplicate records.

Run	Fact Rows	Checksum
1	766,796	3779d3ac1d4cd1951b01ab993bd07e2
2	To be filled	To be filled
3	To be filled	To be filled

The row count and checksum should remain unchanged across all three runs.

8. Finance Reconciliation

The calculated monthly revenue is compared with finance_monthly.csv.

Differences are classified as:

Pipeline bug
Definition difference
Source-data problem

Known data differences include the missing S07 Pune files in July, the March institutional invoice outside the till data, and December Finance rounding.

9. Final Question 1 Result

October 2024 Revenue: To be filled after final validation.

data-mining-lab-1/
├── README.md       ← HERE
├── scripts/
│   ├── federation.py
│   ├── load_fact_sales.py
│   ├── reconcile.py
│   ├── upload_sales.py
│   └── verify_partition.py
├── sql/
│   └── warehouse_schema.sql
├── data/
├── output/
└── docker-compose.yml

Conclusion

The project implements a complete sales data pipeline using MinIO, Python, PostgreSQL and DuckDB, covering partitioned storage, ETL, idempotency, star-schema analytics, historical pricing, federation and finance reconciliation.











# SetuBid – Tender Deduplication Pipeline

## Question 2

This project develops a scalable system to identify duplicate procurement notices without comparing every notice against every other notice.

## Dataset

- `notices/` – Procurement notices in Parquet format
- `labelled_pairs.csv` – 900 manually adjudicated pairs
- `portal_profiles.md` – Portal formatting information

## Initial Label Analysis

| Label | Count | Percentage |
|---|---:|---:|
| Different | 621 | 69.0% |
| Same | 279 | 31.0% |

The labelled dataset is imbalanced toward **different** pairs, so this distribution is considered when evaluating the system.

## Section A – Similarity Representation

Two text representations were considered:

- Word-level 3-shingles
- Character-level 5-grams

Portal URLs, reference numbers, dates and monetary formatting are treated as noise, while procurement wording and descriptive terms are retained as signal.

Similarity is measured using Jaccard similarity:

\[
J(A,B)=\frac{|A\cap B|}{|A\cup B|}
\]

The representations are compared using the manually labelled pairs.

## Implementation

The main analysis scripts are:

```text
scripts/q2_analysis.py
scripts/q2_similarity.py


Initial label analysis was saved to:

output/q2_label_distribution.csv

Similarity results will be saved to:

output/q2_similarity_results.csv
Project Structure
data-mining-lab-1/
├── data/
│   └── notices/
├── output/
├── scripts/
│   ├── q2_analysis.py
│   ├── q2_similarity.py
│   ├── federation.py
│   ├── reconcile.py
│   └── ...
├── labelled_pairs.csv
├── portal_profiles.md
├── docker-compose.yml
└── README.md
Current Status
Label analysis: Completed
Label imbalance: Identified
Similarity representations: Implemented
Similarity measurement: In progress
Candidate retrieval: Pending
Database access path: Pending
Full-corpus performance analysis: Pending


Conclusion:

The initial analysis establishes the labelled-pair distribution and the text representations required for the deduplication system. Further sections will measure similarity accuracy, candidate retrieval, database performance and full-corpus runtime.