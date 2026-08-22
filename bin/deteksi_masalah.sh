#!/bin/bash
# ============================================================================
# DETEKSI MASALAH - Comprehensive Issue Detection Script for Ujian Online
# ============================================================================
# Version: 1.0
# Author: Auto-generated for Ujian Online System
# 
# This script performs comprehensive diagnostics on your Ujian Online
# deployment to detect and report issues in detail.
#
# USAGE:
#   ./deteksi_masalah.sh           # Full diagnostic
#   ./deteksi_masalah.sh --quick   # Quick check (skip deep analysis)
#   ./deteksi_masalah.sh --fix     # Attempt automatic fixes
#   ./deteksi_masalah.sh --api     # API endpoints test only
#   ./deteksi_masalah.sh --db      # Database check only
#   ./deteksi_masalah.sh --logs    # Logs analysis only
#
# ============================================================================

set -o pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'
BOLD='\033[1m'

# Counters
ERRORS=0
WARNINGS=0
FIXES=0

# Config
COMPOSE_FILE="docker-compose.production.yml"
DB_NAME="exam_system"
DB_USER="examuser"
API_PORT=8000
NGINX_PORT=8080

# Detect docker compose command
if docker compose version &> /dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose &> /dev/null; then
    DC="docker-compose"
else
    echo -e "${RED}ERROR: Docker Compose not found!${NC}"
    exit 1
fi

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${WHITE}$1${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
}

print_subheader() {
    echo ""
    echo -e "${MAGENTA}━━━ $1 ━━━${NC}"
}

print_ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "  ${RED}✗${NC} $1"
    ((ERRORS++))
}

print_warning() {
    echo -e "  ${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

print_fix() {
    echo -e "  ${GREEN}🔧${NC} $1"
    ((FIXES++))
}

# ============================================================================
# 1. DOCKER CONTAINERS CHECK
# ============================================================================

check_containers() {
    print_header "1. DOCKER CONTAINERS STATUS"
    
    # Check if compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_error "Compose file not found: $COMPOSE_FILE"
        return 1
    fi
    print_ok "Compose file exists: $COMPOSE_FILE"
    
    # List all containers
    print_subheader "Container Status"
    
    local containers=$(${DC} -f $COMPOSE_FILE ps --format json 2>/dev/null || ${DC} -f $COMPOSE_FILE ps 2>/dev/null)
    
    if [ -z "$containers" ]; then
        print_error "No containers found! Services might not be running."
        print_info "Try: ${DC} -f $COMPOSE_FILE up -d"
        return 1
    fi
    
    # Check each critical service
    local services=("api" "db" "redis" "nginx")
    
    for svc in "${services[@]}"; do
        local status=$(${DC} -f $COMPOSE_FILE ps $svc 2>/dev/null | grep -i "up\|running" || echo "")
        if [ -n "$status" ]; then
            # Check health status
            local health=$(docker inspect --format='{{.State.Health.Status}}' "$(${DC} -f $COMPOSE_FILE ps -q $svc 2>/dev/null)" 2>/dev/null || echo "no-healthcheck")
            if [ "$health" == "healthy" ]; then
                print_ok "$svc: Running (Healthy)"
            elif [ "$health" == "unhealthy" ]; then
                print_error "$svc: Running but UNHEALTHY"
            else
                print_ok "$svc: Running"
            fi
        else
            print_error "$svc: NOT RUNNING"
        fi
    done
    
    # Check optional services
    local optional_services=("celery_worker" "celery_beat" "flutter_builder")
    print_subheader "Optional Services"
    
    for svc in "${optional_services[@]}"; do
        local status=$(${DC} -f $COMPOSE_FILE ps $svc 2>/dev/null | grep -i "up\|running" || echo "")
        if [ -n "$status" ]; then
            print_ok "$svc: Running"
        else
            print_info "$svc: Not running (optional)"
        fi
    done
}

# ============================================================================
# 2. DATABASE CHECK
# ============================================================================

check_database() {
    print_header "2. DATABASE DIAGNOSTICS"
    
    # Connection test
    print_subheader "Connection Test"
    
    if ! ${DC} -f $COMPOSE_FILE exec -T db pg_isready -U $DB_USER -d $DB_NAME &>/dev/null; then
        print_error "Cannot connect to database!"
        print_info "Check if db container is running"
        return 1
    fi
    print_ok "Database connection successful"
    
    # Check critical tables
    print_subheader "Critical Tables"
    
    local tables=("users" "exams" "questions" "question_options" "exam_sessions" "answers")
    
    for table in "${tables[@]}"; do
        local exists=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '$table');" 2>/dev/null)
        
        if [ "$exists" == "t" ]; then
            local count=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
                "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
            print_ok "$table: exists ($count rows)"
        else
            print_error "$table: MISSING!"
        fi
    done
    
    # Check critical columns (common issues)
    print_subheader "Critical Columns (Recent Issues)"
    
    local critical_columns=(
        "exams:has_ever_had_results"
        "exams:is_deleted"
        "exam_sessions:archived_exam_title"
    )
    
    for col_def in "${critical_columns[@]}"; do
        local table=$(echo $col_def | cut -d: -f1)
        local column=$(echo $col_def | cut -d: -f2)
        
        local exists=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = '$table' AND column_name = '$column');" 2>/dev/null)
        
        if [ "$exists" == "t" ]; then
            print_ok "$table.$column: exists"
        else
            print_error "$table.$column: MISSING!"
            
            # Auto-fix if --fix flag
            if [ "$AUTO_FIX" == "true" ]; then
                print_fix "Attempting to add missing column..."
                # Add specific fixes for known columns
                case "$column" in
                    "has_ever_had_results")
                        ${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -c \
                            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS has_ever_had_results BOOLEAN DEFAULT FALSE NOT NULL;" &>/dev/null
                        ;;
                    "is_deleted")
                        ${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -c \
                            "ALTER TABLE exams ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE NOT NULL;" &>/dev/null
                        ;;
                esac
                print_ok "Column added (restart API to apply)"
            fi
        fi
    done
    
    # Check indexes
    print_subheader "Performance Indexes"
    
    local indexes=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';" 2>/dev/null || echo "0")
    
    if [ "$indexes" -gt 20 ]; then
        print_ok "Indexes: $indexes (good coverage)"
    elif [ "$indexes" -gt 10 ]; then
        print_warning "Indexes: $indexes (consider adding more)"
    else
        print_error "Indexes: $indexes (too few, performance may suffer)"
    fi
}

