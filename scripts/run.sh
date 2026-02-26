#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yaml"
ENV_FILE="./secrets/.env"
PROJECT_NAME="baliblissed"

DB_NAME=""
DB_USER=""
IS_NEON=false

PID_FILE="uvicorn.pid"

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# load environment variables
# Uses set -a / source / set +a to safely handle values with spaces,
# special characters, and quoted strings.
load_env() {
    if [ -f "$ENV_FILE" ]; then
        log_info "Loading environment variables from $ENV_FILE"
        set -a
        # shellcheck source=/dev/null
        source "$ENV_FILE"
        set +a

        # Dynamically select compose file based on environment or Redis SSL setting
        if [ "$ENVIRONMENT" = "production" ] || [ "$REDIS_SSL" = "true" ]; then
            COMPOSE_FILE="docker-compose.redis-ssl.yaml"
            log_info "Using production compose file: $COMPOSE_FILE"
        else
            COMPOSE_FILE="docker-compose.yaml"
            log_info "Using development compose file: $COMPOSE_FILE"
        fi
    else
        log_error "Environment file $ENV_FILE not found"
        exit 1
    fi
}

# Detect if using Neon Postgres (cloud-hosted)
is_neon_postgres() {
    if echo "$DATABASE_URL" | grep -q "neon.tech"; then
        return 0  # true - is Neon
    else
        return 1  # false - not Neon
    fi
}

# Convert asyncpg URL to standard psql URL for CLI tools
# Transforms: postgresql+asyncpg://... -> postgresql://...
# Also converts ssl=require to sslmode=require (psql CLI syntax)
get_psql_url() {
    echo "$DATABASE_URL" | sed 's/postgresql+asyncpg/postgresql/' | sed 's/ssl=require/sslmode=require/'
}

# Extract database name from DATABASE_URL
# Handles both local and Neon connection strings with ?ssl=require
get_db_name() {
    # Extract DB name (handles ?ssl=require suffix)
    DB_NAME=$(echo "$DATABASE_URL" | sed -n 's/.*\/\([^?]*\).*/\1/p')
    # Extract username from URL
    DB_USER=$(echo "$DATABASE_URL" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    
    # Set Neon flag for use throughout script
    if is_neon_postgres; then
        IS_NEON=true
        log_info "Detected Neon Postgres (cloud)"
    else
        IS_NEON=false
        log_info "Detected local Postgres"
    fi

    if [ -z "$DB_NAME" ]; then
        DB_NAME="baliblissed"
    fi

    if [ -z "$DB_USER" ]; then
        DB_USER="postgres"
    fi
}

# Checking Postgres connection
# Handles both local Postgres and Neon Postgres (cloud)
check_postgres() {
    log_info "Checking Postgres connection..."
    if command -v psql &> /dev/null; then
        if [ "$IS_NEON" = true ]; then
            # Neon Postgres: use full connection string with SSL
            PSQL_URL=$(get_psql_url)
            if psql "$PSQL_URL" -c '\q' 2>/dev/null; then
                log_success "✅ Neon Postgres connection successful"
            else
                log_error "❌ Could not connect to Neon PostgreSQL"
                log_error "   Check your DATABASE_URL and network connection"
                log_error "   Ensure the Neon project is active and not suspended"
                exit 1
            fi
        else
            # Local Postgres: use username-based auth
            if psql -U "$DB_USER" -c '\q' 2>/dev/null; then
                log_success "✅ Local Postgres connection successful"
            else
                log_error "❌ Could not connect to local PostgreSQL"
                log_error "   Make sure PostgreSQL is running:"
                log_error "   - macOS: brew services start postgresql"
                log_error "   - Linux: sudo service postgresql start"
                exit 1
            fi
        fi
    else
        log_error "❌ psql command not found"
        log_error "   Please install PostgreSQL client"
        exit 1
    fi
    log_info ""
}

# Ask user if they want to recreate the database
# For Neon: drops all tables (database is managed by Neon)
# For Local: drops and recreates the entire database
ask_recreate_db() {
    log_info "🗄️  Database Setup"
    log_info "Current database: $DB_NAME"
    if [ "$IS_NEON" = true ]; then
        log_info "Mode: Neon Postgres (cloud-managed)"
    else
        log_info "Mode: Local Postgres"
    fi
    log_info ""
    read -p "Do you want to recreate the database? This will DELETE all existing data! (y/N): " -n 1 -r
    log_info ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ "$IS_NEON" = true ]; then
            # Neon Postgres: drop all tables (can't drop/create database directly)
            log_info "⚠️  Dropping all tables in Neon database..."
            PSQL_URL=$(get_psql_url)
            # Drop all tables in public schema
            psql "$PSQL_URL" -c "
                DO \$\$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END \$\$;
            " 2>/dev/null || log_warning "Some tables may not have been dropped"
            log_info "✅ Tables dropped"
        else
            # Local Postgres: drop and recreate database
            log_info "⚠️  Dropping existing database..."
            dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true

            log_info "📦 Creating new database..."
            createdb -U "$DB_USER" "$DB_NAME"
            log_info "✅ Database created"
        fi
        log_info ""

        log_info "🔧 Initializing database tables..."
        uv run python -m app.db.init_db
        log_info "✅ Database initialized"
    else
        log_info "🔧 Checking/updating database tables..."
        uv run python -m app.db.init_db
        log_info "✅ Database ready"
    fi
    log_info ""
}

