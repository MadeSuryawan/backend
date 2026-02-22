#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.yml"
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
load_env() {
    if [ -f "$ENV_FILE" ]; then
        log_info "Loading environment variables from $ENV_FILE"
        export $(grep -v '^#' "$ENV_FILE" | xargs)
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
    # log_info "Starting BaliBlissed development environment..."
    log_info "🚀 BaliBlissed Blog API - Quick Start"
    log_info "======================================"
    log_info ""
    load_env
    get_db_name
    check_postgres
    ask_recreate_db
    check_docker
    create_directories
    
    # Start services with otel profile to enable the collector
    docker-compose --profile otel up -d
    uv run uvicorn app:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
    # log_success "Development environment started successfully!"
}

# Stop development environment
stop() {
    log_info "Stopping BaliBlissed development environment..."
    load_env
    # Stop services including those in the otel profile
    docker-compose --profile otel down -v
    
    # Cleanup browser state to prevent auto-launch issues
    if [ -f "./scripts/clean_browser.sh" ]; then
        ./scripts/clean_browser.sh
    fi
    
    log_success "Development environment stopped successfully!"
}

# Clean development environment
clean() {
    log_info "Cleaning development environment..."
    stop
    log_success "Environment cleaned!"
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

case "${1:-help}" in
    start)
        start
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
    shell)
        shell
        ;;
    redis)
        redis
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
