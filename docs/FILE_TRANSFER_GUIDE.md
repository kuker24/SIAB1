# 📁 File Transfer Guide (Windows → Ubuntu VM)
## SCP Commands untuk Transfer Project

---

## ⚠️ Masalah Umum dengan SCP

**Command asli yang bermasalah:**
```bash
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\*" fahmi@127.0.0.1:~/ujian_online/
```

**Kenapa gagal:**
- ❌ Wildcard `*` di dalam quotes tidak expand
- ❌ Spasi di path ("Beta v2.2 jules") 
- ❌ Beberapa file/folder mungkin tertinggal

---

## ✅ Solusi: Transfer yang Benar

### Method 1: Transfer Folder Lengkap (Recommended)

**Dari PowerShell/CMD Windows:**

```powershell
# Hapus folder tujuan dulu (di Ubuntu VM)
ssh -p 2222 fahmi@127.0.0.1 "rm -rf ~/ujian_online/*"

# Transfer TANPA wildcard (akan copy semua isi folder)
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online" fahmi@127.0.0.1:~/

# Atau langsung copy isi folder ke dalam ujian_online
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules"
scp -P 2222 -r ujian_online/* fahmi@127.0.0.1:~/ujian_online/
```

### Method 2: Using rsync (More Reliable)

**Install rsync di Windows:**
1. Install Git for Windows (sudah include rsync)
2. Atau install via WSL

**Command:**
```bash
# Via Git Bash atau WSL
rsync -avz -e "ssh -p 2222" \
  "/c/Users/Administrator/Documents/UJIAN/Beta v2.2 jules/ujian_online/" \
  fahmi@127.0.0.1:~/ujian_online/

# Dengan progress bar
rsync -avz --progress -e "ssh -p 2222" \
  "/c/Users/Administrator/Documents/UJIAN/Beta v2.2 jules/ujian_online/" \
  fahmi@127.0.0.1:~/ujian_online/
```

### Method 3: Batch Script (Windows - Paling Mudah)

**Buat file:** `sync-to-vm.bat`

```batch
@echo off
echo ===================================
echo Transfer Files to Ubuntu VM
echo ===================================

set SOURCE=C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online
set DEST=fahmi@127.0.0.1:~/ujian_online/
set PORT=2222

echo.
echo Source: %SOURCE%
echo Destination: %DEST%
echo Port: %PORT%
echo.

REM Clean destination first
echo [1/3] Cleaning destination folder...
ssh -p %PORT% fahmi@127.0.0.1 "rm -rf ~/ujian_online/*"

REM Create directory
echo [2/3] Creating directory...
ssh -p %PORT% fahmi@127.0.0.1 "mkdir -p ~/ujian_online"

REM Transfer files
echo [3/3] Transferring files...
scp -P %PORT% -r "%SOURCE%\*" %DEST%

echo.
echo ✅ Transfer complete!
echo.
pause
```

**Cara pakai:**
```bash
# Double click file sync-to-vm.bat
# Atau jalankan dari CMD
sync-to-vm.bat
```

---

## 🎯 Transfer File Spesifik

### Transfer .py files only
```powershell
# Via PowerShell
Get-ChildItem -Path "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online" -Recurse -Filter "*.py" | ForEach-Object {
    $relativePath = $_.FullName.Replace("C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\", "").Replace("\", "/")
    $remoteDir = Split-Path -Parent $relativePath
    ssh -p 2222 fahmi@127.0.0.1 "mkdir -p ~/ujian_online/$remoteDir"
    scp -P 2222 $_.FullName "fahmi@127.0.0.1:~/ujian_online/$relativePath"
}
```

### Transfer folder tertentu saja
```bash
# App folder only
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\app" fahmi@127.0.0.1:~/ujian_online/

# Static folder only
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\static" fahmi@127.0.0.1:~/ujian_online/

# Templates folder only
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\templates" fahmi@127.0.0.1:~/ujian_online/
```

---

## 🔍 Verifikasi Transfer

**Check di Ubuntu VM:**

```bash
# SSH ke VM
ssh -p 2222 fahmi@127.0.0.1

# List semua file yang ter-transfer
cd ~/ujian_online
find . -type f | wc -l   # Hitung jumlah file

# Check folder struktur
tree -L 2                # Atau ls -R jika tree tidak ada

# Check size
du -sh ~/ujian_online
```

---

## 📝 PowerShell Script Lengkap

**Buat file:** `Sync-ToVM.ps1`

```powershell
# PowerShell Script untuk Sync Files ke Ubuntu VM
param(
    [string]$Source = "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online",
    [string]$Host = "fahmi@127.0.0.1",
    [int]$Port = 2222,
    [string]$Destination = "~/ujian_online"
)

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  File Sync to Ubuntu VM" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Source:      $Source" -ForegroundColor Yellow
Write-Host "Destination: $Host`:$Destination" -ForegroundColor Yellow
Write-Host "Port:        $Port" -ForegroundColor Yellow
Write-Host ""

# Step 1: Clean destination
Write-Host "[1/4] Cleaning destination..." -ForegroundColor Green
ssh -p $Port $Host "rm -rf $Destination/* 2>/dev/null; mkdir -p $Destination"

