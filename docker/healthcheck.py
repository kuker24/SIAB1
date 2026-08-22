#!/usr/bin/env python3
"""
Health Check Script for Docker Container
Verifies all critical services and dependencies
"""

import sys
import os
import psycopg2
import redis
from datetime import datetime

# Colors for output
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'

def check_database():
    """Check PostgreSQL connection"""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'db'),
            port=os.getenv('DB_PORT', '5432'),
            user=os.getenv('DB_USER', 'examuser'),
            password=os.getenv('DB_PASSWORD', 'postgres'),
            database=os.getenv('DB_NAME', 'siab1'),
            connect_timeout=5
        )
        conn.close()
        return True, "PostgreSQL connected"
    except Exception as e:
        return False, f"PostgreSQL error: {str(e)}"

def check_redis():
    """Check Redis connection"""
    try:
        r = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', '6379')),
            socket_connect_timeout=5
        )
        r.ping()
        return True, "Redis connected"
    except Exception as e:
        return False, f"Redis error: {str(e)}"

def check_disk_space():
    """Check disk space"""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free // (2**30)
        if free_gb < 1:
            return False, f"Low disk space: {free_gb}GB free"
        return True, f"Disk space OK: {free_gb}GB free"
    except Exception as e:
        return False, f"Disk check error: {str(e)}"

def main():
    """Run all health checks"""
    print(f"\n{YELLOW}Running health checks...{NC}\n")
    
    checks = [
        ("Database", check_database),
        ("Redis", check_redis),
        ("Disk Space", check_disk_space),
    ]
    
    all_passed = True
    results = []
    
    for name, check_func in checks:
        status, message = check_func()
        results.append((name, status, message))
        
        if status:
            print(f"{GREEN}✓{NC} {name}: {message}")
        else:
            print(f"{RED}✗{NC} {name}: {message}")
            all_passed = False
    
    print()
    
    if all_passed:
        print(f"{GREEN}All health checks passed!{NC}\n")
        sys.exit(0)
    else:
        print(f"{RED}Some health checks failed!{NC}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