# Check if a port is already in use by a host process (to prevent Docker conflicts)
check_port_conflict() {
    local port="${1:-5432}"
    if nc -z 127.0.0.1 "$port" > /dev/null 2>&1; then
        # Port is in use. Check if it's occupied by our own Docker project containers.
        if ! docker ps --filter "name=${PROJECT_NAME}-db" --filter "status=running" --format '{{.Names}}' | grep -q "${PROJECT_NAME}-db"; then
            log_error "❌ Port $port is already in use by another application (likely your Desktop Postgres app)."
            log_error "   Please stop the host-side Postgres service before running in Docker mode."
            log_error "   - macOS: Turn off your Postgres Desktop App or 'brew services stop postgresql'"
            log_error "   - Linux: 'sudo service postgresql stop'"
            exit 1
        fi
    fi
}

# Check if Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker and try again."
        exit 1
    else
        log_success "Docker is running"
    fi
}

# Create required directories
create_directories() {
    log_info "Creating required directories..."
    mkdir -p ./data/redis ./logs
    log_success "Directories created successfully"
}

# Start development environment
start() {
    log_info "🚀 BaliBlissed Blog API - Quick Start"
    log_info "======================================"
    log_info ""
    load_env
    get_db_name
    check_docker
    create_directories
    
    # Start basic infrastructure services
    # redis-commander is excluded in production compose for security
    local infra_services="db redis prometheus grafana jaeger otel-collector"
    if docker compose -f "$COMPOSE_FILE" config --services | grep -q "redis-commander"; then
        infra_services="$infra_services redis-commander"
    fi
    
    # Check for port conflicts before starting the DB
    if ! is_neon_postgres; then
        check_port_conflict 5432
    fi
    
    log_info "Starting infrastructure services..."
    docker compose -f "$COMPOSE_FILE" --profile otel up -d $infra_services
    
    if ! is_neon_postgres; then
        log_info "Waiting for database to be healthy..."
        until docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U "${DB_USER:-postgres}" > /dev/null 2>&1; do
            sleep 1
        done
        log_success "Database is ready!"
    fi
    
    log_info "Starting backend service using local uvicorn..."
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --workers 1 --loop uvloop --http httptools
}