# ============================================================================
# 3. API HEALTH CHECK
# ============================================================================

check_api() {
    print_header "3. API HEALTH CHECK"
    
    # Basic health endpoint
    print_subheader "Health Endpoints"
    
    local health=$(curl -sf http://localhost:$API_PORT/health 2>/dev/null)
    if [ -n "$health" ]; then
        print_ok "API /health: OK"
    else
        print_error "API /health: FAILED"
        print_info "API might be starting up or crashed"
    fi
    
    # OpenAPI docs
    local docs=$(curl -sf http://localhost:$API_PORT/docs 2>/dev/null | head -c 100)
    if [ -n "$docs" ]; then
        print_ok "API /docs: Accessible"
    else
        print_warning "API /docs: Not accessible"
    fi
    
    # Test critical endpoints (without auth)
    print_subheader "Critical Endpoints (Auth-Protected)"
    
    local endpoints=(
        "/api/auth/me:403:Auth endpoint"
        "/api/exams:403:Exams endpoint"
    )
    
    for ep_def in "${endpoints[@]}"; do
        local endpoint=$(echo $ep_def | cut -d: -f1)
        local expected_code=$(echo $ep_def | cut -d: -f2)
        local description=$(echo $ep_def | cut -d: -f3)
        
        local response_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$API_PORT$endpoint 2>/dev/null)
        
        if [ "$response_code" == "$expected_code" ] || [ "$response_code" == "401" ]; then
            print_ok "$endpoint: $description (Protected - requires auth)"
        elif [ "$response_code" == "200" ]; then
            print_ok "$endpoint: $description (HTTP 200)"
        elif [ "$response_code" == "500" ]; then
            print_error "$endpoint: SERVER ERROR (HTTP 500)"
        elif [ "$response_code" == "000" ]; then
            print_error "$endpoint: CONNECTION REFUSED"
        else
            print_info "$endpoint: HTTP $response_code"
        fi
    done
    
    # Test the problematic results endpoint
    print_subheader "Known Problem Endpoints"
    
    local results_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$API_PORT/api/exams/results/all 2>/dev/null)
    if [ "$results_code" == "401" ] || [ "$results_code" == "403" ]; then
        print_ok "/api/exams/results/all: Working (requires auth)"
    elif [ "$results_code" == "500" ]; then
        print_error "/api/exams/results/all: SERVER ERROR - Check logs!"
    else
        print_info "/api/exams/results/all: Response $results_code"
    fi
}

