
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CDC PIPELINE - SELF-MANAGED ARCHITECTURE                  │
│                         (Kafka on EC2 - KRaft Mode)                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  POSTGRESQL │────▶│   DEBEZIUM  │────▶│    KAFKA    │────▶│   KAFKA     │
│    (RDS)    │     │   CONNECT   │     │   (KRaft)   │     │   STREAMS   │
│ wal_level=  │     │  (ECS/EC2)  │     │  (EC2)      │     │  (Optional) │
│  logical    │     │             │     │  No ZK      │     │             │
└─────────────┘     └─────────────┘     └──────┬──────┘     └──────┬──────┘
                                                │                   │
                                                │                   ▼
                                                │            ┌─────────────┐
                                                │            │   BRONZE    │
                                                │            │   TOPICS    │
                                                │            └──────┬──────┘
                                                │                   │
                                                └───────────────────┘
                                                                  │
                                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AWS GLUE SPARK JOBS                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  BRONZE LAYER   │───▶│  SILVER LAYER   │───▶│   GOLD LAYER    │        │
│  │  (Raw Events)   │    │ (Deduplicated)  │    │  (Analytics)    │        │
│  │  S3 + Iceberg   │    │  S3 + Iceberg   │    │  S3 + Iceberg   │        │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUERY LAYER (ATHENA / SPARK SQL)                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION (AIRFLOW on EC2)                            │
│     • Schedule: Kafka health checks, Glue Job triggers, Monitoring           │
│     • No dependency on AWS managed services for core pipeline                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Differences: MSK vs Self-Managed Kafka

| Aspect | MSK (Managed) | Self-Managed (Your Setup) |
|--------|---------------|---------------------------|
| **Infrastructure** | AWS Managed | EC2 instances managed by you |
| **Zookeeper** | Managed ZK or KRaft | KRaft Mode (No ZK needed) |
| **Cost** | Higher per-hour cost | EC2 cost only (cheaper) |
| **Control** | Limited configuration | Full control over configs |
| **Maintenance** | AWS handles patching | You manage updates, monitoring |
| **Scaling** | Auto-scaling available | Manual or scripted scaling |
| **VPC** | VPC endpoints | Self-configured VPC/security groups |
| **Backup** | Automated | Manual EBS snapshots |

---

## Detailed Component Breakdown

### 1. PostgreSQL (RDS or EC2)

**Configuration (Logical Replication Enabled):**

```sql
-- postgresql.conf settings
wal_level = logical              # Enable logical decoding
max_replication_slots = 10       # Slots for Debezium connectors
max_wal_senders = 10             # Concurrent replication connections
wal_keep_size = 1GB              # WAL retention (prevent slot invalidation)

-- Database setup
CREATE DATABASE cdc_demo;

-- Tables with primary keys (required for CDC)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,       -- MUST have PK for Debezium
    name VARCHAR(100),
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Publication for CDC
CREATE PUBLICATION dbz_publication FOR TABLE users, products, orders;
```

**Why Logical Replication?**
- Physical replication pura database copy karti hai
- Logical replication sirf specific tables ke changes capture karti hai
- Debezium WAL (Write-Ahead Log) ko parse karta hai logical decoding se

---

### 2. Debezium Connect (ECS Fargate or EC2)

**Deployment Options:**

**Option A: ECS Fargate (Serverless)**
```json
{
  "family": "debezium-connect",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "containerDefinitions": [{
    "name": "debezium",
    "image": "debezium/connect:2.5",
    "environment": [
      {"name": "BOOTSTRAP_SERVERS", "value": "kafka1:9092,kafka2:9092,kafka3:9092"},
      {"name": "GROUP_ID", "value": "debezium-cluster"},
      {"name": "CONFIG_STORAGE_TOPIC", "value": "debezium_configs"},
      {"name": "OFFSET_STORAGE_TOPIC", "value": "debezium_offsets"},
      {"name": "STATUS_STORAGE_TOPIC", "value": "debezium_status"}
    ],
    "portMappings": [{"containerPort": 8083}]
  }]
}
```

**Option B: EC2 (More Control)**
```bash
# User Data Script for EC2
#!/bin/bash
yum update -y
yum install -y java-11-amazon-corretto docker
service docker start

docker run -d --name debezium \
  -p 8083:8083 \
  -e BOOTSTRAP_SERVERS=kafka1.internal:9092,kafka2.internal:9092 \
  -e GROUP_ID=debezium-connect-cluster \
  -e CONFIG_STORAGE_TOPIC=debezium_configs \
  -e OFFSET_STORAGE_TOPIC=debezium_offsets \
  -e STATUS_STORAGE_TOPIC=debezium_status \
  -e KEY_CONVERTER=org.apache.kafka.connect.json.JsonConverter \
  -e VALUE_CONVERTER=org.apache.kafka.connect.json.JsonConverter \
  debezium/connect:2.5
```

