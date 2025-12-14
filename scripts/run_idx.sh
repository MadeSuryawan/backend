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
# Note: In IDX, secrets are often managed differently, but we'll stick to your .env convention
ENV_FILE="./secrets/.env"
PROJECT_NAME="baliblissed"

# Default IDX values (overridden by env if present, or fallback logic)
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
        # Export variables, but don't override existing ones if we want to force IDX specific values
        export $(grep -v '^#' "$ENV_FILE" | xargs)
    else
        log_warning "Environment file $ENV_FILE not found."
        log_warning "Using environment variables provided by IDX dev.nix..."
    fi
}

# Determine database configuration
configure_idx_db() {
    # IDX uses specific environment variables or defaults
    # We want to use these INSTEAD of what's in .env if running in IDX context,
    # or at least ensure we are connecting to the IDX postgres instance.
    
    # In IDX, POSTGRES_DB and POSTGRES_USER are usually set by dev.nix or the service
    # If not, we default to what IDX expects (user 'user', db 'baliblissed' or 'postgres')
    
    # Check if we are actually in an IDX environment (simple heuristic or assumed since this is run_idx.sh)
    # We will FORCE the database url for the application runtime in this session
    
    IDX_DB_USER="${POSTGRES_USER:-user}"
    IDX_DB_NAME="${POSTGRES_DB:-baliblissed}"
    IDX_DB_PASSWORD="${POSTGRES_PASSWORD:-password}"
    
    # IDX FIX: Use Unix socket if TCP fails or for consistency if needed.
    # But usually localhost works if bound correctly. 
    # Current issue: Server bound to /tmp/postgresql but default psql looks in /tmp or /var/run.
    # We can force host to be the socket directory if we know it.
    
    # If the user manually started postgres with a specific socket dir, we should respect it
    # or try to detect it. For now, let's stick to TCP localhost if possible, 
    # OR if we know where the socket is.
    
    # Based on the troubleshooting, the process is running on /tmp/postgres
    IDX_DB_HOST="/tmp/postgres" 
    # Note: asyncpg (used by SQLAlchemy) needs host to be the path for unix socket
    
    IDX_DB_PORT="5432"

    log_info "Configuring for IDX environment..."
    log_info "Overriding DATABASE_URL to use IDX defaults: user='$IDX_DB_USER', db='$IDX_DB_NAME', host='$IDX_DB_HOST'"

    # Override the exported DATABASE_URL for the Python process
    # For Unix socket, host is the directory path
    # URL encoded path is safer but for local usually just path works if driver supports it.
    # Asyncpg supports unix sockets by specifying the path as host.
    export DATABASE_URL="postgresql+asyncpg://$IDX_DB_USER:$IDX_DB_PASSWORD@/$IDX_DB_NAME?host=$IDX_DB_HOST"
    
    # Also set env vars for psql helper
    export PGHOST="$IDX_DB_HOST"
    export DB_USER="$IDX_DB_USER"
    export DB_NAME="$IDX_DB_NAME"
    
    # Also set Redis URL for IDX (Unix socket)
    export REDIS_URL="redis+unix:///tmp/redis/redis.sock"
    log_info "Overriding REDIS_URL to use IDX socket: $REDIS_URL"
}

# Checking Postgres connection
check_postgres() {
    log_info "Checking Postgres connection..."
    if command -v psql &> /dev/null; then
        # Try to connect to PostgreSQL using the configured variables
        # PGHOST is set, so it should find the socket
        if psql -U "$DB_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; then
            log_success "✅ Postgres connection successful"
        else
            log_error "❌ Could not connect to PostgreSQL database '$DB_NAME' as user '$DB_USER' on host '$PGHOST'"
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
    log_info "Creating logs directory..."
    mkdir -p ./logs
}

# Start development environment
start() {
    log_info "🚀 BaliBlissed Blog API - IDX Quick Start"
    log_info "========================================="
    log_info ""
    
    load_env
    # Apply IDX specific overrides AFTER loading env
    configure_idx_db
    
    check_postgres
    ask_recreate_db

    # check_docker

    create_directories
    
    # log_info "Starting Docker..."
    # # docker-compose --profile development up --build -d
    # docker-compose up -d
    
    log_info "Starting Uvicorn..."
    # The variables exported in configure_idx_db will be picked up by the app
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --workers 4 --loop uvloop --http httptools
    # log_success "Development environment started successfully!"
}

# Stop development environment
stop() {
    log_info "Stopping BaliBlissed development environment..."
    # docker-compose --profile development down
    docker-compose down -v
    log_success "Development environment stopped successfully!"
}

case "${1:-start}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    help|--help|-h)
        echo "Usage: ./scripts/run_idx.sh [start]"
        ;;
    *)
        log_error "Unknown command: $1"
        exit 1
        ;;
esac