# ============================================================================
# 4. LOG ANALYSIS
# ============================================================================

check_logs() {
    print_header "4. LOG ANALYSIS"
    
    print_subheader "Recent Errors (Last 100 lines)"
    
    # Get API errors
    local api_errors=$(${DC} -f $COMPOSE_FILE logs --tail=100 api 2>&1 | grep -iE "error|exception|traceback|failed|critical" | tail -10)
    
    if [ -z "$api_errors" ]; then
        print_ok "No recent errors in API logs"
    else
        print_error "Found errors in API logs:"
        echo ""
        echo -e "${RED}$api_errors${NC}" | head -20
        echo ""
    fi
    
    # Check for common Python errors
    print_subheader "Common Python Errors"
    
    local common_errors=(
        "NameError:Missing import or undefined variable"
        "ImportError:Module import failed"
        "ModuleNotFoundError:Missing dependency"
        "AttributeError:Method or property not found"
        "TypeError:Wrong argument type"
        "KeyError:Missing dictionary key"
        "ValidationError:Pydantic validation failed"
        "IntegrityError:Database constraint violated"
        "OperationalError:Database connection issue"
    )
    
    local log_content=$(${DC} -f $COMPOSE_FILE logs --tail=500 api 2>&1)
    
    for err_def in "${common_errors[@]}"; do
        local err_type=$(echo $err_def | cut -d: -f1)
        local err_desc=$(echo $err_def | cut -d: -f2)
        
        # Fix: properly handle count with tr to remove whitespace/newlines
        local count=$(echo "$log_content" | grep -c "$err_type" 2>/dev/null | tr -d '\n\r' || echo "0")
        count=${count:-0}  # Default to 0 if empty
        
        if [ "$count" -gt 0 ] 2>/dev/null; then
            print_error "$err_type: $count occurrences ($err_desc)"
            
            # Show last occurrence
            local last_error=$(echo "$log_content" | grep -A 3 "$err_type" | tail -5)
            echo -e "    ${YELLOW}Last occurrence:${NC}"
            echo "$last_error" | sed 's/^/        /'
            echo ""
        fi
    done
    
    # Check for import errors specifically (like our and_ issue)
    print_subheader "Import/Definition Issues"
    
    local undefined=$(echo "$log_content" | grep -oE "name '[^']+' is not defined" | sort | uniq)
    
    if [ -n "$undefined" ]; then
        print_error "Found undefined names:"
        echo "$undefined" | while read line; do
            echo -e "    ${RED}• $line${NC}"
        done
        print_info "Fix: Add missing imports to the relevant Python file"
    else
        print_ok "No undefined name errors found"
    fi
}

# ============================================================================
# 5. CODE VALIDATION (Python imports check)
# ============================================================================

check_code() {
    print_header "5. CODE VALIDATION"
    
    print_subheader "Python Syntax Check"
    
    # Check if we can access the container's code
    local py_files=$(${DC} -f $COMPOSE_FILE exec -T api find /app -name "*.py" -type f 2>/dev/null | head -20)
    
    if [ -z "$py_files" ]; then
        print_warning "Cannot access Python files in container"
        return
    fi
    
    # Check for common issues in critical files
    print_subheader "Critical Import Checks"
    
    # Check exams.py for required imports
    local exams_imports=$(${DC} -f $COMPOSE_FILE exec -T api cat /app/app/api/exams.py 2>/dev/null | head -50)
    
    if echo "$exams_imports" | grep -q "from sqlalchemy import.*and_"; then
        print_ok "exams.py: and_ import present"
    else
        print_error "exams.py: and_ import MISSING!"
        print_info "Fix: Add 'and_' to the sqlalchemy imports"
    fi
    
    if echo "$exams_imports" | grep -q "from sqlalchemy import.*or_"; then
        print_ok "exams.py: or_ import present"
    else
        print_warning "exams.py: or_ import might be missing"
    fi
    
    # Check for common missing imports in all API files
    # Note: sessions.py tidak diperlukan - session logic ada di exams.py
    local api_files=("exams.py" "users.py" "auth.py" "templates.py" "grading.py")
    
    print_subheader "API File Validation"
    
    for file in "${api_files[@]}"; do
        local exists=$(${DC} -f $COMPOSE_FILE exec -T api test -f /app/app/api/$file 2>/dev/null && echo "yes" || echo "no")
        if [ "$exists" == "yes" ]; then
            print_ok "app/api/$file: exists"
        else
            print_error "app/api/$file: not found (critical file missing!)"
        fi
    done
}

