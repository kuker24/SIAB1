#!/bin/bash
# ============================================
# SYNC STATUS CHECKER
# Verifies database replication and file sync
# ============================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔍 Checking Synchronization Status...${NC}"
echo "========================================"

# 1. Check Database Replication (Master Side)
echo -e "\n[1] Database Replication Status (Master)"
DB_CONTAINER=$(docker compose -f docker-compose.production.yml ps -q db)

if [ -z "$DB_CONTAINER" ]; then
    echo -e "${RED}❌ Database container is not running!${NC}"
else
    # Check pg_stat_replication
    REPLICATION_COUNT=$(docker exec $DB_CONTAINER psql -U examuser -d exam_system -tAc "SELECT count(*) FROM pg_stat_replication;")
    
    if [ "$REPLICATION_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Replication Active${NC}: $REPLICATION_COUNT replica(s) connected."
        
        # Show details
        docker exec $DB_CONTAINER psql -U examuser -d exam_system -c \
            "SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication;"
    else
        echo -e "${YELLOW}⚠ No replicas connected.${NC} (Is the secondary server running?)"
    fi
fi

# 2. Check Configuration Consistency
echo -e "\n[2] Configuration Check"
if [ -f .env ]; then
    echo -e "${GREEN}✓ .env file exists${NC}"
    
    # Check if critical keys match defaults (warning)
    source .env
    if [ "$DB_PASSWORD" == "changeme" ] || [ "$DB_PASSWORD" == "rahasia" ]; then
         echo -e "${YELLOW}⚠ Warning: Using default DB_PASSWORD. Please change for production.${NC}"
    fi
else
    echo -e "${RED}❌ .env file missing!${NC}"
fi

# 3. Last Sync Status
echo -e "\n[3] Last Synchronization"
# We don't have a log file for sync yet, but we can check if the script exists
if [ -f scripts/sync_robust.sh ]; then
    echo -e "${GREEN}✓ Robust sync script available${NC} (scripts/sync_robust.sh)"
    echo "  Run './scripts/sync_robust.sh' to sync files."
else
    echo -e "${RED}❌ Robust sync script missing.${NC}"
fi

echo -e "\n========================================"
echo -e "${GREEN}Done.${NC}"