**Connector Registration:**
```bash
curl -X POST http://debezium-host:8083/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "name": "postgres-connector",
    "config": {
      "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
      "database.hostname": "postgres.rds.amazonaws.com",
      "database.port": "5432",
      "database.user": "debezium",
      "database.password": "${DB_PASSWORD}",
      "database.dbname": "cdc_demo",
      "database.server.name": "cdc-server",
      "table.include.list": "public.users,public.products,public.orders",
      "plugin.name": "pgoutput",
      "publication.name": "dbz_publication",
      "slot.name": "debezium_slot",
      "transforms": "unwrap",
      "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
      "transforms.unwrap.add.fields": "op,ts_ms,source",
      "transforms.unwrap.delete.handling.mode": "rewrite",
      "heartbeat.interval.ms": "10000"
    }
  }'
```

---

### 3. Apache Kafka (Self-Managed on EC2 - KRaft Mode)

**KRaft Mode Kya Hai?**
- **Kafka Raft (KRaft)**: Zookeeper ki jagah Kafka khud hi metadata manage karta hai
- **Benefits**: 
  - One less component to manage (No ZK cluster)
  - Faster startup and recovery
  - Better scalability
  - Simpler deployment

**Architecture:**
```
┌─────────────────────────────────────────┐
│           KRaft Controller Quorum        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │Controller│  │Controller│  │Controller│ │
│  │  Node 1 │  │  Node 2 │  │  Node 3 │ │
│  │ (Leader)│  │(Follower)│  │(Follower)│ │
│  └────┬────┘  └────┬────┘  └────┬────┘ │
│       └─────────────┴─────────────┘     │
│              Metadata Quorum            │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│            Kafka Broker Nodes           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
│  │ Broker 1│  │ Broker 2│  │ Broker 3│ │
│  │(Follower)│  │(Follower)│  │(Follower)│ │
│  │         │  │         │  │         │ │
│  │ Topics: │  │ Topics: │  │ Topics: │ │
│  │cdc.users│  │cdc.users│  │cdc.users│ │
│  │cdc.prod │  │cdc.prod │  │cdc.prod │ │
│  │cdc.order│  │cdc.order│  │cdc.order│ │
│  └─────────┘  └─────────┘  └─────────┘ │
└─────────────────────────────────────────┘
```

**EC2 Instance Setup (3 nodes):**

```bash
# server.properties for Node 1 (Controller + Broker)
node.id=1
process.roles=broker,controller
listeners=PLAINTEXT://:9092,CONTROLLER://:9093
advertised.listeners=PLAINTEXT://kafka1.internal:9092
controller.quorum.voters=1@kafka1.internal:9093,2@kafka2.internal:9093,3@kafka3.internal:9093
log.dirs=/var/lib/kafka/data
num.partitions=3
default.replication.factor=3
min.insync.replicas=2
offsets.topic.replication.factor=3
transaction.state.log.replication.factor=3
transaction.state.log.min.isr=2
```

**Topic Creation:**
```bash
# Create topics with replication
kafka-topics.sh --bootstrap-server kafka1:9092 \
  --create --topic cdc.users \
  --partitions 6 --replication-factor 3

kafka-topics.sh --bootstrap-server kafka1:9092 \
  --create --topic cdc.products \
  --partitions 6 --replication-factor 3

kafka-topics.sh --bootstrap-server kafka1:9092 \
  --create --topic cdc.orders \
  --partitions 6 --replication-factor 3

# Internal topics for Debezium
kafka-topics.sh --bootstrap-server kafka1:9092 \
  --create --topic debezium_configs \
  --partitions 1 --replication-factor 3

kafka-topics.sh --bootstrap-server kafka1:9092 \
  --create --topic debezium_offsets \
  --partitions 25 --replication-factor 3
```

**Monitoring Commands:**
```bash
# Check cluster health
kafka-broker-api-versions.sh --bootstrap-server kafka1:9092

# List topics
kafka-topics.sh --bootstrap-server kafka1:9092 --list

# Consumer groups
kafka-consumer-groups.sh --bootstrap-server kafka1:9092 --list

# Check lag
kafka-consumer-groups.sh --bootstrap-server kafka1:9092 \
  --group glue-cdc-consumer --describe
```