# ============================================================================
# 6. NGINX / FRONTEND CHECK
# ============================================================================

check_nginx() {
    print_header "6. NGINX / FRONTEND CHECK"
    
    print_subheader "Nginx Status"
    
    local nginx_test=$(${DC} -f $COMPOSE_FILE exec -T nginx nginx -t 2>&1)
    if echo "$nginx_test" | grep -q "successful"; then
        print_ok "Nginx configuration: Valid"
    else
        print_error "Nginx configuration: Invalid"
        echo "$nginx_test" | sed 's/^/    /'
    fi
    
    # Check frontend access (Jinja2 template routes)
    print_subheader "Frontend Pages (Jinja2 Routes)"
    
    # Updated: aplikasi menggunakan Jinja2 template routing, bukan static HTML
    local pages=(
        "/:Root endpoint"
        "/admin/:Admin dashboard"
        "/admin/exams:Exam management"
        "/admin/results:Results page"
        "/student/:Student dashboard"
        "/student/exam:Student exam page"
    )
    
    for page_def in "${pages[@]}"; do
        local page=$(echo $page_def | cut -d: -f1)
        local desc=$(echo $page_def | cut -d: -f2)
        local code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$NGINX_PORT$page 2>/dev/null)
        
        if [ "$code" == "200" ]; then
            print_ok "$page: Accessible ($desc)"
        elif [ "$code" == "304" ]; then
            print_ok "$page: Accessible ($desc - cached)"
        elif [ "$code" == "404" ]; then
            print_error "$page: Not Found (HTTP 404) - Check Jinja2 template"
        else
            print_warning "$page: HTTP $code ($desc)"
        fi
    done
}

# ============================================================================
# 7. REDIS CHECK
# ============================================================================

