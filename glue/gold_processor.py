import sys
import logging
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import *
from pyspark.sql.types import *
from pyspark.sql.window import Window


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'DATABASE_NAME', 'S3_BUCKET'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

DATABASE_NAME = args['DATABASE_NAME']
S3_BUCKET = args['S3_BUCKET']

logger.info(f"Starting Gold Processor - Database: {DATABASE_NAME}")

spark.conf.set("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog")
spark.conf.set("spark.sql.catalog.glue_catalog.warehouse", f"s3://{S3_BUCKET}/iceberg/")
spark.conf.set("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")

spark.sql(f"CREATE DATABASE IF NOT EXISTS glue_catalog.{DATABASE_NAME}")
logger.info(f"Glue Catalog database glue_catalog.{DATABASE_NAME} verified/created")


def create_gold_table(table_name: str):
    table_identifier = f"glue_catalog.{DATABASE_NAME}.gold_{table_name}"

    try:
        if table_name == "user_analytics":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS {table_identifier} (
                    user_id BIGINT, full_name STRING, email_domain STRING,
                    registration_date STRING, total_orders BIGINT, total_spent DOUBLE,
                    avg_order_value DOUBLE, user_segment STRING, last_activity TIMESTAMP,
                    refresh_date TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{S3_BUCKET}/iceberg/{DATABASE_NAME}/gold_user_analytics'
                TBLPROPERTIES ('format-version'='2')
            """)
        elif table_name == "product_analytics":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS {table_identifier} (
                    product_id BIGINT, product_name STRING, category STRING,
                    price DOUBLE, total_orders BIGINT, total_revenue DOUBLE,
                    unique_customers BIGINT, performance_category STRING,
                    refresh_date TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{S3_BUCKET}/iceberg/{DATABASE_NAME}/gold_product_analytics'
                TBLPROPERTIES ('format-version'='2')
            """)
        elif table_name == "sales_summary":
            spark.sql(f"""
                CREATE TABLE IF NOT EXISTS {table_identifier} (
                    date_key STRING, total_orders BIGINT, total_revenue DOUBLE,
                    avg_order_value DOUBLE, unique_customers BIGINT, top_product BIGINT,
                    refresh_date TIMESTAMP
                ) USING iceberg
                LOCATION 's3://{S3_BUCKET}/iceberg/{DATABASE_NAME}/gold_sales_summary'
                TBLPROPERTIES ('format-version'='2')
            """)
        logger.info(f"Gold table {table_identifier} verified/created")
    except Exception as e:
        logger.error(f"Error creating gold table {table_name}: {str(e)}")
        raise


def process_user_analytics():
    logger.info("Processing user analytics")

    silver_users = f"glue_catalog.{DATABASE_NAME}.silver_users"
    silver_orders = f"glue_catalog.{DATABASE_NAME}.silver_orders"
    gold_table = f"glue_catalog.{DATABASE_NAME}.gold_user_analytics"

    try:
        if not spark.catalog.tableExists(silver_users):
            logger.warning(f"{silver_users} does not exist, skipping")
            return
        if not spark.catalog.tableExists(silver_orders):
            logger.warning(f"{silver_orders} does not exist, skipping")
            return

        users_df = spark.read.table(silver_users).filter("is_active = true")
        orders_df = spark.read.table(silver_orders).filter("is_active = true")

        user_stats = orders_df.groupBy("user_id").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_spent"),
            avg("total_amount").alias("avg_order_value")
        )

        user_analytics = users_df.join(
            user_stats, users_df["id"] == user_stats["user_id"], "left"
        ).select(
            users_df["id"].alias("user_id"),
            users_df["name"].alias("full_name"),
            users_df["email_domain"],
            date_format(users_df["processed_at"], "yyyy-MM-dd").alias("registration_date"),
            coalesce(user_stats["total_orders"], lit(0)).alias("total_orders"),
            coalesce(user_stats["total_spent"], lit(0.0)).alias("total_spent"),
            coalesce(user_stats["avg_order_value"], lit(0.0)).alias("avg_order_value"),
            when(coalesce(user_stats["total_spent"], lit(0.0)) > 1000, "Premium")
                .when(coalesce(user_stats["total_spent"], lit(0.0)) > 500, "Regular")
                .otherwise("New").alias("user_segment"),
            users_df["processed_at"].alias("last_activity"),
            current_timestamp().alias("refresh_date")
        )

        create_gold_table("user_analytics")
        user_analytics.writeTo(gold_table).replace()

        user_count = user_analytics.count()
        logger.info(f"Written {user_count} user analytics records")

    except Exception as e:
        logger.error(f"Error in user analytics: {str(e)}")
        raise


