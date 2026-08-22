Semua File didalam Folder : ujian_online :

└── ujian_online
    ├── apk_builder_gui.py
    ├── apk_builds
    │   └── ujian_online_seb_20260118_163334.apk
    ├── app
    │   ├── api
    │   ├── config.py
    │   ├── core
    │   ├── database.py
    │   ├── __init__.py
    │   ├── locales
    │   ├── logging_config.py
    │   ├── main.py
    │   ├── middleware
    │   ├── models
    │   ├── schemas
    │   ├── tasks
    │   └── utils
    ├── backup-comprehensive.sh
    ├── backup-database.sh
    ├── build_apk_automated.py
    ├── build-flutter.sh
    ├── cache-maintenance.sh
    ├── cleanup.ps1
    ├── config
    │   └── security.py
    ├── DEPLOYMENT_GUIDE.md
    ├── deploy.sh
    ├── deteksi_masalah.sh
    ├── docker-compose.production.yml
    ├── docker-entrypoint.sh
    ├── Dockerfile.flutter
    ├── Dockerfile.production
    ├── env-config.txt
    ├── env-example.txt
    ├── FILE_TRANSFER_GUIDE.md
    ├── flutter_client_code
    │   ├── analysis_options.yaml
    │   ├── android
    │   ├── android_src
    │   ├── build
    │   ├── build_error.log
    │   ├── flutter_client_code.iml
    │   ├── lib
    │   ├── pubspec.lock
    │   ├── pubspec.yaml
    │   ├── README.md
    │   ├── sxb_dependencies.yaml
    │   ├── test
    │   └── windows_src
    ├── generate-docker-compose.sh
    ├── healthcheck.py
    ├── health-monitor.sh
    ├── init.sql
    ├── logs
    ├── monitor.sh
    ├── nginx.production.conf
    ├── README_SYNC.md
    ├── rebuild.sh
    ├── recovery_sistem
    │   └── README.md
    ├── requirements-dev.txt
    ├── requirements-gui.txt
    ├── requirements-test.txt
    ├── requirements.txt
    ├── restore.sh
    ├── run_apk_builder_gui.bat
    ├── scripts
    │   ├── build_apk.py
    │   ├── check_security.py
    │   ├── generate_full_documentation.py
    │   ├── init_seb_presets.py
    │   └── system_check.py
    ├── seb_configs
    ├── self-healing.sh
    ├── setup-ssh-key.sh
    ├── static
    │   ├── apk
    │   ├── components
    │   ├── css
    │   ├── favicon.gif
    │   ├── js
    │   ├── seb
    │   ├── sw.js
    │   └── uploads
    ├── sync.bat
    ├── sync-nopass.sh
    ├── sync.ps1
    ├── sync.sh
    ├── telegram-notify.sh
    ├── templates
    │   ├── admin
    │   ├── base.html
    │   ├── components
    │   ├── exam
    │   ├── seb
    │   ├── student
    │   └── test_modals.html
    ├── tests
    │   ├── conftest.py
    │   ├── test_api_endpoints.py
    │   ├── test_api.py
    │   ├── test_auth.py
    │   ├── test_exams.py
    │   ├── test_exam_submission.py
    │   ├── test_grading.py
    │   └── test_models.py
    ├── tools
    │   └── apk_builder_gui
    ├── undeploy.sh
    └── uploads

41 directories, 71 files

pindahkan/Transfer Ke docker/server linux ubuntu lalu lakukan configurai seperti ini ( intinya saya pakai docker)


Deploy :

 Step 1: Make scripts executable
chmod +x *.sh

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



Rebuild :
# Make executable
chmod +x rebuild.sh

# Run rebuild script
./rebuild.sh


Clean Everything :
# Using undeploy script
chmod +x undeploy.sh
./undeploy.sh

# Manual cleanup jika masih ada
docker system prune -a --volumes -f