check_redis() {
    print_header "7. REDIS CACHE CHECK"
    
    local redis_ping=$(${DC} -f $COMPOSE_FILE exec -T redis redis-cli ping 2>/dev/null)
    
    if [ "$redis_ping" == "PONG" ]; then
        print_ok "Redis: Responding"
        
        # Check memory usage
        local memory=$(${DC} -f $COMPOSE_FILE exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
        print_info "Memory usage: $memory"
        
        # Check connected clients
        local clients=$(${DC} -f $COMPOSE_FILE exec -T redis redis-cli info clients 2>/dev/null | grep "connected_clients" | cut -d: -f2 | tr -d '\r')
        print_info "Connected clients: $clients"
    else
        print_error "Redis: Not responding"
    fi
}

# ============================================================================
# 8. SYSTEM RESOURCES CHECK
# ============================================================================

check_system() {
    print_header "8. SYSTEM RESOURCES"
    
    print_subheader "Memory Usage"
    
    local total_mem=$(free -h | awk '/^Mem:/ {print $2}')
    local used_mem=$(free -h | awk '/^Mem:/ {print $3}')
    local free_mem=$(free -h | awk '/^Mem:/ {print $4}')
    local mem_percent=$(free | awk '/^Mem:/ {printf("%.0f", $3/$2 * 100)}')
    
    if [ "$mem_percent" -lt 80 ]; then
        print_ok "Memory: $used_mem / $total_mem used ($mem_percent%)"
    elif [ "$mem_percent" -lt 90 ]; then
        print_warning "Memory: $used_mem / $total_mem used ($mem_percent%) - Getting high"
    else
        print_error "Memory: $used_mem / $total_mem used ($mem_percent%) - CRITICAL!"
    fi
    
    print_subheader "Disk Usage"
    
    local disk_percent=$(df -h . | awk 'NR==2 {gsub(/%/,""); print $5}')
    local disk_avail=$(df -h . | awk 'NR==2 {print $4}')
    
    if [ "$disk_percent" -lt 80 ]; then
        print_ok "Disk: $disk_avail available ($disk_percent% used)"
    elif [ "$disk_percent" -lt 90 ]; then
        print_warning "Disk: $disk_avail available ($disk_percent% used) - Getting full"
    else
        print_error "Disk: $disk_avail available ($disk_percent% used) - CRITICAL!"
    fi
    
    print_subheader "Docker Resource Usage"
    
    echo ""
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null | head -10
    echo ""
    
    # Check API container memory specifically (critical for 600+ users)
    print_subheader "API Container Memory Check"
    
    local api_mem_percent=$(docker stats --no-stream --format "{{.Name}} {{.MemPerc}}" 2>/dev/null | grep -i "api" | awk '{print $2}' | sed 's/%//' | tr -d '\n\r')
    
    if [ -n "$api_mem_percent" ]; then
        # Remove any decimal point for comparison
        local api_mem_int=$(echo "$api_mem_percent" | cut -d. -f1)
        
        if [ "$api_mem_int" -ge 95 ] 2>/dev/null; then
            print_error "API Container Memory: ${api_mem_percent}% - CRITICAL! May crash soon"
            print_info "Recommendation: Reduce workers or increase memory limit in docker-compose.production.yml"
        elif [ "$api_mem_int" -ge 85 ] 2>/dev/null; then
            print_warning "API Container Memory: ${api_mem_percent}% - High usage"
        else
            print_ok "API Container Memory: ${api_mem_percent}% - Normal"
        fi
    else
        print_info "Could not check API container memory"
    fi
}

# ============================================================================
# 9. API PERFORMANCE METRICS
# ============================================================================

check_api_performance() {
    print_header "9. API PERFORMANCE METRICS"
    
    print_subheader "Response Time Check"
    
    # Test critical endpoints for response time
    local endpoints=(
        "/health:Health check"
        "/api/auth/login:Login endpoint"
        "/api/exams:Exams list"
    )
    
    for ep_def in "${endpoints[@]}"; do
        local endpoint=$(echo $ep_def | cut -d: -f1)
        local description=$(echo $ep_def | cut -d: -f2)
        
        # Measure response time in milliseconds
        local start_time=$(date +%s%N)
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$API_PORT$endpoint 2>/dev/null)
        local end_time=$(date +%s%N)
        
        # Calculate duration in milliseconds
        local duration=$(( (end_time - start_time) / 1000000 ))
        
        # Only check if endpoint responded
        if [ "$http_code" != "000" ]; then
            if [ "$duration" -lt 500 ]; then
                print_ok "$endpoint: ${duration}ms ($description - fast)"
            elif [ "$duration" -lt 2000 ]; then
                print_warning "$endpoint: ${duration}ms ($description - acceptable)"
            else
                print_error "$endpoint: ${duration}ms ($description - TOO SLOW!)"
            fi
        else
            print_error "$endpoint: No response ($description - API down?)"
        fi
    done
    
    # Check worker utilization
    print_subheader "Worker Status"
    
    # Fix: properly handle count with tr to remove whitespace/newlines
    local total_workers=$(${DC} -f $COMPOSE_FILE exec -T api ps aux 2>/dev/null | grep -c "uvicorn.workers" 2>/dev/null | tr -d '\n\r' || echo "0")
    total_workers=${total_workers:-0}  # Default to 0 if empty
    
    if [ "$total_workers" -gt 0 ] 2>/dev/null; then
        print_ok "Active workers: $total_workers"
        
        # Get worker count from docker-compose config
        local configured_workers=$(grep "workers" $COMPOSE_FILE | grep -oP '\-\-workers \K[0-9]+' 2>/dev/null || echo "unknown")
        if [ "$configured_workers" != "unknown" ]; then
            print_info "Configured workers: $configured_workers"
        fi
    else
        print_warning "Could not detect worker count"
    fi
}

# ============================================================================
# 10. DATABASE PERFORMANCE CHECK
# ============================================================================