def process_product_analytics():
    logger.info("Processing product analytics")

    silver_products = f"glue_catalog.{DATABASE_NAME}.silver_products"
    silver_orders = f"glue_catalog.{DATABASE_NAME}.silver_orders"
    gold_table = f"glue_catalog.{DATABASE_NAME}.gold_product_analytics"

    try:
        if not spark.catalog.tableExists(silver_products):
            logger.warning(f"{silver_products} does not exist, skipping")
            return
        if not spark.catalog.tableExists(silver_orders):
            logger.warning(f"{silver_orders} does not exist, skipping")
            return

        products_df = spark.read.table(silver_products).filter("is_active = true")
        orders_df = spark.read.table(silver_orders).filter("is_active = true")

        product_stats = orders_df.groupBy("product_id").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_revenue"),
            countDistinct("user_id").alias("unique_customers")
        )

        product_analytics = products_df.join(
            product_stats, products_df["id"] == product_stats["product_id"], "left"
        ).select(
            products_df["id"].alias("product_id"),
            products_df["name"].alias("product_name"),
            products_df["category"],
            products_df["price"],
            coalesce(product_stats["total_orders"], lit(0)).alias("total_orders"),
            coalesce(product_stats["total_revenue"], lit(0.0)).alias("total_revenue"),
            coalesce(product_stats["unique_customers"], lit(0)).alias("unique_customers"),
            when(coalesce(product_stats["total_revenue"], lit(0.0)) > 5000, "Top Performer")
                .when(coalesce(product_stats["total_revenue"], lit(0.0)) > 1000, "Good")
                .otherwise("Average").alias("performance_category"),
            current_timestamp().alias("refresh_date")
        )

        create_gold_table("product_analytics")
        product_analytics.writeTo(gold_table).replace()

        product_count = product_analytics.count()
        logger.info(f"Written {product_count} product analytics records")

    except Exception as e:
        logger.error(f"Error in product analytics: {str(e)}")
        raise


def process_sales_summary():
    logger.info("Processing sales summary")

    silver_orders = f"glue_catalog.{DATABASE_NAME}.silver_orders"
    gold_table = f"glue_catalog.{DATABASE_NAME}.gold_sales_summary"

    try:
        if not spark.catalog.tableExists(silver_orders):
            logger.warning(f"{silver_orders} does not exist, skipping")
            return

        orders_df = spark.read.table(silver_orders).filter("is_active = true")

        orders_df = orders_df.withColumn(
            "created_at_ts",
            from_unixtime(col("created_at") / 1000)
        ).withColumn(
            "date_key",
            date_format(col("created_at_ts"), "yyyy-MM-dd")
        )

        sales_summary = orders_df.groupBy("date_key").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_revenue"),
            avg("total_amount").alias("avg_order_value"),
            countDistinct("user_id").alias("unique_customers")
        )

        product_revenue = orders_df.groupBy("date_key", "product_id").agg(
            sum("total_amount").alias("product_revenue")
        )

        window = Window.partitionBy("date_key").orderBy(col("product_revenue").desc())
        top_product_per_day = product_revenue.withColumn("rank", row_number().over(window)) \
            .filter("rank = 1") \
            .select("date_key", col("product_id").alias("top_product"))

        final_summary = sales_summary.join(top_product_per_day, "date_key", "left").select(
            col("date_key"),
            col("total_orders"),
            col("total_revenue"),
            col("avg_order_value"),
            col("unique_customers"),
            coalesce(col("top_product"), lit(0)).alias("top_product"),
            current_timestamp().alias("refresh_date")
        )

        create_gold_table("sales_summary")
        final_summary.writeTo(gold_table).replace()

        sales_count = final_summary.count()
        logger.info(f"Written {sales_count} sales summary records")

    except Exception as e:
        logger.error(f"Error in sales summary: {str(e)}")
        raise


def main():
    logger.info("=" * 50)
    logger.info("Starting Gold Layer Processing")
    logger.info("=" * 50)

    try:
        process_user_analytics()
        process_product_analytics()
        process_sales_summary()

        logger.info("=" * 50)
        logger.info("Gold Tables Summary:")
        gold_tables = ["user_analytics", "product_analytics", "sales_summary"]
        for table in gold_tables:
            try:
                result = spark.sql(f"SELECT COUNT(*) FROM glue_catalog.{DATABASE_NAME}.gold_{table}")
                count = result.collect()[0][0]
                logger.info(f"  glue_catalog.{DATABASE_NAME}.gold_{table}: {count} records")
            except Exception as e:
                logger.warning(f"  glue_catalog.{DATABASE_NAME}.gold_{table}: Error - {str(e)}")

        logger.info("=" * 50)
        logger.info("Gold job completed successfully!")
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Gold job failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
    job.commit()

