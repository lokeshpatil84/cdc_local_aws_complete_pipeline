import sys
import logging
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql.window import Window


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cdc-iceberg-job")

args = getResolvedOptions(sys.argv, ["JOB_NAME", "DATABASE_NAME", "S3_BUCKET"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

DATABASE = args["DATABASE_NAME"]
BUCKET = args["S3_BUCKET"]

logger.info(f"Starting CDC Processor - Database: {DATABASE}, Bucket: {BUCKET}")

spark.conf.set("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.warehouse", f"s3://{BUCKET}/iceberg/")
spark.conf.set("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")

spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{DATABASE}")
logger.info(f"Glue Catalog database glue_catalog.{DATABASE} verified/created")


def create_bronze_table(table):
    try:
        if table == "users":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.bronze_users (
                    id BIGINT, name STRING, email STRING, created_at BIGINT,
                    updated_at BIGINT, op STRING, ts_ms BIGINT, processed_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/bronze_users'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        elif table == "products":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.bronze_products (
                    id BIGINT, name STRING, price DOUBLE, category STRING,
                    created_at BIGINT, updated_at BIGINT, op STRING, ts_ms BIGINT, processed_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/bronze_products'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        elif table == "orders":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.bronze_orders (
                    id BIGINT, user_id BIGINT, product_id BIGINT, quantity INT,
                    total_amount DOUBLE, status STRING, created_at BIGINT, updated_at BIGINT,
                    op STRING, ts_ms BIGINT, processed_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/bronze_orders'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        logger.info(f"Bronze table glue_catalog.{DATABASE}.bronze_{table} created/verified")
    except Exception as e:
        logger.error(f"Error creating bronze table {table}: {str(e)}")
        raise


def create_silver_table(table):
    try:
        if table == "users":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.silver_users (
                    id BIGINT, name STRING, email STRING, email_domain STRING,
                    is_active BOOLEAN, op STRING, ts_ms BIGINT, processed_at TIMESTAMP,
                    _audit_updated_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/silver_users'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        elif table == "products":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.silver_products (
                    id BIGINT, name STRING, price DOUBLE, category STRING,
                    price_category STRING, is_active BOOLEAN, op STRING, ts_ms BIGINT, processed_at TIMESTAMP,
                    _audit_updated_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/silver_products'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        elif table == "orders":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS glue_catalog.{DATABASE}.silver_orders (
                    id BIGINT, user_id BIGINT, product_id BIGINT, quantity INT,
                    total_amount DOUBLE, status STRING, order_value_category STRING,
                    is_active BOOLEAN, op STRING, ts_ms BIGINT, processed_at TIMESTAMP,
                    _audit_updated_at TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{BUCKET}/iceberg/{DATABASE}/silver_orders'
                PARTITIONED BY (days(processed_at))
                TBLPROPERTIES ('format-version'='2', 'write.target-file-size-bytes'='134217728')
            """)
        logger.info(f"Silver table glue_catalog.{DATABASE}.silver_{table} created/verified")
    except Exception as e:
        logger.error(f"Error creating silver table {table}: {str(e)}")
        raise


def read_cdc(table):
    try:
        path = f"s3://{BUCKET}/raw/{table}/"
        logger.info(f"Reading CDC data from: {path}")

        df = spark.read.option("mode", "PERMISSIVE").json(path)

        if df.rdd.isEmpty():
            logger.info(f"No new CDC data for {table}")
            return None

        record_count = df.count()
        logger.info(f"Read {record_count} records from {table}")

        df = df.withColumnRenamed("__op", "op") \
               .withColumnRenamed("__ts_ms", "ts_ms") \
               .withColumn("processed_at", current_timestamp())

        if table == "users":
            df = df.select(
                "id", "name", "email", "created_at", "updated_at",
                "op", "ts_ms", "processed_at"
            ).withColumn("id", col("id").cast("long"))

        elif table == "products":
            df = df.select(
                "id", "name", "price", "category", "created_at", "updated_at",
                "op", "ts_ms", "processed_at"
            ).withColumn("id", col("id").cast("long")) \
                  .withColumn("price", col("price").cast("double"))

        elif table == "orders":
            df = df.select(
                "id", "user_id", "product_id", "quantity", "total_amount", "status",
                "created_at", "updated_at", "op", "ts_ms", "processed_at"
            ).withColumn("id", col("id").cast("long")) \
                  .withColumn("user_id", col("user_id").cast("long")) \
                  .withColumn("product_id", col("product_id").cast("long")) \
                  .withColumn("quantity", col("quantity").cast("int")) \
                  .withColumn("total_amount", col("total_amount").cast("double"))

        return df

    except Exception as e:
        logger.error(f"Error reading CDC data for {table}: {str(e)}")
        raise


def write_bronze(df, table):
    try:
        target_table = f"glue_catalog.{DATABASE}.bronze_{table}"
        logger.info(f"Writing to Bronze: {target_table}")

        df.writeTo(target_table) \
          .option("mergeSchema", "true") \
          .append()

        logger.info(f"Appended {df.count()} records to Bronze {table}")

    except Exception as e:
        logger.error(f"Error writing to bronze {table}: {str(e)}")
        raise


def merge_silver_proper(df, table):
    try:
        if table == "users":
            src_df = df.select(
                col("id").alias("src_id"),
                col("name").alias("src_name"),
                col("email").alias("src_email"),
                regexp_extract(col("email"), "@(.+)", 1).alias("email_domain"),
                when(col("op") == "d", False).otherwise(True).alias("is_active"),
                col("op"),
                col("ts_ms"),
                col("processed_at")
            ).withColumn("row_num", row_number().over(
                Window.partitionBy("src_id").orderBy(col("ts_ms").desc())
            ))

        elif table == "products":
            src_df = df.select(
                col("id").alias("src_id"),
                col("name").alias("src_name"),
                col("price").alias("src_price"),
                col("category").alias("src_category"),
                when(col("price") < 50, "Low")
                    .when(col("price") < 200, "Medium")
                    .otherwise("High").alias("price_category"),
                when(col("op") == "d", False).otherwise(True).alias("is_active"),
                col("op"),
                col("ts_ms"),
                col("processed_at")
            ).withColumn("row_num", row_number().over(
                Window.partitionBy("src_id").orderBy(col("ts_ms").desc())
            ))

        elif table == "orders":
            src_df = df.select(
                col("id").alias("src_id"),
                col("user_id").alias("src_user_id"),
                col("product_id").alias("src_product_id"),
                col("quantity").alias("src_quantity"),
                col("total_amount").alias("src_total_amount"),
                col("status").alias("src_status"),
                when(col("total_amount") < 100, "Small")
                    .when(col("total_amount") < 500, "Medium")
                    .otherwise("Large").alias("order_value_category"),
                when(col("op") == "d", False).otherwise(True).alias("is_active"),
                col("op"),
                col("ts_ms"),
                col("processed_at")
            ).withColumn("row_num", row_number().over(
                Window.partitionBy("src_id").orderBy(col("ts_ms").desc())
            ))

        latest_src = src_df.filter("row_num = 1").drop("row_num")
        latest_src.createOrReplaceTempView(f"silver_src_{table}")
        target_table = f"glue_catalog.{DATABASE}.silver_{table}"

        if table == "users":
            spark.sql(f"""
                MERGE INTO {target_table} AS tgt
                USING silver_src_{table} AS src
                ON tgt.id = src.src_id
                WHEN MATCHED AND src.src_ts_ms > tgt.ts_ms THEN
                    UPDATE SET
                        name = src.src_name,
                        email = src.src_email,
                        email_domain = src.email_domain,
                        is_active = src.is_active,
                        op = src.op,
                        ts_ms = src.src_ts_ms,
                        processed_at = src.processed_at,
                        _audit_updated_at = current_timestamp()
                WHEN MATCHED AND src.op = 'd' THEN
                    UPDATE SET
                        is_active = False,
                        op = 'd',
                        _audit_updated_at = current_timestamp()
                WHEN NOT MATCHED THEN
                    INSERT (id, name, email, email_domain, is_active, op, ts_ms, processed_at, _audit_updated_at)
                    VALUES (src.src_id, src.src_name, src.src_email, src.email_domain,
                            src.is_active, src.op, src.src_ts_ms, src.processed_at, current_timestamp())
            """)

        elif table == "products":
            spark.sql(f"""
                MERGE INTO {target_table} AS tgt
                USING silver_src_{table} AS src
                ON tgt.id = src.src_id
                WHEN MATCHED AND src.src_ts_ms > tgt.ts_ms THEN
                    UPDATE SET
                        name = src.src_name,
                        price = src.src_price,
                        category = src.src_category,
                        price_category = src.price_category,
                        is_active = src.is_active,
                        op = src.op,
                        ts_ms = src.src_ts_ms,
                        processed_at = src.processed_at,
                        _audit_updated_at = current_timestamp()
                WHEN MATCHED AND src.op = 'd' THEN
                    UPDATE SET
                        is_active = False,
                        op = 'd',
                        _audit_updated_at = current_timestamp()
                WHEN NOT MATCHED THEN
                    INSERT (id, name, price, category, price_category, is_active, op, ts_ms, processed_at, _audit_updated_at)
                    VALUES (src.src_id, src.src_name, src.src_price, src.src_category,
                            src.price_category, src.is_active, src.op, src.src_ts_ms, src.processed_at, current_timestamp())
            """)

        elif table == "orders":
            spark.sql(f"""
                MERGE INTO {target_table} AS tgt
                USING silver_src_{table} AS src
                ON tgt.id = src.src_id
                WHEN MATCHED AND src.src_ts_ms > tgt.ts_ms THEN
                    UPDATE SET
                        user_id = src.src_user_id,
                        product_id = src.src_product_id,
                        quantity = src.src_quantity,
                        total_amount = src.src_total_amount,
                        status = src.src_status,
                        order_value_category = src.order_value_category,
                        is_active = src.is_active,
                        op = src.op,
                        ts_ms = src.src_ts_ms,
                        processed_at = src.processed_at,
                        _audit_updated_at = current_timestamp()
                WHEN MATCHED AND src.op = 'd' THEN
                    UPDATE SET
                        is_active = False,
                        op = 'd',
                        _audit_updated_at = current_timestamp()
                WHEN NOT MATCHED THEN
                    INSERT (id, user_id, product_id, quantity, total_amount, status,
                            order_value_category, is_active, op, ts_ms, processed_at, _audit_updated_at)
                    VALUES (src.src_id, src.src_user_id, src.src_product_id, src.src_quantity,
                            src.src_total_amount, src.src_status, src.order_value_category,
                            src.is_active, src.op, src.src_ts_ms, src.processed_at, current_timestamp())
            """)

        logger.info(f"MERGE completed for Silver {table}")

    except Exception as e:
        logger.error(f"Error in MERGE for {table}: {str(e)}")
        raise


def process_table(table):
    try:
        logger.info(f"Processing table: {table}")

        create_bronze_table(table)
        create_silver_table(table)

        df = read_cdc(table)
        if df is None or df.rdd.isEmpty():
            logger.info(f"No new data for {table}, skipping")
            return

        write_bronze(df, table)
        merge_silver_proper(df, table)

        try:
            bronze_count = spark.sql(f"SELECT COUNT(*) FROM glue_catalog.{DATABASE}.bronze_{table}").collect()[0][0]
            silver_count = spark.sql(f"SELECT COUNT(*) FROM glue_catalog.{DATABASE}.silver_{table}").collect()[0][0]
            active_count = spark.sql(f"SELECT COUNT(*) FROM glue_catalog.{DATABASE}.silver_{table} WHERE is_active = true").collect()[0][0]
            logger.info(f"Counts - Bronze: {bronze_count}, Silver: {silver_count}, Active: {active_count}")
        except Exception as count_e:
            logger.warning(f"Could not get counts: {str(count_e)}")

    except Exception as e:
        logger.error(f"Failed processing table {table}: {str(e)}")
        logger.warning(f"Skipping table {table} due to error")


def optimize_tables():
    try:
        logger.info("Running Iceberg compaction...")
        for table in ["users", "products", "orders"]:
            for layer in ["bronze", "silver"]:
                try:
                    full_table = f"glue_catalog.{DATABASE}.{layer}_{table}"
                    spark.sql(f"OPTIMIZE {full_table} REWRITE DATA USING BIN_PACK")
                    logger.info(f"Optimized: {full_table}")
                except Exception as opt_e:
                    logger.warning(f"Optimization skip for {full_table}: {str(opt_e)}")
    except Exception as e:
        logger.warning(f"Optimization failed: {str(e)}")


def main():
    logger.info("Starting CDC Processing Pipeline")

    try:
        for tbl in ["users", "products", "orders"]:
            process_table(tbl)

        optimize_tables()

        logger.info("CDC Processing Pipeline Completed Successfully!")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
    job.commit()