check_database_performance() {
    print_header "10. DATABASE PERFORMANCE CHECK"
    
    print_subheader "Connection Pool Status"
    
    # Check active connections
    local active_conn=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null || echo "0")
    
    local idle_conn=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';" 2>/dev/null || echo "0")
    
    local total_conn=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null || echo "0")
    
    # Clean up values (remove whitespace)
    active_conn=$(echo "$active_conn" | tr -d ' \n\r')
    idle_conn=$(echo "$idle_conn" | tr -d ' \n\r')
    total_conn=$(echo "$total_conn" | tr -d ' \n\r')
    
    if [ "$total_conn" -gt 0 ] 2>/dev/null; then
        print_ok "Total connections: $total_conn (Active: $active_conn, Idle: $idle_conn)"
        
        # Check if approaching max_connections (700)
        if [ "$total_conn" -gt 600 ] 2>/dev/null; then
            print_warning "Connection count approaching max_connections limit (700)"
        fi
    else
        print_info "Could not retrieve connection stats"
    fi
    
    # Check for slow queries
    print_subheader "Query Performance"
    
    local slow_queries=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND (now() - query_start) > interval '2 seconds';" 2>/dev/null || echo "0")
    
    slow_queries=$(echo "$slow_queries" | tr -d ' \n\r')
    
    if [ "$slow_queries" -eq 0 ] 2>/dev/null; then
        print_ok "Slow queries (>2s): 0"
    elif [ "$slow_queries" -lt 5 ] 2>/dev/null; then
        print_warning "Slow queries (>2s): $slow_queries"
    else
        print_error "Slow queries (>2s): $slow_queries - Performance bottleneck!"
    fi
    
    # Check for locks
    local locks=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT count(*) FROM pg_locks WHERE granted = false;" 2>/dev/null || echo "0")
    
    locks=$(echo "$locks" | tr -d ' \n\r')
    
    if [ "$locks" -eq 0 ] 2>/dev/null; then
        print_ok "Blocked queries: 0 (no locks)"
    else
        print_warning "Blocked queries: $locks (waiting for locks)"
    fi
    
    # Database size
    print_subheader "Database Size"
    
    local db_size=$(${DC} -f $COMPOSE_FILE exec -T db psql -U $DB_USER -d $DB_NAME -tAc \
        "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" 2>/dev/null | tr -d ' \n\r')
    
    if [ -n "$db_size" ]; then
        print_info "Database size: $db_size"
    fi
}

# ============================================================================
# 11. CELERY TASK QUEUE STATUS
# ============================================================================

check_celery_queue() {
    print_header "11. CELERY TASK QUEUE STATUS"
    
    print_subheader "Queue Health"
    
    # Check if celery worker is running
    local worker_running=$(${DC} -f $COMPOSE_FILE ps celery_worker 2>/dev/null | grep -i "up\\|running" || echo "")
    
    if [ -z "$worker_running" ]; then
        print_error "Celery worker: NOT RUNNING"
        return 1
    fi
    
    print_ok "Celery worker: Running"
    
    # Check active tasks (running now)
    print_subheader "Task Queue Status"
    
    # Try to get task count from Celery inspect
    local active_tasks=$(${DC} -f $COMPOSE_FILE exec -T celery_worker celery -A app.tasks.scheduler inspect active 2>/dev/null | grep -c "uuid" || echo "0")
    
    active_tasks=$(echo "$active_tasks" | tr -d ' \n\r')
    
    if [ "$active_tasks" -eq 0 ] 2>/dev/null; then
        print_ok "Active tasks: 0 (idle)"
    elif [ "$active_tasks" -lt 10 ] 2>/dev/null; then
        print_ok "Active tasks: $active_tasks (normal)"
    else
        print_warning "Active tasks: $active_tasks (high load)"
    fi
    
    # Check scheduled tasks (from celery beat)
    print_subheader "Scheduled Tasks"
    
    local beat_running=$(${DC} -f $COMPOSE_FILE ps celery_beat 2>/dev/null | grep -i "up\\|running" || echo "")
    
    if [ -n "$beat_running" ]; then
        print_ok "Celery beat: Running (scheduler active)"
    else
        print_warning "Celery beat: Not running (no scheduled tasks)"
    fi
    
    # Check Redis queue size (if tasks are backed up)
    print_subheader "Queue Backlog"
    
    # Check celery queue length in Redis
    local queue_size=$(${DC} -f $COMPOSE_FILE exec -T redis redis-cli llen celery 2>/dev/null | tr -d ' \n\r' || echo "0")
    
    if [ "$queue_size" -eq 0 ] 2>/dev/null; then
        print_ok "Queue size: 0 (no backlog)"
    elif [ "$queue_size" -lt 50 ] 2>/dev/null; then
        print_ok "Queue size: $queue_size (healthy)"
    elif [ "$queue_size" -lt 200 ] 2>/dev/null; then
        print_warning "Queue size: $queue_size (growing)"
    else
        print_error "Queue size: $queue_size - BOTTLENECK! Tasks backing up"
    fi
}

