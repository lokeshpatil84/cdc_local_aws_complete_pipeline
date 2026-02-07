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

## CI/CD Workflow

This project uses GitHub Actions for automated CI/CD:

### Workflow Files
- `.github/workflows/01-ci.yml` - Code quality checks (Python, Terraform, Docker)
- `.github/workflows/cd-main.yml` - Infrastructure deployment (Terraform)

### Deployment Modes

#### 1. Auto-trigger (Plan-Only)
Push to `dev` or `main` branch triggers:
1. CI runs (code quality checks)
2. CD auto-triggers on CI success
3. **Only generates Terraform plan** (no auto-apply)
4. Plan artifacts available for review

```bash
# Push to dev - auto plan for dev environment
git checkout dev
git push origin dev

# Push to main - auto plan for prod environment  
git checkout main
git push origin main
```

#### 2. Manual Apply
Manual workflow dispatch required to apply changes:

1. Go to **Actions** → **CD - Infrastructure and Glue Jobs**
2. Click **Run workflow**
3. Select:
   - **Environment**: `dev`, `staging`, or `prod`
   - **Action**: `deploy` (for plan+apply) or `plan-only` (just plan)
   - **Reason**: Required for production
4. Review the generated plan
5. Approve via GitHub Environment (required for `prod`)
6. Changes are applied

### Environment Mapping

| Branch  | Environment | State Bucket                           | Lock Table                          |
|---------|-------------|----------------------------------------|-------------------------------------|
| dev     | dev         | cdc-pipeline-tfstate-dev              | cdc-pipeline-terraform-lock-dev     |
| staging | staging     | cdc-pipeline-tfstate-staging          | cdc-pipeline-terraform-lock-staging |
| main    | prod        | cdc-pipeline-tfstate-prod             | cdc-pipeline-terraform-lock-prod    |

### State Isolation
Each environment has **isolated Terraform state**:
- Separate S3 bucket for state storage
- Separate DynamoDB table for state locking
- Prevents cross-environment contamination

### GitHub Secrets Required

Configure these in GitHub repository settings:

| Secret Name | Description |
|------------|-------------|
| `AWS_DEV_ACCESS_KEY_ID` | AWS credentials for dev environment |
| `AWS_DEV_SECRET_ACCESS_KEY` | AWS secret for dev |
| `AWS_STAGING_ACCESS_KEY_ID` | AWS credentials for staging |
| `AWS_STAGING_SECRET_ACCESS_KEY` | AWS secret for staging |
| `AWS_PROD_ACCESS_KEY_ID` | AWS credentials for prod |
| `AWS_PROD_SECRET_ACCESS_KEY` | AWS secret for prod |
| `SSH_PUBLIC_KEY` | SSH public key for Kafka EC2 access |

### GitHub Environments

Create these environments in GitHub settings for approval gates:

1. **dev** - Optional approval
2. **staging** - Optional approval  
3. **prod** - Required approval (protect production changes)

### Scheduled Drift Detection
Nightly at 6:00 UTC:
- Runs plan against production
- Alerts if infrastructure drift detected

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
