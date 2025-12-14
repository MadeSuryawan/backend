#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
# Note: In IDX, secrets are often managed differently, but we'll stick to your .env convention
ENV_FILE="./secrets/.env"
PROJECT_NAME="baliblissed"

DB_NAME=""
DB_USER=""

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
        log_warning "Environment file $ENV_FILE not found."
        log_warning "Using environment variables provided by IDX dev.nix..."
    fi
}

# Extract database name from DATABASE_URL
get_db_name() {
    # If DATABASE_URL is set (from .env), use it
    if [ -n "$DATABASE_URL" ]; then
        DB_NAME=$(echo $DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')
        DB_USER=$(echo $DATABASE_URL | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    fi
    
    # Fallback to IDX defaults if empty
    if [ -z "$DB_NAME" ]; then
        DB_NAME="${POSTGRES_DB:-baliblissed}"
    fi

    if [ -z "$DB_USER" ]; then
        DB_USER="${POSTGRES_USER:-user}"
    fi
}

# Checking Postgres connection
check_postgres() {
    log_info "Checking Postgres connection..."
    if command -v psql &> /dev/null; then
        # Try to connect to PostgreSQL
        # We use the implicit host/port from env vars
        if psql -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
            log_success "✅ Postgres connection successful"
        else
            log_error "❌ Could not connect to PostgreSQL database '$DB_NAME' as user '$DB_USER'"
            log_error "   Ensure the service is running and the database exists."
            exit 1
        fi
    else
        log_error "❌ psql command not found"
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
        dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true

        log_info "📦 Creating new database..."
        createdb -U "$DB_USER" "$DB_NAME"
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

# Create required directories
create_directories() {
    log_info "Creating logs directory..."
    mkdir -p ./logs
    # Redis data dir in IDX is managed by the service or tmp, usually doesn't need ./data/redis
}

# Start development environment
start() {
    log_info "🚀 BaliBlissed Blog API - IDX Quick Start"
    log_info "========================================="
    log_info ""
    
    load_env
    get_db_name
    check_postgres
    ask_recreate_db
    create_directories
    
    log_info "Starting Uvicorn..."
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
}

case "${1:-start}" in
    start)
        start
        ;;
    help|--help|-h)
        echo "Usage: ./scripts/run_idx.sh [start]"
        ;;
    *)
        log_error "Unknown command: $1"
        exit 1
        ;;
esac