# Start backend inside Docker
start_docker() {
    log_info "🚀 BaliBlissed Blog API - Docker Environment"
    log_info "========================================="
    load_env
    get_db_name
    check_docker
    create_directories
    
    # If not using Neon, we need to spin up the DB and route it correctly
    if ! is_neon_postgres; then
        # Rewrite localhost/127.0.0.1 to the Docker service name 'db'.
        # Warn and use as-is if neither is found (e.g. custom hostname).
        if echo "$DATABASE_URL" | grep -qE "(localhost|127\.0\.0\.1)"; then
            export DOCKER_DATABASE_URL=$(echo "$DATABASE_URL" | sed -E 's/(localhost|127\.0\.0\.1)/db/g')
        else
            log_warning "DATABASE_URL does not contain 'localhost' or '127.0.0.1' — using as-is for Docker"
            export DOCKER_DATABASE_URL="$DATABASE_URL"
        fi
        
        # Check for port conflicts before starting the DB
        check_port_conflict 5432
        
        log_info "Starting local Postgres container..."
        docker compose -f "$COMPOSE_FILE" up -d db
        
        log_info "Waiting for database to be healthy..."
        until docker compose -f "$COMPOSE_FILE" exec -T db pg_isready -U "${DB_USER:-postgres}" > /dev/null 2>&1; do
            sleep 1
        done
        log_success "Database is ready!"
    else
        export DOCKER_DATABASE_URL="$DATABASE_URL"
    fi

    # Run DB checks and recreation logic (just like start command)
    # check_postgres  <-- Removed: redundant and causes failure if host-side Postgres app is off
    # ask_recreate_db

    log_info "Starting all remaining services via Docker Compose..."
    docker compose -f "$COMPOSE_FILE" --profile otel up -d
    log_success "Environment is running in Docker!"
    log_info "You can view logs with: ./scripts/run.sh logs backend"
}

# Stop development environment (SAFE: preserves database volumes)
stop() {
    log_info "Stopping BaliBlissed development environment..."
    load_env
    # Stop services including those in the otel profile
    # -v is NOT used here to ensure data persistence
    docker compose -f "$COMPOSE_FILE" --profile otel down
    
    log_success "Development environment stopped successfully!"
}

# Cleanup browser state to prevent auto-launch issues
clean_browser() {
    if [ -f "./scripts/clean_browser.sh" ]; then
        ./scripts/clean_browser.sh
    fi
}

# Restart development environment (full Docker mode).
# To restart in hybrid mode (infra in Docker, backend local), use 'reset' instead.
restart() {
    log_info "Restarting development environment (Docker mode)..."
    stop
    start_docker
}

# Clean development environment (WIPES database volumes)
clean() {
    log_info "Wiping BaliBlissed development environment (deleting volumes)..."
    load_env
    docker compose -f "$COMPOSE_FILE" --profile otel down -v
    log_success "Environment wiped and volumes removed!"
}

# Reset development environment
reset() {
    log_info "Resetting development environment..."
    clean
    start
}

# Run tests
test() {
    log_info "Running tests..."
    uv run pytest
}

# Show logs
logs() {
    load_env
    local service="${1:-backend}"
    log_info "Showing logs for $service..."
    docker compose -f "$COMPOSE_FILE" logs -f "$service"
}

# Show status
status() {
    load_env
    log_info "Checking service status..."
    docker compose -f "$COMPOSE_FILE" ps
}

# Build docker images
build() {
    load_env
    local target="${1:-development}"
    log_info "Building specific Docker image for target: $target"
    
    if [ "$target" = "production" ]; then
        docker build --target production -t baliblissed:prod .
        log_success "Production image built successfully"
    else
        # For development build, we build the backend image with development stage explicitly
        docker build --target development -t baliblissed:dev .
        log_success "Development image built successfully"
    fi
}

# Print help message
help() {
    echo "Usage: ./scripts/run.sh [command] [args]"
    echo ""
    echo "Commands:"
    echo "  start         Start infrastructure in Docker, run Backend via local uvicorn (default)"
    echo "  start_docker  Start all services including Backend in Docker"
    echo "  stop          Stop all services (safe: preserves database volumes)"
    echo "  restart       Stop and then start_docker (safe: preserves database volumes)"
    echo "  clean         Stop all services and REMOVE volumes (hard reset)"
    echo "  reset         Wipe volumes and then start in hybrid mode"
    echo "  logs [svc]    View logs for a specific service (default: backend)"
    echo "  status        Show status of all Docker containers"
    echo "  build [target] Build Docker images (target options: development, production)"
    echo "  test          Run pytest"
    echo "  help          Show this help message"
    echo ""
    echo "Environment Switching:"
    echo "  Set ENVIRONMENT=production or REDIS_SSL=true in .env to use Redis SSL"
}

case "${1:-start}" in
    start)
        start
        ;;
    start_docker)
        start_docker
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs "$2"
        ;;
    status)
        status
        ;;
    clean)
        clean
        ;;
    reset)
        reset
        ;;
    test)
        test
        ;;
    build)
        build "$2"
        ;;
    help|--help|-h)
        help
        ;;
    *)
        log_error "Unknown command: $1"
        help
        exit 1
        ;;
esac
