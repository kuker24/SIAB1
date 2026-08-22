# 🚀 Production Deployment Guide
## Sistem Ujian Online - Security Hardened

---

## 📋 Pre-Deployment Checklist

### 1. Generate Secure Keys

```bash
# Generate secure random keys (run these commands)
openssl rand -hex 32
```

Generate 5 keys untuk:
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `SEB_DEFAULT_CONFIG_KEY`
- `SEB_DEFAULT_BROWSER_EXAM_KEY`
- `DB_PASSWORD`

### 2. Required Environment Variables

Copy `.env.production` ke `.env` dan isi semua value:

```bash
cp .env.production .env
# Edit .env dengan editor favorit Anda
nano .env
```

### 3. Critical Security Settings

Pastikan semua ini sudah diatur:

```env
APP_ENV=production
DEBUG=false
FORCE_HTTPS=true
JWT_SECRET_KEY=<strong-random-key>
SEB_DEFAULT_CONFIG_KEY=<strong-random-key>
SEB_DEFAULT_BROWSER_EXAM_KEY=<strong-random-key>
```

---

## 🐳 Docker Deployment

### Step 1: Setup SSL/TLS Certificate

Gunakan Let's Encrypt untuk SSL gratis:

```bash
# Install certbot
sudo apt-get update
sudo apt-get install certbot

# Generate certificate
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# Copy certificates to project directory
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./docker/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./docker/ssl/
sudo chmod 644 ./docker/ssl/*.pem
```

### Step 2: Configure Nginx for HTTPS

```nginx
# docker/nginx.production.conf
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### Step 3: Deploy

```bash
# Pull latest code
git pull origin main

# Build and start services
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml build --no-cache
docker-compose -f docker-compose.production.yml up -d

# Check logs
docker-compose -f docker-compose.production.yml logs -f api
```

---

## 🔒 Security Verification

### Test Security Headers

```bash
curl -I https://your-domain.com
```

Expected headers:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Strict-Transport-Security: max-age=63072000`
- `Content-Security-Policy: default-src 'self'...`

### Test HTTPS Redirect

```bash
curl -I http://your-domain.com
# Should return 301 redirect to HTTPS
```

### SSL Labs Test

Buka: https://www.ssllabs.com/ssltest/

Target: **Grade A+**

---

## 📊 Post-Deployment Monitoring

### Check Application Health

```bash
# Health check
curl https://your-domain.com/health

# Check logs
docker-compose -f docker-compose.production.yml logs -f --tail=100
```

### Setup Log Rotation

```bash
# Install logrotate
sudo apt-get install logrotate

# Create config
cat << 'EOF' | sudo tee /etc/logrotate.d/ujian-online
/home/user/ujian-online/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 user user
}
EOF
```

### Setup Fail2ban (Optional)

```bash
# Install fail2ban
sudo apt-get install fail2ban

# Create custom filter
sudo tee /etc/fail2ban/filter.d/ujian-online.conf << 'EOF'
[Definition]
failregex = ^.*Invalid login attempt from <HOST>.*$
            ^.*APK_TOKEN_MISSING for user.*from <HOST>.*$
ignoreregex =
EOF

# Enable jail
sudo tee -a /etc/fail2ban/jail.local << 'EOF'
[ujian-online]
enabled = true
port = http,https
filter = ujian-online
logpath = /home/user/ujian-online/logs/security.log
maxretry = 5
bantime = 3600
EOF

sudo systemctl restart fail2ban
```

---

## 🚨 Security Incident Response

### If You Suspect a Breach

1. **Immediately**:
   ```bash
   # Stop the application
   docker-compose -f docker-compose.production.yml down
   ```

2. **Rotate all secrets**:
   ```bash
   # Generate new keys
   openssl rand -hex 32

   # Update .env file
   nano .env

   # Restart application
   docker-compose -f docker-compose.production.yml up -d
   ```

3. **Check logs for suspicious activity**:
   ```bash
   grep -i "failed\|error\|unauthorized" logs/security.log
   ```

4. **Notify users** if PII (Personally Identifiable Information) was compromised

---

## 🔄 Regular Maintenance

### Weekly Tasks

- [ ] Check logs for errors
- [ ] Review failed login attempts
- [ ] Monitor disk space
- [ ] Check SSL certificate expiry

### Monthly Tasks

- [ ] Update Docker images
- [ ] Review and rotate secrets if needed
- [ ] Security scan with OWASP ZAP
- [ ] Backup verification

### Quarterly Tasks

- [ ] Full security audit
- [ ] Penetration testing
- [ ] Update dependencies
- [ ] Review access logs

---

## 📞 Support & Troubleshooting

### Common Issues

**Application won't start**:
```bash
# Check environment variables
docker-compose -f docker-compose.production.yml config

# Check database connection
docker-compose -f docker-compose.production.yml exec db pg_isready -U examuser
```

**High memory usage**:
```bash
# Check memory usage
docker stats

# Restart services
docker-compose -f docker-compose.production.yml restart api
```

**SSL certificate expired**:
```bash
# Renew certificate
sudo certbot renew

# Copy new certificates
sudo cp /etc/letsencrypt/live/your-domain.com/*.pem ./docker/ssl/
docker-compose -f docker-compose.production.yml restart nginx
```

---

**Last Updated**: February 2026
**Security Version**: 2.0
**Compatible with**: Sistem Ujian Online v1.0.0+