---

### 4. Kafka Streams (Optional Layer)

**Kyun Use Karein?**
- Real-time filtering (sirf specific events process karna)
- Enrichment (external API se data join karna)
- Aggregation (windowed operations)
- Routing (alag-alag topics mein bhejna)

**Example: Filter + Enrich**
```java
// Kafka Streams application
StreamsBuilder builder = new StreamsBuilder();

KStream<String, JsonNode> cdcStream = builder.stream("cdc.users");

// Filter: Sirf INSERT operations
KStream<String, JsonNode> insertsOnly = cdcStream
    .filter((key, value) -> value.get("op").asText().equals("c"));

// Enrich: User data ke saath department info add karo
KStream<String, JsonNode> enriched = insertsOnly
    .leftJoin(
        departmentTable,
        (user, dept) -> {
            ObjectNode enriched = user.deepCopy();
            enriched.set("department", dept);
            return enriched;
        }
    );

// Write to Bronze topic
enriched.to("bronze.users");

// Build and start
KafkaStreams streams = new KafkaStreams(builder.build(), props);
streams.start();
```

**Agar Skip Karein Toh:**
- Direct Debezium → Kafka → Glue (simpler)
- Processing sirf Glue mein hoga (batch ya micro-batch)

---

### 5. AWS Glue Spark Jobs (Medallion Architecture)

**Job 1: Bronze Processor**
```python
# cdc_processor.py - Bronze Layer
from pyspark.context import SparkContext
from awsglue.context import GlueContext

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

# Read from Kafka (Self-managed)
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka1.internal:9092,kafka2.internal:9092,kafka3.internal:9092") \
    .option("subscribe", "cdc.users,cdc.products,cdc.orders") \
    .option("startingOffsets", "latest") \
    .option("kafka.security.protocol", "PLAINTEXT") \  # Or SASL_SSL if secured
    .load()

# Parse JSON payload
parsed = df.select(
    col("topic"),
    from_json(col("value").cast("string"), schema).alias("data")
)

# Write to Iceberg Bronze table
parsed.writeStream \
    .format("iceberg") \
    .outputMode("append") \
    .option("checkpointLocation", "s3://bucket/checkpoints/bronze") \
    .start("glue_catalog.cdc_db.bronze_users")
```

**Job 2: Silver Processor (Merge)**
```python
# Silver layer with MERGE logic
spark.sql("""
    MERGE INTO glue_catalog.cdc_db.silver_users AS target
    USING (
        SELECT 
            id, name, email, op, ts_ms,
            ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts_ms DESC) as rn
        FROM glue_catalog.cdc_db.bronze_users
        WHERE processed_date = current_date()
    ) AS source
    ON target.id = source.id
    WHEN MATCHED AND source.rn = 1 AND source.op != 'd' THEN
        UPDATE SET *
    WHEN MATCHED AND source.op = 'd' THEN
        DELETE
    WHEN NOT MATCHED AND source.rn = 1 THEN
        INSERT *
""")
```

**Job 3: Gold Processor**
```python
# Aggregation for analytics
spark.sql("""
    CREATE OR REPLACE TABLE glue_catalog.cdc_db.gold_user_stats AS
    SELECT 
        u.id,
        u.name,
        COUNT(o.id) as total_orders,
        SUM(o.total_amount) as lifetime_value,
        CASE 
            WHEN SUM(o.total_amount) > 10000 THEN 'VIP'
            WHEN SUM(o.total_amount) > 1000 THEN 'Gold'
            ELSE 'Silver'
        END as segment
    FROM glue_catalog.cdc_db.silver_users u
    LEFT JOIN glue_catalog.cdc_db.silver_orders o ON u.id = o.user_id
    WHERE u.is_active = true
    GROUP BY u.id, u.name
""")
```

---

### 6. Apache Iceberg on S3

**Table Structure:**
```
s3://cdc-data-bucket/
├── iceberg/
│   ├── cdc_db/
│   │   ├── bronze_users/
│   │   │   ├── data/
│   │   │   │   ├── 00001.parquet
│   │   │   │   └── 00002.parquet
│   │   │   └── metadata/
│   │   │       ├── 00001.metadata.json
│   │   │       └── 00001-snap-xxx.avro
│   │   ├── silver_users/
│   │   └── gold_user_stats/
│   └── raw_archive/          # Optional: Raw JSON backup
│       └── year=2024/month=01/day=15/
```

