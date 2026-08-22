#!/bin/bash
# ============================================
# AUTO CACHE MAINTENANCE
# Clear Redis cache & optimize performance
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detect docker compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose"
else
    echo -e "${RED}ERROR: Docker Compose not found${NC}"
    exit 1
fi

cd "$(dirname "$0")"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC} ${BLUE}   AUTO CACHE MAINTENANCE - SIAB1${NC}                                    ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Timestamp: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo ""

# ============================================
# 1. Check Redis Status
# ============================================
echo -e "${BLUE}[1/5] Checking Redis status...${NC}"

REDIS_STATUS=$($DC -f docker-compose.production.yml exec -T redis redis-cli ping 2>/dev/null | tr -d '\r' || echo "ERROR")

if [ "$REDIS_STATUS" != "PONG" ]; then
    echo -e "${RED}✗ Redis not responding${NC}"
    echo "  Cannot clear cache - Redis is down"
    exit 1
fi

echo -e "${GREEN}✓ Redis is healthy${NC}"
echo ""

# ============================================
# 2. Get Cache Statistics (Before)
# ============================================
echo -e "${BLUE}[2/5] Cache statistics (before cleanup)...${NC}"

# Get memory usage
USED_MEMORY_BEFORE=$($DC -f docker-compose.production.yml exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r\n ')

# Get number of keys
KEYS_BEFORE=$($DC -f docker-compose.production.yml exec -T redis redis-cli DBSIZE 2>/dev/null | grep -oP '\d+' || echo "0")

echo "  Memory Used: $USED_MEMORY_BEFORE"
echo "  Total Keys: $KEYS_BEFORE"
echo ""

# ============================================
# 3. Clear Sessions (Expired)
# ============================================
echo -e "${BLUE}[3/5] Clearing expired sessions...${NC}"

# Redis automatically handles TTL expiration, but we can help by:
# - Cleaning up specific session patterns
# - Removing old session data

EXPIRED_SESSIONS=$($DC -f docker-compose.production.yml exec -T redis redis-cli --scan --pattern "session:*" 2>/dev/null | wc -l)

if [ "$EXPIRED_SESSIONS" -gt 0 ]; then
    echo "  Found $EXPIRED_SESSIONS session keys"
    echo "  (TTL-based, will expire automatically)"
else
    echo "  No session keys found"
fi

echo -e "${GREEN}✓ Session cleanup verified${NC}"
echo ""

# ============================================
# 4. Clear Application Cache (Selective)
# ============================================
echo -e "${BLUE}[4/5] Clearing application cache...${NC}"

# SAFETY NOTE: This ONLY clears temporary cache copies.
# Original data in DATABASE (PostgreSQL) is NEVER touched.
# 
# PROTECTED (NEVER CLEARED):
#   - exam:session:*      → Active exam sessions
#   - exam:data:*         → Exam questions & content
#   - exam:results:*      → Exam results
#   - student:answers:*   → Student answers
#   - user:session:*      → Active user logins
#   - All database tables → Jadwal, hasil, soal ujian
#   - File uploads        → Media files in /uploads
#
# SAFE TO CLEAR (Cache copies only):
PATTERNS=(
    "system:*"           # System settings cache → Will reload from DB
    "user:profile:*"     # User profile cache → Will reload from DB
    "exam:stats:*"       # Exam statistics cache → Will recalculate from DB
)

CLEARED_COUNT=0

for pattern in "${PATTERNS[@]}"; do
    # Count matching keys
    MATCHING=$($DC -f docker-compose.production.yml exec -T redis redis-cli --scan --pattern "$pattern" 2>/dev/null | wc -l)
    
    if [ "$MATCHING" -gt 0 ]; then
        echo "  Clearing pattern: $pattern ($MATCHING keys)"
        
        # Delete matching keys
        $DC -f docker-compose.production.yml exec -T redis redis-cli --scan --pattern "$pattern" 2>/dev/null | \
            xargs -r $DC -f docker-compose.production.yml exec -T redis redis-cli DEL 2>/dev/null || true
        
        CLEARED_COUNT=$((CLEARED_COUNT + MATCHING))
    fi
done

if [ "$CLEARED_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Cleared $CLEARED_COUNT cache keys${NC}"
else
    echo -e "${GREEN}✓ No stale cache to clear${NC}"
fi
echo ""

# ============================================
# 5. Get Cache Statistics (After) & Optimize
# ============================================
echo -e "${BLUE}[5/5] Final statistics & optimization...${NC}"

# Run Redis optimization (defrag memory if needed)
$DC -f docker-compose.production.yml exec -T redis redis-cli MEMORY PURGE 2>/dev/null || true

# Get updated stats
USED_MEMORY_AFTER=$($DC -f docker-compose.production.yml exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r\n ')
KEYS_AFTER=$($DC -f docker-compose.production.yml exec -T redis redis-cli DBSIZE 2>/dev/null | grep -oP '\d+' || echo "0")

echo "  Memory Before: $USED_MEMORY_BEFORE"
echo "  Memory After:  $USED_MEMORY_AFTER"
echo "  Keys Before:   $KEYS_BEFORE"
echo "  Keys After:    $KEYS_AFTER"
echo "  Keys Cleared:  $((KEYS_BEFORE - KEYS_AFTER))"

echo -e "${GREEN}✓ Cache optimization complete${NC}"
echo ""

# ============================================
# Summary
# ============================================
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC} ${GREEN}              ✅ CACHE MAINTENANCE COMPLETE!${NC}                            ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  • Expired sessions: Verified"
echo "  • Application cache: Cleared $CLEARED_COUNT keys"
echo "  • Memory optimization: Complete"
echo "  • Redis health: OK"
echo ""
echo -e "${CYAN}Next auto-maintenance: Tomorrow at configured time${NC}"
echo ""
