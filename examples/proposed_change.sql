ALTER TABLE analytics.customer_orders DROP COLUMN email;

ALTER TABLE analytics.customer_orders
ADD COLUMN lifecycle_status VARCHAR NOT NULL;

CREATE OR REPLACE VIEW analytics.order_export AS
SELECT * FROM analytics.customer_orders;