**Maintenance Procedures:**
```sql
-- Optimize (compaction) - Run weekly
OPTIMIZE glue_catalog.cdc_db.bronze_users REWRITE DATA USING BIN_PACK;

-- Expire old snapshots - Retain 7 days
EXPIRE SNAPSHOTS glue_catalog.cdc_db.bronze_users 
    RETAIN 7 DAYS;

-- Remove orphan files
REMOVE ORPHAN FILES glue_catalog.cdc_db.bronze_users;
```

---

### 7. Orchestration (Airflow on EC2)

**Why Airflow on EC2 (not MWAA)?**
- **Cost**: MWAA expensive hai large deployments ke liye
- **Control**: Custom plugins, Python libraries install kar sakte hain
- **Network**: Self-managed Kafka ke saath easy integration (same VPC)
- **Flexibility**: Resource customization

**DAG Structure:**
```python
from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.bash import BashOperator
from datetime import datetime

default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'email_on_failure': True,
    'retries': 2
}

with DAG(
    'self_managed_cdc_pipeline',
    default_args=default_args,
    schedule_interval='@hourly',
    start_date=datetime(2024, 1, 1),
    catchup=False
) as dag:

    # Health check for self-managed Kafka
    kafka_health = BashOperator(
        task_id='check_kafka_health',
        bash_command='''
            kafka-broker-api-versions.sh \
            --bootstrap-server kafka1.internal:9092 \
            --command-config /opt/airflow/config/client.properties
        '''
    )

    # Check Debezium connector status
    debezium_health = BashOperator(
        task_id='check_debezium',
        bash_command='''
            curl -s http://debezium.internal:8083/connectors/postgres-connector/status | \
            grep -q "RUNNING" && echo "OK" || exit 1
        '''
    )

    # Trigger Glue Jobs
    bronze_job = GlueJobOperator(
        task_id='bronze_processing',
        job_name='cdc-bronze-processor',
        script_location='s3://bucket/scripts/bronze.py'
    )

    silver_job = GlueJobOperator(
        task_id='silver_processing',
        job_name='cdc-silver-processor'
    )

    gold_job = GlueJobOperator(
        task_id='gold_processing',
        job_name='cdc-gold-processor'
    )

    # Dependencies
    kafka_health >> debezium_health >> bronze_job >> silver_job >> gold_job
```

---

## Infrastructure as Code (Terraform)

### Kafka Cluster Module

```hcl
# kafka-cluster.tf
resource "aws_instance" "kafka_broker" {
  count         = 3
  ami           = "ami-0c55b159cbfafe1f0"  # Amazon Linux 2023
  instance_type = "m5.xlarge"              # 4 vCPU, 16GB RAM
  subnet_id     = aws_subnet.private[count.index % 3].id
  
  vpc_security_group_ids = [aws_security_group.kafka.id]
  
  root_block_device {
    volume_size = 500  # GB for Kafka logs
    volume_type = "gp3"
    iops        = 3000
  }

  user_data = templatefile("${path.module}/kafka-setup.sh", {
    node_id = count.index + 1
    controller_quorum = "1@kafka1:9093,2@kafka2:9093,3@kafka3:9093"
  })

  tags = {
    Name = "kafka-broker-${count.index + 1}"
    Role = count.index < 3 ? "controller,broker" : "broker"
  }
}

# Security Group
resource "aws_security_group" "kafka" {
  name_prefix = "kafka-cluster-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]  # Internal only
  }

  ingress {
    from_port   = 9093
    to_port     = 9093
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]  # Controller quorum
  }
}
```

### Debezium ECS Service

```hcl
# debezium.tf
resource "aws_ecs_cluster" "debezium" {
  name = "debezium-connect-cluster"
}

resource "aws_ecs_task_definition" "debezium" {
  family                   = "debezium-connect"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "2048"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.debezium_task.arn

  container_definitions = jsonencode([{
    name  = "debezium"
    image = "debezium/connect:2.5"
    
    environment = [
      { name = "BOOTSTRAP_SERVERS", value = join(",", aws_instance.kafka_broker[*].private_ip) },
      { name = "GROUP_ID", value = "debezium-cluster" },
      { name = "CONFIG_STORAGE_TOPIC", value = "debezium_configs" },
      { name = "OFFSET_STORAGE_TOPIC", value = "debezium_offsets" },
      { name = "STATUS_STORAGE_TOPIC", value = "debezium_status" },
      { name = "KEY_CONVERTER", value = "org.apache.kafka.connect.json.JsonConverter" },
      { name = "VALUE_CONVERTER", value = "org.apache.kafka.connect.json.JsonConverter" },
      { name = "CONNECT_TOPIC_CREATION_ENABLE", value = "true" }
    ]
    
    portMappings = [{ containerPort = 8083 }]
    
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.debezium.name
        awslogs-region        = "ap-south-1"
        awslogs-stream-prefix = "debezium"
      }
    }
  }])
}

resource "aws_ecs_service" "debezium" {
  name            = "debezium-connect"
  cluster         = aws_ecs_cluster.debezium.id
  task_definition = aws_ecs_task_definition.debezium.arn
  desired_count   = 2  # HA with 2 tasks
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.debezium.id]
    assign_public_ip = false
  }
}
```

