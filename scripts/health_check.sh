#!/bin/bash

# Health Check Script for CDC Pipeline
# Usage: ./health_check.sh <aws_region>

set -e

AWS_REGION=${1:-ap-south-1}
PROJECT_NAME="cdc-pipeline"
ENVIRONMENT="dev"

echo "=========================================="
echo "CDC Pipeline Health Check"
echo "Region: $AWS_REGION"
echo "Time: $(date)"
echo "=========================================="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter for passed/failed checks
PASSED=0
FAILED=0

check_service() {
    local service_name=$1
    local check_command=$2
    local description=$3
    
    echo "Checking $service_name..."
    if eval "$check_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $service_name: HEALTHY${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ $service_name: UNHEALTHY${NC} - $description"
        ((FAILED++))
    fi
}

echo "1. AWS Resource Checks"
echo "-----------------------------------"

# Check S3 Bucket
check_service "S3 Data Lake Bucket" \
    "aws s3 ls s3://${PROJECT_NAME}-${ENVIRONMENT}-data-lake/ --region ${AWS_REGION}" \
    "Bucket may not exist or no access"

# Check RDS Instance
check_service "RDS PostgreSQL" \
    "aws rds describe-db-instances --db-instance-identifier ${PROJECT_NAME}-${ENVIRONMENT}-postgres --region ${AWS_REGION} --query 'DBInstances[0].DBInstanceStatus' --output text | grep -q available" \
    "RDS instance not available"

# Check EC2 Kafka Instance
check_service "Kafka EC2 Instance" \
    "aws ec2 describe-instances --filters 'Name=tag:Name,Values=*kafka*' 'Name=instance-state-name,Values=running' --region ${AWS_REGION} --query 'Reservations[0].Instances[0].InstanceId'" \
    "Kafka instance not running"

# Check ECS Services
check_service "Debezium Connect ECS" \
    "aws ecs describe-services --cluster ${PROJECT_NAME}-${ENVIRONMENT} --services ${PROJECT_NAME}-${ENVIRONMENT}-debezium --region ${AWS_REGION} --query 'services[0].status' --output text | grep -q RUNNING" \
    "Debezium service not running"

# Check Glue Jobs
check_service "Glue Jobs" \
    "aws glue get-jobs --query 'Jobs[?contains(Name, \`${PROJECT_NAME}\`)]' --region ${AWS_REGION} | grep -q ." \
    "No Glue jobs found"

# Check SNS Topic
check_service "SNS Alerts Topic" \
    "aws sns get-topic-attributes --topic-arn arn:aws:sns:${AWS_REGION}:$(aws sts get-caller-identity --query Account --output text):${PROJECT_NAME}-${ENVIRONMENT}-alerts --region ${AWS_REGION}" \
    "SNS topic not accessible"

echo ""
echo "2. Kafka Connectivity Check"
echo "-----------------------------------"

# Get Kafka public IP
KAFKA_IP=$(aws ec2 describe-instances --filters 'Name=tag:Name,Values=*kafka*' 'Name=instance-state-name,Values=running' --region ${AWS_REGION} --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null || echo "")

if [ -n "$KAFKA_IP" ]; then
    echo "Kafka IP: $KAFKA_IP"
    if nc -zv $KAFKA_IP 9092 2>/dev/null; then
        echo -e "${GREEN}✓ Kafka port 9092: OPEN${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Kafka port 9092: CLOSED${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠ Kafka IP not found - skipping port check${NC}"
fi

echo ""
echo "3. Service Endpoints"
echo "-----------------------------------"

# Get Airflow URL
AIRFLOW_URL=$(aws cloudformation describe-stacks --stack-name ${PROJECT_NAME}-${ENVIRONMENT}-airflow --region ${AWS_REGION} --query 'Stacks[0].Outputs[?OutputKey==`AlbDnsName`].OutputValue' --output text 2>/dev/null || echo "")
if [ -n "$AIRFLOW_URL" ]; then
    echo "Airflow: http://${AIRFLOW_URL}"
else
    echo -e "${YELLOW}⚠ Airflow URL not found${NC}"
fi

# Get Debezium URL
DEBEZIUM_URL=$(aws cloudformation describe-stacks --stack-name ${PROJECT_NAME}-${ENVIRONMENT}-ecs --region ${AWS_REGION} --query 'Stacks[0].Outputs[?OutputKey==`AlbDnsName`].OutputValue' --output text 2>/dev/null || echo "")
if [ -n "$DEBEZIUM_URL" ]; then
    echo "Debezium Connect: http://${DEBEZIUM_URL}:8083"
    
    # Check if Debezium API is responding
    if curl -s -o /dev/null -w "%{http_code}" "http://${DEBEZIUM_URL}:8083/" | grep -q "200\|404"; then
        echo -e "${GREEN}✓ Debezium API: RESPONDING${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Debezium API: NOT RESPONDING${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⚠ Debezium URL not found${NC}"
fi

echo ""
echo "=========================================="
echo "Health Check Summary"
echo "=========================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All services are healthy!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some services need attention${NC}"
    exit 1
fi

