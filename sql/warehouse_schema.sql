-- ============================================================
-- ANNAPURNA STORES
-- ANALYTICAL STAR SCHEMA
-- ============================================================

-- ------------------------------------------------------------
-- 1. STORE DIMENSION
-- ------------------------------------------------------------

DROP TABLE IF EXISTS fact_sales CASCADE;
DROP TABLE IF EXISTS dim_date CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;
DROP TABLE IF EXISTS dim_category CASCADE;
DROP TABLE IF EXISTS dim_store CASCADE;


CREATE TABLE dim_store (
    store_sk        SERIAL PRIMARY KEY,
    store_id        VARCHAR(10) NOT NULL UNIQUE,
    store_name      VARCHAR(200) NOT NULL,
    address_line    VARCHAR(300),
    city            VARCHAR(100),
    state           VARCHAR(100),
    region          VARCHAR(100),
    floor_area_sqft NUMERIC,
    opened_on       DATE
);


-- ------------------------------------------------------------
-- 2. CATEGORY DIMENSION
-- ------------------------------------------------------------

CREATE TABLE dim_category (
    category_sk     SERIAL PRIMARY KEY,
    category_id     VARCHAR(10) NOT NULL UNIQUE,
    category_name   VARCHAR(200) NOT NULL,
    department      VARCHAR(100),
    gst_rate        NUMERIC(8,4)
);


-- ------------------------------------------------------------
-- 3. PRODUCT DIMENSION
--
-- IMPORTANT:
-- product_code is NOT unique.
--
-- product_sk identifies the correct historical product version.
-- ------------------------------------------------------------

CREATE TABLE dim_product (
    product_sk      INTEGER PRIMARY KEY,
    product_code    VARCHAR(50) NOT NULL,
    product_name    VARCHAR(300),
    category_sk     INTEGER NOT NULL,
    brand           VARCHAR(200),
    pack_size       VARCHAR(100),
    uom             VARCHAR(50),
    valid_from      DATE NOT NULL,
    valid_to        DATE NOT NULL,
    is_current      BOOLEAN NOT NULL,

    CONSTRAINT fk_dim_product_category
        FOREIGN KEY (category_sk)
        REFERENCES dim_category(category_sk)
);


CREATE INDEX idx_dim_product_code_dates
ON dim_product(product_code, valid_from, valid_to);


-- ------------------------------------------------------------
-- 4. DATE DIMENSION
-- ------------------------------------------------------------

CREATE TABLE dim_date (
    date_sk         INTEGER PRIMARY KEY,
    full_date       DATE NOT NULL UNIQUE,
    day_of_month    INTEGER NOT NULL,
    day_name        VARCHAR(20) NOT NULL,
    day_of_week     INTEGER NOT NULL,
    week_of_year    INTEGER NOT NULL,
    month_number    INTEGER NOT NULL,
    month_name      VARCHAR(20) NOT NULL,
    quarter_number  INTEGER NOT NULL,
    year_number     INTEGER NOT NULL
);


CREATE INDEX idx_dim_date_month
ON dim_date(year_number, month_number);


-- ------------------------------------------------------------
-- 5. SALES FACT TABLE
--
-- Grain:
-- ONE valid sales transaction line.
--
-- We retain line_type because not every billing line is revenue.
-- ------------------------------------------------------------

CREATE TABLE fact_sales (
    sales_sk        BIGSERIAL PRIMARY KEY,

    store_sk        INTEGER NOT NULL,
    product_sk      INTEGER NOT NULL,
    date_sk         INTEGER NOT NULL,

    business_date   DATE NOT NULL,

    bill_no         VARCHAR(100) NOT NULL,
    line_no         INTEGER NOT NULL,

    product_code    VARCHAR(50) NOT NULL,

    qty             NUMERIC(18,4),
    till_unit_price NUMERIC(18,4),

    line_type       VARCHAR(20) NOT NULL,

    transaction_ts  TIMESTAMP,

    -- Revenue contribution after applying line-type rules
    revenue_amount  NUMERIC(18,4) NOT NULL DEFAULT 0,

    source_object   TEXT NOT NULL,

    CONSTRAINT fk_fact_store
        FOREIGN KEY (store_sk)
        REFERENCES dim_store(store_sk),

    CONSTRAINT fk_fact_product
        FOREIGN KEY (product_sk)
        REFERENCES dim_product(product_sk),

    CONSTRAINT fk_fact_date
        FOREIGN KEY (date_sk)
        REFERENCES dim_date(date_sk),

    CONSTRAINT uq_fact_business_line
        UNIQUE (
            store_sk,
            business_date,
            bill_no,
            line_no
        )
);


-- ------------------------------------------------------------
-- FACT TABLE INDEXES
-- ------------------------------------------------------------

CREATE INDEX idx_fact_store
ON fact_sales(store_sk);

CREATE INDEX idx_fact_product
ON fact_sales(product_sk);

CREATE INDEX idx_fact_date
ON fact_sales(date_sk);

CREATE INDEX idx_fact_store_date
ON fact_sales(store_sk, business_date);

CREATE INDEX idx_fact_product_date
ON fact_sales(product_sk, business_date);

CREATE INDEX idx_fact_line_type
ON fact_sales(line_type);


-- ------------------------------------------------------------
-- VERIFY TABLES
-- ------------------------------------------------------------

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
      'dim_store',
      'dim_category',
      'dim_product',
      'dim_date',
      'fact_sales'
  )
ORDER BY table_name;

ALTER TABLE fact_sales DROP CONSTRAINT IF EXISTS fact_sales_line_type_check;

ALTER TABLE fact_sales
ADD CONSTRAINT fact_sales_line_type_check
CHECK (line_type IN ('SALE','RETURN','DISCOUNT','VOID'));