---

## Cost Comparison: MSK vs Self-Managed

**Monthly Cost Estimate (3-node cluster, 6 TB data):**

| Component | MSK | Self-Managed (EC2) |
|-----------|-----|-------------------|
| **Kafka Brokers** | $1,200 (3× kafka.m5.large) | $420 (3× m5.xlarge on-demand) |
| **Zookeeper** | Included | $0 (KRaft mode) |
| **Storage** | $600 (6 TB × $0.10/GB) | $480 (6 TB gp3 EBS) |
| **Data Transfer** | $200 | $100 |
| **Management** | $0 (AWS managed) | $200 (Your time/monitoring) |
| **Total** | **~$2,000/month** | **~$1,200/month** |

**Savings**: ~40% with self-managed (but operational overhead zyada)

---

## Operational Runbook

### Daily Checks
```bash
# 1. Kafka cluster health
kafka-broker-api-versions.sh --bootstrap-server kafka1:9092

# 2. Consumer lag check
kafka-consumer-groups.sh --bootstrap-server kafka1:9092 --describe --all-groups

# 3. Debezium connector status
curl http://debezium:8083/connectors/postgres-connector/status

# 4. Disk space on Kafka nodes
for host in kafka1 kafka2 kafka3; do
  ssh $host "df -h /var/lib/kafka/data"
done
```

### Failure Scenarios

**Scenario 1: Kafka Broker Down**
```bash
# Auto-recovery (Replication factor 3)
# 1. Failed broker ka data replicate hoga remaining 2 se
# 2. New broker launch karo ASG se ya manually
# 3. Join cluster with same broker.id

# Manual recovery
systemctl restart kafka  # If process crashed
# OR
# Replace EC2 instance (same private IP wapas assign karo)
```

**Scenario 2: Debezium Connector Failed**
```bash
# Check logs
curl http://debezium:8083/connectors/postgres-connector/status

# Restart
curl -X POST http://debezium:8083/connectors/postgres-connector/restart

# If persistent failure:
# 1. Check PostgreSQL replication slot: SELECT * FROM pg_replication_slots;
# 2. Check WAL retention: pg_current_wal_lsn() vs confirmed_flush_lsn
# 3. Recreate connector if slot lost (full snapshot hoga)
```

**Scenario 3: Replication Slot Lost (Critical)**
```sql
-- If Debezium complains about "replication slot not found"
-- Ya WAL segment already removed

-- Check slot
SELECT slot_name, active, restart_lsn, confirmed_flush_lsn 
FROM pg_replication_slots WHERE slot_name = 'debezium_slot';

-- Recreate (WARNING: Full snapshot hoga - downtime possible)
SELECT pg_drop_replication_slot('debezium_slot');
-- Recreate connector via API (Debezium new slot banayega)
```

---

## Summary: Self-Managed vs Managed Services

| Your Choice | Pros | Cons |
|-------------|------|------|
| **Self-Managed Kafka** | 40% cost savings, full control, KRaft simplicity | Operational overhead, manual patching, scaling complexity |
| **ECS Fargate Debezium** | No server management, auto-scaling, integrated monitoring | Cold start latency, Fargate limits |
| **Airflow on EC2** | Cost effective, custom plugins, direct VPC access | Manual upgrades, backup responsibility |
| **Glue + Iceberg** | Serverless processing, ACID guarantees, time travel | Cold start time, Spark complexity |

**Aapka architecture production-ready hai with proper:**
- High Availability (3-node Kafka, 2-task Debezium)
- Durability (Replication factor 3, EBS backups)
- Scalability (Auto Scaling Groups for Kafka)
- Monitoring (CloudWatch, custom dashboards)

Koi specific component aur detail mein chahiye toh batayein!