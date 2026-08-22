# 🚀 Quick Sync Guide

Sync perubahan code dari Windows ke Ubuntu server dengan mudah!

## Cara Pakai

### Option 1: Double-Click (Termudah)
1. **Double-click** file `sync.bat`
2. Done! Script akan auto-detect WSL/Git Bash dan sync + restart server

### Option 2: Via WSL/Git Bash (Manual)
```bash
# Buka WSL atau Git Bash
cd "/mnt/c/Users/Administrator/Documents/UJIAN/Beta v2.2 jules/ujian_online"

# Jalankan script
./sync.sh
```

### Option 3: Via PowerShell (Advanced)
```powershell
# Buka PowerShell
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online"

# Run via WSL
wsl ./sync.sh
```

## Apa yang Di-Sync?

✅ **File yang di-sync:**
- Semua file `.py` (Python code)
- File `.js`, `.css`, `.html` (Frontend)
- File `.sql` (Migrations)
- File config (`docker-compose.yml`, `Dockerfile`, dll)

❌ **File yang TIDAK di-sync (auto-excluded):**
- `.env` (punya config berbeda di server)
- `uploads/` (file user uploads)
- `logs/` (log files)
- `__pycache__/`, `.git/` (cache & git history)

## Troubleshooting

### Error: "Permission denied"
```bash
# Di WSL/Git Bash, buat script executable:
chmod +x sync.sh
```

### Error: "Connection refused"
- Pastikan Ubuntu VM sedang running
- Cek SSH port forwarding di VirtualBox (Port 2222 → 22)
- Test connection: `ssh -p 2222 fahmi@127.0.0.1`

### Error: "rsync: command not found"
```bash
# Install rsync di Ubuntu:
sudo apt install rsync
```

## Workflow Development

1. **Edit code** di Windows (VS Code, dll)
2. **Save file** (`Ctrl+S`)
3. **Double-click `sync.bat`** untuk upload & restart
4. **Test** di browser (refresh cache: `Ctrl+Shift+F5`)
5. Repeat! 🔁

## Notes

- Sync hanya kirim **file yang berubah** (fast!)
- Auto-restart **Docker services** setelah sync
- **Safe** - tidak akan overwrite `.env`, `uploads`, `logs`
