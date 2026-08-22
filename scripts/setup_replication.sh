#!/bin/bash
# ==========================================
# SETUP REPLICATION (PHASE 3)
# ==========================================

# Load .env
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
fi

DB_CONTAINER=$(docker compose -f ../docker-compose.production.yml ps -q db)

if [ -z "$DB_CONTAINER" ]; then
    echo "❌ Error: DB Master container not running."
    echo "Please start the system first: ./install.sh or docker compose up -d"
    exit 1
fi

echo "🚀 Setting up Replication..."

# 1. Create Replicator User
echo "creating 'replicator' user on Master..."
docker exec -i $DB_CONTAINER psql -U examuser -d exam_system -c "
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
        CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD '$DB_PASSWORD';
    END IF;
END
\$\$;"

# 2. Update pg_hba.conf (Allow replication)
# Note: Alpine postgres config location
HBA_PATH="/var/lib/postgresql/data/pg_hba.conf"
echo "Configuring pg_hba.conf..."

# Helper function to add line if not exists
add_hba_rule() {
    local rule="$1"
    # Check if rule exists (ignoring whitespace)
    if ! docker exec $DB_CONTAINER grep -qF "$rule" "$HBA_PATH"; then
        echo "  Adding rule: $rule"
        docker exec -u 0 -i $DB_CONTAINER bash -c "echo '$rule' >> $HBA_PATH"
    else
        echo "  Rule already exists (Skipping): $rule"
    fi
}

add_hba_rule "host replication replicator 0.0.0.0/0 md5"
add_hba_rule "host all all 0.0.0.0/0 md5"

# 3. Reload Config
echo "Reloading Master configuration..."
docker exec -i $DB_CONTAINER psql -U examuser -d exam_system -c "SELECT pg_reload_conf();"

echo ""
echo "✅ Replication Setup Complete!"
echo ""
echo "👉 To start Read Replica:"
echo "   1. Add this to .env file:"
echo "      DATABASE_READ_URL=postgresql+asyncpg://replicator:$DB_PASSWORD@db_replica:5432/exam_system"
echo ""
echo "   2. Start replica container:"
echo "      docker compose -f docker-compose.production.yml --profile scaling up -d"
echo ""
