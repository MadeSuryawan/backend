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

# Extract database name from DATABASE_URL
get_db_name() {
    DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')
    DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    
    if [ -z "$DB_NAME" ]; then
    DB_NAME="baliblissed"
    fi

    if [ -z "$DB_USER" ]; then
        DB_USER="postgres"
    fi
}

# Checking Postgres connection
check_postgres() {
    log_info "Checking Postgres connection..."
    if command -v psql &> /dev/null; then
        # Try to connect to PostgreSQL
        if psql -U $DB_USER -c '\q' 2>/dev/null; then
            log_success "✅ Postgres connection successful"
        else
            log_error "❌ Could not connect to PostgreSQL"
            log_error "   Make sure PostgreSQL is running:"
            log_error "   - macOS: brew services start postgresql"
            log_error "   - Linux: sudo service postgresql start"
            exit 1
        fi
    else
        log_error "❌ psql command not found"
        log_error "   Please install PostgreSQL"
        exit 1
    fi
    log_info ""
}

# Ask user if they want to recreate the database
ask_recreate_db() {
    log_info "🗄️  Database Setup"
    log_info "Current database: $DB_NAME"
    log_info ""
    read -p "Do you want to recreate the database? This will DELETE all existing data! (y/N): " -n 1 -r
    log_info ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "⚠️  Dropping existing database..."
        dropdb -U $DB_USER --if-exists $DB_NAME 2>/dev/null || true

        log_info "📦 Creating new database..."
        createdb -U $DB_USER $DB_NAME
        log_info "✅ Database created"
        log_info ""

        log_info "🔧 Initializing database tables..."
        python -m app.db.init_db
        log_info "✅ Database initialized"
    else
        log_info "🔧 Checking/updating database tables..."
        python -m app.db.init_db
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
    
    # docker-compose --profile development up --build -d
    docker-compose up -d
    uvicorn app:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
    # log_success "Development environment started successfully!"
}

# Stop development environment
stop() {
    log_info "Stopping BaliBlissed development environment..."
    # docker-compose --profile development down
    docker-compose down -v
    log_success "Development environment stopped successfully!"
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