# ============================================================================
# SUMMARY REPORT
# ============================================================================

print_summary() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${WHITE}                        DIAGNOSTIC SUMMARY                              ${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
        echo -e "  ${GREEN}🎉 ALL SYSTEMS OPERATIONAL!${NC}"
        echo -e "  ${GREEN}   No errors or warnings detected.${NC}"
    else
        if [ $ERRORS -gt 0 ]; then
            echo -e "  ${RED}❌ ERRORS: $ERRORS${NC}"
        fi
        if [ $WARNINGS -gt 0 ]; then
            echo -e "  ${YELLOW}⚠️  WARNINGS: $WARNINGS${NC}"
        fi
        if [ $FIXES -gt 0 ]; then
            echo -e "  ${GREEN}🔧 AUTO-FIXES APPLIED: $FIXES${NC}"
        fi
    fi
    
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if [ $ERRORS -gt 0 ]; then
        echo -e "${WHITE}Recommended Actions:${NC}"
        echo -e "  1. Check API logs: ${CYAN}${DC} -f $COMPOSE_FILE logs --tail=100 api${NC}"
        echo -e "  2. Restart services: ${CYAN}${DC} -f $COMPOSE_FILE restart${NC}"
        echo -e "  3. Rebuild if needed: ${CYAN}${DC} -f $COMPOSE_FILE up -d --build${NC}"
        echo -e "  4. Run with auto-fix: ${CYAN}./deteksi_masalah.sh --fix${NC}"
    fi
    
    echo ""
    echo -e "${CYAN}Script completed at: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${WHITE}${BOLD}  DETEKSI MASALAH - Ujian Online Diagnostic Tool v1.0                   ${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}Started at:${NC} $(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "  ${CYAN}Server:${NC} $(hostname)"
    echo -e "  ${CYAN}Directory:${NC} $(pwd)"
    echo ""
    
    # Parse arguments
    QUICK_MODE=false
    AUTO_FIX=false
    
    for arg in "$@"; do
        case $arg in
            --quick)
                QUICK_MODE=true
                ;;
            --fix)
                AUTO_FIX=true
                echo -e "  ${GREEN}🔧 Auto-fix mode enabled${NC}"
                ;;
            --api)
                check_api
                exit 0
                ;;
            --db)
                check_database
                exit 0
                ;;
            --logs)
                check_logs
                exit 0
                ;;
            --performance)
                check_api_performance
                check_database_performance
                check_celery_queue
                exit 0
                ;;
            --help|-h)
                echo "Usage: ./deteksi_masalah.sh [options]"
                echo ""
                echo "Options:"
                echo "  --quick        Quick check (skip deep analysis)"
                echo "  --fix          Attempt automatic fixes"
                echo "  --api          API endpoints test only"
                echo "  --db           Database check only"
                echo "  --logs         Logs analysis only"
                echo "  --performance  Performance metrics only"
                echo "  --help         Show this help"
                exit 0
                ;;
        esac
    done
    
    # Run all checks
    check_containers
    check_database
    check_api
    check_logs
    
    if [ "$QUICK_MODE" != "true" ]; then
        check_code
        check_nginx
        check_redis
        check_system
        
        # Add performance monitoring (new sections)
        check_api_performance
        check_database_performance
        check_celery_queue
    fi
    
    # Print summary
    print_summary
    
    # Return error code if issues found
    if [ $ERRORS -gt 0 ]; then
        exit 1
    fi
    exit 0
}

# Run main
main "$@"
