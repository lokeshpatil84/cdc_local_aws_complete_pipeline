#!/bin/bash

# Monitoring Dashboard for CDC Pipeline
# Real-time monitoring of all AWS resources

AWS_REGION=${1:-ap-south-1}
PROJECT_NAME="cdc-pipeline"
ENVIRONMENT="dev"

clear
echo "╔════════════════════════════════════════════════════════════╗"
echo "║          CDC Pipeline - Real-time Monitoring               ║"
echo "║                                                            ║"
echo "║  Project: $PROJECT_NAME                            ║"
echo "║  Environment: $ENVIRONMENT                               ║"
echo "║  Region: $AWS_REGION                                   ║"
echo "║  Time: $(date '+%Y-%m-%d %H:%M:%S')                          ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

while true; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " [ $(date '+%H:%M:%S') ] Resource Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # S3 Buckets
    echo ""
    echo "📦 S3 Data Lake:"
    aws s3 ls s3://${PROJECT_NAME}-${ENVIRONMENT}-data-lake/ --region ${AWS_REGION} 2>/dev/null | head -5 || echo "   Unable to access bucket"
    
    # RDS Status
    echo ""
    echo "🗄️ RDS PostgreSQL:"
    RDS_STATUS=$(aws rds describe-db-instances --db-instance-identifier ${PROJECT_NAME}-${ENVIRONMENT}-postgres --region ${AWS_REGION} --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "Unknown")
    echo "   Status: $RDS_STATUS"
    
    RDS_CPU=$(aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name CPUUtilization --start-time "$(date -u -v-5M)" --end-time "$(date -u)" --period 300 --statistics Average --dimensions "Name=DBInstanceIdentifier,Value=${PROJECT_NAME}-${ENVIRONMENT}-postgres" --region ${AWS_REGION} --query 'Datapoints[0].Average' --output text 2>/dev/null || echo "N/A")
    echo "   CPU Usage: ${RDS_CPU:-N/A}%"
    
    # EC2 Instances
    echo ""
    echo "💻 EC2 Instances:"
    aws ec2 describe-instances --filters "Name=tag:Project,Values=${PROJECT_NAME}" --region ${AWS_REGION} --query 'Reservations[].Instances[].{Name:Tags[?Key==`Name`].Value | [0], State:State.Name, IP:PublicIpAddress}' --output table 2>/dev/null || echo "   Unable to list instances"
    
    # ECS Services
    echo ""
    echo "🐳 ECS Services:"
    CLUSTERS=$(aws ecs list-clusters --region ${AWS_REGION} --query "clusterArns[?contains(@, \`${PROJECT_NAME}\`)]" --output text 2>/dev/null || echo "")
    
    if [ -n "$CLUSTERS" ]; then
        for CLUSTER in $CLUSTERS; do
            CLUSTER_NAME=$(echo $CLUSTER | rev | cut -d'/' -f1 | rev)
            echo "   Cluster: $CLUSTER_NAME"
            aws ecs list-services --cluster $CLUSTER --region ${AWS_REGION} --query 'serviceArns' --output text 2>/dev/null | tr '\t' '\n' | while read SERVICE; do
                SERVICE_NAME=$(echo $SERVICE | rev | cut -d'/' -f1 | rev)
                RUNNING=$(aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region ${AWS_REGION} --query 'services[0].runningCount' --output text 2>/dev/null || echo "0")
                DESIRED=$(aws ecs describe-services --cluster $CLUSTER --services $SERVICE --region ${AWS_REGION} --query 'services[0].desiredCount' --output text 2>/dev/null || echo "0")
                echo "     - $SERVICE_NAME: $RUNNING/$DESIRED"
            done
        done
    else
        echo "   No ECS clusters found"
    fi
    
    # Glue Jobs
    echo ""
    echo "📊 Glue Jobs:"
    aws glue get-jobs --query "Jobs[?contains(Name, \`${PROJECT_NAME}\`)]" --region ${AWS_REGION} --output table 2>/dev/null | head -20 || echo "   No jobs found"
    
    # Kafka Topics
    echo ""
    echo "📨 Kafka Topics:"
    KAFKA_IP=$(aws ec2 describe-instances --filters 'Name=tag:Name,Values=*kafka*' 'Name=instance-state-name,Values=running' --region ${AWS_REGION} --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null || echo "")
    
    if [ -n "$KAFKA_IP" ]; then
        # Try to list Kafka topics (this may require SSH access)
        echo "   Kafka IP: $KAFKA_IP"
        echo "   Port 9092: $(nc -zv -w2 $KAFKA_IP 9092 2>&1 | grep -q open && echo "Open" || echo "Closed")"
    else
        echo "   Kafka instance not found"
    fi
    
    # Cost Estimation
    echo ""
    echo "💰 Estimated Monthly Cost:"
    BILLING_DATA=$(aws ce get-cost-and-usage --time-period Start=$(date -d "$(date +%Y-%m-01)" +%Y-%m-%d),End=$(date -d "+1 month" +%Y-%m-%d) --granularity MONTHLY --metrics "BlendedCost" --group-by Type=DIMENSION,Key=SERVICE --region ${AWS_REGION} 2>/dev/null || echo "")
    
    if [ -n "$BILLING_DATA" ]; then
        echo "$BILLING_DATA" | grep -A5 '"Key": "AWS Services"' | head -10 || echo "   Unable to retrieve billing data"
    else
        echo "   Billing data not available"
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo " Press [Ctrl+C] to exit | Refreshing in 30 seconds..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    sleep 30
    clear
done

