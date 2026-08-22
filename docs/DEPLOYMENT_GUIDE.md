# 🚀 Panduan Deployment Ujian Online
## Perintah-Perintah Deployment Terstruktur

---

## 📋 Quick Navigation

- [1. First Time Deploy (Fresh Install)](#1-first-time-deploy-fresh-install)
- [2. Normal Restart (Tanpa Rebuild)](#2-normal-restart-tanpa-rebuild)
- [3. Update & Rebuild (Ada Perubahan Code)](#3-update--rebuild-ada-perubahan-code)
- [4. Full Rebuild (Reset Everything)](#4-full-rebuild-reset-everything)
- [5. Undeploy (Hapus Semua)](#5-undeploy-hapus-semua)
- [6. Maintenance Commands](#6-maintenance-commands)

---

## 1. First Time Deploy (Fresh Install)

**Kapan:** Pertama kali install di server baru

```bash
cd ~/ujian_online

# Step 1: Make scripts executable
chmod +x *.sh

# Step 2: Setup environment template
mv env-example.txt .env.example

# Step 3: Clean old files (jika ada)
rm -f .env env-config.txt

# Step 4: Deploy (auto-generate secure keys)
./deploy.sh
```

**Script akan:**
- ✅ Generate secure keys otomatis
- ✅ Create Docker images
- ✅ Setup database
- ✅ Start semua services

**Verifikasi:**
```bash
# Check semua service running
docker compose -f docker-compose.production.yml ps

# Check logs
docker compose -f docker-compose.production.yml logs -f api
```

---

## 2. Normal Restart (Tanpa Rebuild)

**Kapan:** 
- Server restart
- Container crash
- Tidak ada perubahan code

```bash
cd ~/ujian_online

# Stop containers
docker compose -f docker-compose.production.yml stop

# Start containers
docker compose -f docker-compose.production.yml up -d
```

**Atau pakai:**
```bash
cd ~/ujian_online

# Restart semua service
docker compose -f docker-compose.production.yml restart
```

---

## 3. Update & Rebuild (Ada Perubahan Code)

**Kapan:**
- Ada update code dari Windows
- Perubahan di Python files
- Perubahan di dependencies

### Option A: Rebuild Specific Service (Recommended)

```bash
cd ~/ujian_online

# Stop services
docker compose -f docker-compose.production.yml down

# Rebuild ONLY API & workers (faster)
docker compose -f docker-compose.production.yml build --no-cache api celery_worker celery_beat

# Start all services
docker compose -f docker-compose.production.yml up -d

# Monitor logs
docker compose -f docker-compose.production.yml logs -f api
```

### Option B: Rebuild All (Slower but Complete)

```bash
cd ~/ujian_online

# Stop and remove containers (keep data)
docker compose -f docker-compose.production.yml down

# Rebuild all with no cache
docker compose -f docker-compose.production.yml build --no-cache

# Start
docker compose -f docker-compose.production.yml up -d
```

---

## 4. Full Rebuild (Reset Everything)

**Kapan:**
- Ganti environment variables
- Database corrupted
- Fresh start needed
- Testing deployment

### Option A: Using rebuild.sh (Automated)

```bash
cd ~/ujian_online

# Make executable
chmod +x rebuild.sh

# Run rebuild script
./rebuild.sh
```

### Option B: Manual Full Reset

```bash
cd ~/ujian_online

# Step 1: Stop dan hapus SEMUA (termasuk volume/data)
docker compose -f docker-compose.production.yml down -v

# Step 2: Hapus .env lama
rm -f .env

# Step 3: Generate .env.example jika belum ada
cat > .env.example << 'EOF'
APP_NAME="Ujian Online"
APP_ENV=production
DEBUG=false
SECRET_KEY=your-super-secret-key-change-in-production
DATABASE_URL=postgresql+asyncpg://examuser:REPLACE_DB_PASSWORD@db:5432/exam_system
DB_PASSWORD=REPLACE_DB_PASSWORD
POSTGRES_PASSWORD=REPLACE_DB_PASSWORD
REDIS_URL=redis://redis:6379/0
REDIS_HOST=redis
JWT_SECRET_KEY=your-jwt-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
SEB_DEFAULT_CONFIG_KEY=default-seb-config-key
SEB_DEFAULT_BROWSER_EXAM_KEY=default-browser-exam-key
SEB_STRICT_MODE=false
SEB_CHALLENGE_ENABLED=true
HOST=0.0.0.0
PORT=8000
WORKERS=4
TZ=Asia/Jakarta
CORS_ORIGINS=*
APP_SECRET_KEY=your-super-secret-app-key-min-32-chars
ENFORCE_SXB=false
DOMAIN=your-server-ip:8080
PROTOCOL=http
RAM_PROFILE=8
EOF

# Step 4: Deploy fresh
./deploy.sh
```

**⚠️ WARNING:** Command ini akan **HAPUS SEMUA DATA** (database, uploads, dll)

---

## 5. Undeploy (Hapus Semua)

### Option A: Stop & Remove (Keep Images)

```bash
cd ~/ujian_online

# Stop dan remove containers + volumes
docker compose -f docker-compose.production.yml down -v
```

### Option B: Complete Cleanup (Remove Everything)

```bash
cd ~/ujian_online

# Stop dan remove containers + volumes
docker compose -f docker-compose.production.yml down -v

# Hapus images
docker rmi ujian_online-api ujian_online-celery_worker ujian_online-celery_beat

# Hapus unused images
docker image prune -f

# Optional: Hapus file .env
rm -f .env
```

### Option C: Nuclear Option (Clean Everything)

```bash
cd ~/ujian_online

# Using undeploy script
chmod +x undeploy.sh
./undeploy.sh

# Manual cleanup jika masih ada
docker system prune -a --volumes -f
```

**⚠️ WARNING:** Ini akan hapus SEMUA Docker resources!

---

## 6. Maintenance Commands

### Check Status

```bash
# List semua container
docker compose -f docker-compose.production.yml ps

# Check resource usage
docker stats

# Check disk usage
docker system df
```

### View Logs

```bash
# All services
docker compose -f docker-compose.production.yml logs -f

# Specific service
docker compose -f docker-compose.production.yml logs -f api
docker compose -f docker-compose.production.yml logs -f db
docker compose -f docker-compose.production.yml logs -f nginx

# Last 100 lines
docker compose -f docker-compose.production.yml logs --tail=100 api
```

### Database Operations

```bash
# Backup database
./backup-database.sh

# Access PostgreSQL
docker compose -f docker-compose.production.yml exec db psql -U examuser -d exam_system

# View database size
docker compose -f docker-compose.production.yml exec db psql -U examuser -d exam_system -c "SELECT pg_size_pretty(pg_database_size('exam_system'));"
```

### Redis Operations

```bash
# Access Redis CLI
docker compose -f docker-compose.production.yml exec redis redis-cli

# Check Redis memory
docker compose -f docker-compose.production.yml exec redis redis-cli INFO memory

# Flush Redis cache (be careful!)
docker compose -f docker-compose.production.yml exec redis redis-cli FLUSHALL
```

### Container Operations

```bash
# Restart specific service
docker compose -f docker-compose.production.yml restart api

# Scale workers (if needed)
docker compose -f docker-compose.production.yml up -d --scale celery_worker=3

# Execute command in container
docker compose -f docker-compose.production.yml exec api python -m app.main
```

---

## 🎯 Quick Reference Table

| Scenario | Command | Data Loss? |
|----------|---------|------------|
| Server restart | `docker compose -f docker-compose.production.yml restart` | ❌ No |
| Code update | `docker compose -f docker-compose.production.yml down && build --no-cache && up -d` | ❌ No |
| Change .env | `./rebuild.sh` or `down -v && deploy.sh` | ✅ Yes |
| Fresh install | `./deploy.sh` | N/A |
| Remove all | `./undeploy.sh` or `down -v` | ✅ Yes |

---

## 📝 Best Practices

### Before Deployment
1. ✅ Backup database: `./backup-database.sh`
2. ✅ Test di development dulu
3. ✅ Check disk space: `df -h`
4. ✅ Review changes di code

### After Deployment
1. ✅ Check logs: `docker compose logs -f api`
2. ✅ Test login ke admin panel
3. ✅ Verify database connection
4. ✅ Monitor resource usage: `docker stats`

### Troubleshooting
```bash
# API tidak start
docker compose -f docker-compose.production.yml logs api

# Database connection error
docker compose -f docker-compose.production.yml exec db pg_isready -U examuser

# Nginx 502 error
docker compose -f docker-compose.production.yml logs nginx
docker compose -f docker-compose.production.yml restart nginx

# Port already in use
sudo lsof -i :8080
sudo kill -9 <PID>
```

---

## 🚨 Emergency Commands

### Container keeps crashing
```bash
# Force remove
docker compose -f docker-compose.production.yml rm -f -s -v api

# Rebuild and start
docker compose -f docker-compose.production.yml up -d --build api
```

### Database corrupted
```bash
# Stop all
docker compose -f docker-compose.production.yml down

# Remove volume
docker volume rm ujian_online_postgres_data

# Fresh start
./deploy.sh
```

### Out of disk space
```bash
# Clean unused data
docker system prune -a -f

# Remove old logs
docker compose -f docker-compose.production.yml exec api sh -c "rm -rf /app/logs/*.log.old"

# Clear Redis cache
docker compose -f docker-compose.production.yml exec redis redis-cli FLUSHALL
```

---

## 📞 Support

Jika ada masalah:
1. Check logs terlebih dahulu
2. Restart service yang bermasalah
3. Jika masih error, lakukan full rebuild
4. Last resort: undeploy dan deploy ulang

**File Penting:**
- Deployment: `deploy.sh`
- Rebuild: `rebuild.sh`
- Undeploy: `undeploy.sh`
- Backup: `backup-database.sh`
- Config: `docker-compose.production.yml`