# Step 2: Count files
Write-Host "[2/4] Counting files..." -ForegroundColor Green
$fileCount = (Get-ChildItem -Path $Source -Recurse -File | Measure-Object).Count
Write-Host "Total files to transfer: $fileCount" -ForegroundColor White

# Step 3: Transfer
Write-Host "[3/4] Transferring files..." -ForegroundColor Green
scp -P $Port -r "$Source\*" "$Host`:$Destination/"

# Step 4: Verify
Write-Host "[4/4] Verifying transfer..." -ForegroundColor Green
$remoteCount = ssh -p $Port $Host "find $Destination -type f | wc -l"
Write-Host "Files transferred: $remoteCount" -ForegroundColor White

if ($fileCount -eq $remoteCount) {
    Write-Host ""
    Write-Host "✅ Transfer successful!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "⚠️  Warning: File count mismatch!" -ForegroundColor Yellow
    Write-Host "   Local: $fileCount | Remote: $remoteCount" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"
```

**Cara pakai:**
```powershell
# Jalankan dari PowerShell
.\Sync-ToVM.ps1

# Atau dengan custom parameters
.\Sync-ToVM.ps1 -Port 2222 -Host "fahmi@127.0.0.1"
```

---

## 🚀 One-Liner untuk Update Cepat

**Update app folder saja (paling sering):**
```powershell
scp -P 2222 -r "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online\app" fahmi@127.0.0.1:~/ujian_online/
```

**Update semua Python files:**
```bash
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online"
for /R %f in (*.py) do @scp -P 2222 "%f" fahmi@127.0.0.1:~/ujian_online/
```

---

## 🛠️ Troubleshooting

### "Permission denied"
```bash
# Pastikan SSH key sudah ter-setup
ssh-copy-id -p 2222 fahmi@127.0.0.1

# Atau check permission di server
ssh -p 2222 fahmi@127.0.0.1 "ls -la ~/ujian_online"
```

### "Connection refused"
```bash
# Check SSH service di VM
ssh -p 2222 fahmi@127.0.0.1 "sudo systemctl status ssh"

# Check port forwarding VirtualBox
# Setting → Network → Port Forwarding → Host Port 2222 → Guest Port 22
```

### "Some files missing"
```bash
# Check apa yang tidak ter-copy
# Di Windows
dir /s /b "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online" > local-files.txt

# Di Ubuntu
ssh -p 2222 fahmi@127.0.0.1 "find ~/ujian_online -type f" > remote-files.txt

# Compare
fc local-files.txt remote-files.txt
```

### File tertinggal di subfolder
```powershell
# Gunakan robocopy (Windows built-in, lebih reliable)
# Install SSH client di VM dulu, lalu:

# Transfer via Shared Folder VirtualBox
# 1. Set shared folder di VirtualBox
# 2. Mount di Ubuntu
# 3. Copy langsung

# Atau gunakan WinSCP GUI (easier)
# Download: https://winscp.net/
```

---

## 💡 Rekomendasi

**Untuk development sehari-hari:**
1. ✅ **VSCode Remote SSH** - Edit langsung di VM
2. ✅ **Git** - Push/pull dari Windows ke VM
3. ✅ **WinSCP** - GUI untuk file transfer
4. ✅ **Batch script** - Otomatis transfer on save

**Untuk production deployment:**
1. ✅ **Git clone** langsung di server
2. ✅ **CI/CD** - Auto deploy on push
3. ✅ **rsync** - Incremental sync

---

## 📦 Alternative: Using Git

**Paling recommended untuk project code:**

```bash
# Di Windows
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules\ujian_online"
git add .
git commit -m "Update code"
git push origin main

# Di Ubuntu VM
ssh -p 2222 fahmi@127.0.0.1
cd ~/ujian_online
git pull origin main
```

**Advantages:**
- ✅ Track changes
- ✅ No file missing
- ✅ Faster (only diff)
- ✅ Rollback capability

---

## 🎯 Quick Copy-Paste Solutions

### Solution 1: Clean Transfer (Most Reliable)
```bash
# Step 1: Clean
ssh -p 2222 fahmi@127.0.0.1 "rm -rf ~/ujian_online && mkdir -p ~/ujian_online"

# Step 2: Transfer (NO wildcard inside quotes!)
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules"
scp -P 2222 -r ujian_online fahmi@127.0.0.1:~/
```

### Solution 2: Incremental Update
```bash
# Using rsync via Git Bash
cd "/c/Users/Administrator/Documents/UJIAN/Beta v2.2 jules"
rsync -avz --delete -e "ssh -p 2222" ujian_online/ fahmi@127.0.0.1:~/ujian_online/
```

### Solution 3: Manual Verification
```bash
# Transfer
cd "C:\Users\Administrator\Documents\UJIAN\Beta v2.2 jules"
scp -P 2222 -r ujian_online fahmi@127.0.0.1:~/

# Verify
ssh -p 2222 fahmi@127.0.0.1 "cd ~/ujian_online && find . -type f | wc -l"
```

---

**Pilih method yang paling cocok dengan workflow Anda!** 🚀
