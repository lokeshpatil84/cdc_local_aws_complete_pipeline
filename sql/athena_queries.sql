SELECT * FROM "cdc_demo_dev"."bronze_users"
ORDER BY processed_at DESC
LIMIT 20;

SELECT * FROM "cdc_demo_dev"."bronze_products"
ORDER BY processed_at DESC
LIMIT 20;

SELECT * FROM "cdc_demo_dev"."bronze_orders"
ORDER BY processed_at DESC
LIMIT 20;

SELECT op, COUNT(*) as cnt
FROM "cdc_demo_dev"."bronze_users"
GROUP BY op
ORDER BY cnt DESC;

SELECT * FROM "cdc_demo_dev"."bronze_users"
WHERE op = 'c'
ORDER BY ts_ms DESC
LIMIT 10;

SELECT
    id,
    name,
    email,
    op,
    ts_ms,
    processed_at
FROM "cdc_demo_dev"."bronze_users"
WHERE op = 'u'
ORDER BY ts_ms DESC
LIMIT 10;

SELECT * FROM "cdc_demo_dev"."bronze_users"
WHERE op = 'd'
ORDER BY ts_ms DESC
LIMIT 10;

SELECT
    'users' as table_name,
    COUNT(*) as total_events,
    COUNT(CASE WHEN op = 'c' THEN 1 END) as inserts,
    COUNT(CASE WHEN op = 'u' THEN 1 END) as updates,
    COUNT(CASE WHEN op = 'd' THEN 1 END) as deletes
FROM "cdc_demo_dev"."bronze_users"

UNION ALL

SELECT
    'products' as table_name,
    COUNT(*) as total_events,
    COUNT(CASE WHEN op = 'c' THEN 1 END) as inserts,
    COUNT(CASE WHEN op = 'u' THEN 1 END) as updates,
    COUNT(CASE WHEN op = 'd' THEN 1 END) as deletes
FROM "cdc_demo_dev"."bronze_products"

UNION ALL

SELECT
    'orders' as table_name,
    COUNT(*) as total_events,
    COUNT(CASE WHEN op = 'c' THEN 1 END) as inserts,
    COUNT(CASE WHEN op = 'u' THEN 1 END) as updates,
    COUNT(CASE WHEN op = 'd' THEN 1 END) as deletes
FROM "cdc_demo_dev"."bronze_orders";

