#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

check_prerequisites() {
    echo "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        echo "Docker is not installed."
        exit 1
    fi
    echo "Docker: $(docker --version)"

    if ! command -v docker-compose &> /dev/null; then
        echo "Docker Compose is not installed."
        exit 1
    fi
    echo "Docker Compose: $(docker-compose --version)"

    if ! docker info &> /dev/null; then
        echo "Docker is not running."
        exit 1
    fi
}

start_services() {
    echo "Starting CDC Pipeline services..."
    docker-compose up -d --build

    echo "Waiting for PostgreSQL..."
    until docker exec cdc-postgres pg_isready -U postgres -d cdc_demo; do
        sleep 2
    done
    echo "PostgreSQL ready"

    echo "Waiting for Kafka..."
    until docker exec cdc-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 &>/dev/null; do
        sleep 5
    done
    echo "Kafka ready"

    echo "Waiting for Debezium..."
    until curl -s http://localhost:8083/connectors &>/dev/null; do
        sleep 5
    done
    echo "Debezium ready"

    echo "All services are running!"
}

check_status() {
    echo "Service Status:"
    docker-compose ps
}

view_logs() {
    SERVICE="${1:-all}"
    if [ "$SERVICE" = "all" ]; then
        docker-compose logs -f
    else
        docker-compose logs -f "$SERVICE"
    fi
}

stop_services() {
    echo "Stopping CDC Pipeline services..."
    docker-compose down -v
    echo "Services stopped"
}

clean_services() {
    echo "Cleaning up CDC Pipeline environment..."
    docker-compose down -v --remove-orphans
    echo "Environment cleaned (volumes removed)"
}

setup_connectors() {
    echo "Setting up Debezium connectors..."

    CONNECTORS=$(curl -s "http://localhost:8083/connectors" 2>/dev/null || echo "[]")
    echo "Existing connectors: $CONNECTORS"

    if echo "$CONNECTORS" | grep -q '"cdc-connector"'; then
        echo "Connector 'cdc-connector' already exists."
        curl -s "http://localhost:8083/connectors/cdc-connector/status"
        echo ""
        return 0
    fi

    curl -s -X DELETE "http://localhost:8083/connectors/cdc-connector" 2>/dev/null || true
    sleep 2

    echo "Creating CDC connector..."
    RESPONSE=$(curl -X PUT "http://localhost:8083/connectors/cdc-connector/config" \
        -H "Content-Type: application/json" \
        -d '{
            "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
            "database.hostname": "postgres",
            "database.port": "5432",
            "database.user": "postgres",
            "database.password": "postgres",
            "database.dbname": "cdc_demo",
            "database.server.name": "cdc-server",
            "topic.prefix": "cdc",
            "table.include.list": "public.users,public.products,public.orders",
            "plugin.name": "pgoutput",
            "publication.autocreate.mode": "filtered",
            "slot.name": "debezium_slot",
            "key.converter": "org.apache.kafka.connect.json.JsonConverter",
            "value.converter": "org.apache.kafka.connect.json.JsonConverter",
            "key.converter.schemas.enable": "false",
            "value.converter.schemas.enable": "false",
            "transforms": "unwrap",
            "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
            "transforms.unwrap.add.fields": "op,ts_ms,source",
            "heartbeat.interval.ms": "5000"
        }')

    echo "$RESPONSE"
    sleep 3

    STATUS=$(curl -s "http://localhost:8083/connectors/cdc-connector/status")

    if echo "$STATUS" | grep -q '"state":"RUNNING"'; then
        echo "Connector is RUNNING!"
        echo "Kafka Topics:"
        docker exec cdc-kafka kafka-topics --list --bootstrap-server localhost:9092 2>/dev/null | grep -E "^(cdc|__heartbeat)" || echo "  (topics may take a moment)"
    else
        echo "Connector status:"
        echo "$STATUS"
    fi
}

list_topics() {
    echo "Kafka Topics:"
    docker exec cdc-kafka kafka-topics --list --bootstrap-server localhost:9092
}

test_cdc() {
    echo "Testing CDC with sample operations..."

    TEST_EMAIL="test$(date +%s)@example.com"

    docker exec cdc-postgres psql -U postgres -d cdc_demo -c \
        "INSERT INTO users (name, email) VALUES ('Test User', '${TEST_EMAIL}');" 2>/dev/null

    docker exec cdc-postgres psql -U postgres -d cdc_demo -c \
        "UPDATE users SET name = 'Updated User' WHERE email = '${TEST_EMAIL}';" 2>/dev/null

    docker exec cdc-postgres psql -U postgres -d cdc_demo -c \
        "DELETE FROM users WHERE email = '${TEST_EMAIL}';" 2>/dev/null

    echo "CDC Operations Complete!"
}

show_help() {
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  start         Start all services"
    echo "  stop          Stop all services"
    echo "  clean         Stop and remove volumes"
    echo "  status        Show service status"
    echo "  logs [svc]    View logs"
    echo "  connectors    Setup Debezium connectors"
    echo "  topics        List Kafka topics"
    echo "  test          Run CDC test"
    echo "  restart       Restart services"
    echo "  help          Show help"
    echo ""
    echo "Services:"
    echo "  PostgreSQL:   localhost:5432"
    echo "  Kafka:        localhost:9092"
    echo "  Debezium:     localhost:8083"
}

case "${1:-start}" in
    start)
        check_prerequisites
        start_services
        check_status
        ;;
    stop)
        stop_services
        ;;
    clean)
        clean_services
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs "${2:-all}"
        ;;
    connectors)
        setup_connectors
        ;;
    topics)
        list_topics
        ;;
    test)
        test_cdc
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac

