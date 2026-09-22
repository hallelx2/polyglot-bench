DROP TABLE IF EXISTS loyalty_transaction, ledger_entry, order_item, "order",
  inventory, coupon, discount_rule, tax_rate, product, customer, customer_tier CASCADE;

CREATE TABLE customer_tier (
  id                              INT PRIMARY KEY,
  name                            TEXT NOT NULL,
  points_multiplier               INT  NOT NULL,
  free_shipping_threshold_cents   INT  NOT NULL,
  bonus_points                    INT  NOT NULL
);

CREATE TABLE customer (
  id         INT PRIMARY KEY,
  email      TEXT NOT NULL,
  full_name  TEXT NOT NULL,
  region     TEXT NOT NULL,
  tier_id    INT  NOT NULL REFERENCES customer_tier(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON customer (region);

CREATE TABLE product (
  id               INT PRIMARY KEY,
  sku              TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  category         TEXT NOT NULL,
  unit_price_cents INT  NOT NULL,
  weight_grams     INT  NOT NULL,
  tax_exempt       BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX ON product (category);

CREATE TABLE inventory (
  warehouse_id INT NOT NULL,
  product_id   INT NOT NULL REFERENCES product(id),
  on_hand      INT NOT NULL,
  reserved     INT NOT NULL DEFAULT 0,
  PRIMARY KEY (warehouse_id, product_id)
);

CREATE TABLE discount_rule (
  id                  INT PRIMARY KEY,
  scope               TEXT NOT NULL,          -- tier | category | volume | sku
  tier_id             INT,
  category            TEXT,
  min_qty             INT,
  sku                 TEXT,
  percent_bp          INT NOT NULL,
  max_discount_cents  INT,
  stackable           BOOLEAN NOT NULL,
  active_from         DATE NOT NULL,
  active_to           DATE NOT NULL
);
CREATE INDEX ON discount_rule (active_from, active_to);

CREATE TABLE tax_rate (
  id       INT PRIMARY KEY,
  region   TEXT NOT NULL,
  category TEXT,                              -- NULL = region default
  rate_bp  INT NOT NULL
);
CREATE INDEX ON tax_rate (region);

CREATE TABLE coupon (
  id               INT PRIMARY KEY,
  code             TEXT NOT NULL UNIQUE,
  percent_bp       INT NOT NULL,
  max_discount_cents INT NOT NULL,
  min_spend_cents  INT NOT NULL,
  max_uses         INT NOT NULL,
  times_used       INT NOT NULL DEFAULT 0,
  expires_on       DATE NOT NULL
);

CREATE TABLE "order" (
  id            BIGSERIAL PRIMARY KEY,
  customer_id   INT NOT NULL REFERENCES customer(id),
  warehouse_id  INT NOT NULL,
  subtotal_cents INT NOT NULL,
  coupon_id     INT,
  coupon_discount_cents INT NOT NULL,
  tax_total_cents INT NOT NULL,
  shipping_cents  INT NOT NULL,
  total_cents     INT NOT NULL,
  points_earned   INT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON "order" (customer_id, created_at DESC);

CREATE TABLE order_item (
  id             BIGSERIAL PRIMARY KEY,
  order_id       BIGINT NOT NULL REFERENCES "order"(id),
  product_id     INT NOT NULL,
  sku            TEXT NOT NULL,
  category       TEXT NOT NULL,
  qty            INT NOT NULL,
  unit_price_cents INT NOT NULL,
  discount_cents INT NOT NULL,
  net_cents      INT NOT NULL,
  tax_cents      INT NOT NULL
);
CREATE INDEX ON order_item (order_id);

CREATE TABLE ledger_entry (
  id       BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL,
  account  TEXT NOT NULL,
  debit_cents  INT NOT NULL,
  credit_cents INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE loyalty_transaction (
  id          BIGSERIAL PRIMARY KEY,
  customer_id INT NOT NULL,
  order_id    BIGINT,
  points      INT NOT NULL,
  kind        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON loyalty_transaction (customer_id, created_at DESC);

-- Autovacuum is disabled on the tables the benchmark churns. Each checkout run
-- inserts tens of thousands of rows and the reset deletes them again; left to
-- itself, autovacuum fires mid-measurement and competes with the very queries
-- being timed. bench/reset.sh vacuums explicitly between runs instead, so the
-- work still happens — just never while a stopwatch is running.
ALTER TABLE "order"              SET (autovacuum_enabled = false);
ALTER TABLE order_item           SET (autovacuum_enabled = false);
ALTER TABLE ledger_entry         SET (autovacuum_enabled = false);
ALTER TABLE loyalty_transaction  SET (autovacuum_enabled = false);
ALTER TABLE inventory            SET (autovacuum_enabled = false);
ALTER TABLE coupon               SET (autovacuum_enabled = false);
