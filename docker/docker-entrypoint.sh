#!/bin/bash
# ============================================
# Docker Entrypoint - Auto-Initialize Everything
# ============================================

set -e

echo "╔════════════════════════════════════════════╗"
echo "║   SIAB1 - INITIALIZATION                  ║"
echo "╚════════════════════════════════════════════╝"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Prepare Prometheus before Uvicorn spawns worker processes.
prepare_prometheus_multiprocess() {
    if [[ "$*" != *"uvicorn"* ]] || [[ -z "${PROMETHEUS_MULTIPROC_DIR:-}" ]]; then
        return
    fi

    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -maxdepth 1 -type f -name '*.db' -delete
    echo -e "${GREEN}✓ Prometheus multiprocess directory prepared${NC}"
}

# Function to wait for PostgreSQL
wait_for_postgres() {
    echo -e "${BLUE}[1/5] Waiting for PostgreSQL...${NC}"

    until PGPASSWORD=${DB_PASSWORD:-postgres} psql -h "${DB_HOST:-db}" -U "${DB_USER:-examuser}" -d "${DB_NAME:-siab1}" -c '\q' 2>/dev/null; do
        echo -e "${YELLOW}PostgreSQL is unavailable - sleeping${NC}"
        sleep 2
    done

    echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
}

# Function to wait for Redis
wait_for_redis() {
    echo -e "${BLUE}[2/5] Waiting for Redis...${NC}"

    until redis-cli -h "${REDIS_HOST:-redis}" ping 2>/dev/null | grep -q PONG; do
        echo -e "${YELLOW}Redis is unavailable - sleeping${NC}"
        sleep 2
    done

    echo -e "${GREEN}✓ Redis is ready${NC}"
}

# Function to check if database is initialized
check_database_initialized() {
    echo -e "${BLUE}[3/5] Checking database initialization...${NC}"

    TABLES_COUNT=$(PGPASSWORD=${DB_PASSWORD:-postgres} psql -h "${DB_HOST:-db}" -U "${DB_USER:-examuser}" -d "${DB_NAME:-siab1}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')

    if [ "$TABLES_COUNT" -gt "0" ]; then
        echo -e "${GREEN}✓ Database already initialized ($TABLES_COUNT tables)${NC}"
        return 0
    else
        echo -e "${YELLOW}Database needs initialization${NC}"
        return 1
    fi
}

# Function to fix upload directory permissions
fix_upload_permissions() {
    echo -e "${BLUE}[4/5] Fixing upload directory permissions...${NC}"

    # Ensure upload directories are writable by the app user
    if [ -d "/app/static/uploads" ]; then
        chmod -R 777 /app/static/uploads 2>/dev/null || true
        echo -e "${GREEN}✓ Upload directory permissions fixed${NC}"
    fi

    if [ -d "/app/uploads" ]; then
        chmod -R 777 /app/uploads 2>/dev/null || true
    fi
}

# Function to seed SEB presets if not exists
seed_seb_presets() {
    echo -e "${BLUE}[5/6] Checking SEB presets...${NC}"

    # Check if presets exist
    PRESET_COUNT=$(PGPASSWORD=${DB_PASSWORD:-postgres} psql -h "${DB_HOST:-db}" -U "${DB_USER:-examuser}" -d "${DB_NAME:-siab1}" -t -c "SELECT COUNT(*) FROM seb_config_templates WHERE is_default = true;" 2>/dev/null | tr -d ' ')

    if [ "$PRESET_COUNT" -ge "3" ]; then
        echo -e "${GREEN}✓ SEB presets already exist ($PRESET_COUNT presets)${NC}"
    else
        echo -e "${YELLOW}Seeding SEB presets via Python script...${NC}"
        python3 /app/scripts/init_seb_presets.py || echo -e "${YELLOW}Warning: Could not seed presets (may already exist)${NC}"
        echo -e "${GREEN}✓ SEB presets checked${NC}"
    fi
}

# Function to verify admin user
verify_admin_user() {
    echo -e "${BLUE}[6/6] Verifying admin user...${NC}"

    ADMIN_EXISTS=$(PGPASSWORD=${DB_PASSWORD:-postgres} psql -h "${DB_HOST:-db}" -U "${DB_USER:-examuser}" -d "${DB_NAME:-siab1}" -t -c "SELECT COUNT(*) FROM users WHERE username='admin';" 2>/dev/null | tr -d ' ')

    if [ "$ADMIN_EXISTS" -gt "0" ]; then
        echo -e "${GREEN}✓ Admin user exists${NC}"
    else
        echo -e "${RED}✗ No admin user found! Check init.sql${NC}"
    fi
}

# Main initialization
main() {
    echo ""
    echo -e "${BLUE}Starting initialization checks...${NC}"
    echo ""

    # Wait for dependencies
    wait_for_postgres
    wait_for_redis

    # Check and initialize database
    if check_database_initialized; then
        echo -e "${GREEN}Database is ready${NC}"
    else
        echo -e "${YELLOW}Database will be initialized by init.sql${NC}"
        sleep 5  # Wait for init.sql to complete
    fi

    # Fix upload permissions
    fix_upload_permissions

    # Seed presets only for API startup to avoid repeated races from Celery containers.
    if [[ "$*" == *"uvicorn"* ]]; then
        seed_seb_presets
    else
        echo -e "${BLUE}[5/6] Skipping SEB preset seeding for non-API process...${NC}"
    fi

    # Verify admin
    verify_admin_user

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   INITIALIZATION COMPLETE! ✅              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}Starting application server...${NC}"
    echo ""
}

# Run main initialization
main

# Clear stale metric files after initialization subprocesses have exited and
# immediately before Uvicorn spawns its worker processes.
prepare_prometheus_multiprocess "$@"

# Start the application
exec "$@"
