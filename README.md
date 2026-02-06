# CDC Data Pipeline

Real-time data pipeline that captures database changes and processes them through a lakehouse architecture.

## Architecture

```
PostgreSQL -> Debezium -> Kafka -> Glue (Bronze/Silver) -> S3/Iceberg -> Athena
```

### Flow
1. PostgreSQL database stores source data
2. Debezium captures INSERT/UPDATE/DELETE operations
3. Kafka acts as event backbone
4. Glue jobs process data into Bronze (raw) and Silver (cleaned) layers
5. Data stored in S3 using Apache Iceberg format
6. Athena used for querying

## Project Structure

```
├── docker-compose.yml      # Local development setup
├── run.sh                  # Local operations script
├── requirements.txt        # Python dependencies
├── sql/
│   └── init.sql           # Database schema
├── glue/
│   ├── cdc_processor.py   # Bronze/Silver processing
│   └── gold_processor.py  # Analytics layer
├── airflow/
│   └── dags/
│       └── cdc_pipeline_dag.py  # Pipeline orchestration
├── scripts/
│   ├── debezium_connector.py  # Connector management
│   └── verify_cdc.py          # Verification script
└── terraform/
    ├── main.tf            # Infrastructure definition
    └── modules/           # AWS resource modules
```

## Local Development

```bash
# Start all services
./run.sh start

# Setup connectors
./run.sh connectors

# Run CDC test
./run.sh test

# View events in Kafka
docker exec cdc-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic cdc.public.users \
  --from-beginning
```

## AWS Deployment

```bash
# Configure AWS credentials
aws configure

# Deploy infrastructure
cd terraform
terraform init
terraform plan -out=tfplan-dev
terraform apply tfplan-dev

# Upload scripts to S3
aws s3 cp glue/ s3://bucket/scripts/ --recursive
aws s3 cp airflow/dags/ s3://bucket/dags/ --recursive
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| PostgreSQL | 5432 | Source database |
| Kafka | 9092 | Event streaming |
| Debezium | 8083 | CDC connector |

## Database Tables

- **users** - User information
- **products** - Product catalog
- **orders** - Order transactions

## Athena Queries

```sql
-- Bronze layer
SELECT * FROM "database".bronze_users;

-- Silver layer
SELECT * FROM "database".silver_users;

-- Gold layer
SELECT * FROM "database".gold_user_analytics;
```


┌─────────────────────────────────────────────────────────────────────────┐
│ POSTGRESSQL (RDS or EC2) │
│ wal_level = logical → Logical Replication │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ DEBEZIUM CONNECT (ECS Fargate or EC2) │
│ • Captures CDC events in real-time │
│ • Converts DB changes to Kafka Events │
│ • Handles schema evolution │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ APACHE KAFKA (Self-Managed on EC2) │
│ • KRaft Mode (No Zookeeper) │
│ • Topics: cdc.users, cdc.products, cdc.orders │
│ • Always Running Event Backbone │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ KAFKA STREAMS (Optional) │
│ • Real-time routing/filtering/enrichment │
│ • Writes to Bronze topics │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ AWS GLUE SPARK JOBS │
│ ┌─────────────────────────────────────────────┐ │
│ │ BRONZE LAYER (Raw CDC Events) │ │
│ │ • Full payload with before/after states │ │
│ │ • Schema: cdc_demo_dev_bronze_{table} │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ SILVER LAYER (Cleaned & Standardized) │ │
│ │ • Deduplicated records │ │
│ │ • Data quality flags │ │
│ │ • Schema: cdc_demo_dev_silver_{table} │ │
│ └─────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────┐ │
│ │ GOLD LAYER (Analytics-Ready) │ │
│ │ • User analytics (segments, CLV) │ │
│ │ • Product analytics (revenue, popularity) │ │
│ │ • Sales trends and patterns │ │
│ │ • Schema: cdc_demo_dev_gold_* │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ APACHE ICEBERG TABLES (on S3) │
│ • ACID Transactions │
│ • Time Travel │
│ • Schema Evolution │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ AWS GLUE DATA CATALOG │
│ (Table Metadata) │
└─────────────────────────────────┬───────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────────┐
│ AMAZON ATHENA │
│ • Query Gold Tables │
│ • Analytics / Dashboards │
└─────────────────────────────────────────────────────────────────────────┘

Optional Orchestration:
┌─────────────────────────────────────────────────────────────────────────┐
│ APACHE AIRFLOW (Docker on EC2) │
│ • Schedule Glue Jobs │
│ • Monitor Failures │
└─────────────────────────────────────────────────────────────────────────┘
```
