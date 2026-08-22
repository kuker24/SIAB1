#!/usr/bin/env python3
"""
Flutter SDK Auto-Setup Module
Automatically downloads and configures Flutter SDK for Windows

Usage:
    from flutter_setup import FlutterSetup
    setup = FlutterSetup(log_callback=print)
    setup.ensure_flutter_ready()
"""

import os
import sys
import subprocess
import urllib.request
import zipfile
import shutil
import winreg
from pathlib import Path
from typing import Callable, Optional


class FlutterSetup:
    """Manages Flutter SDK installation and configuration"""
    
    # URLs for SDK downloads
    FLUTTER_URL = "https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.16.5-stable.zip"
    ANDROID_CMDLINE_URL = "https://dl.google.com/android/repository/commandlinetools-win-9477386_latest.zip"
    
    # Installation paths
    DEFAULT_INSTALL_DIR = Path.home() / "AppData" / "Local" / "FlutterSDK"
    
    def __init__(self, 
                 install_dir: Optional[Path] = None,
                 log_callback: Callable[[str], None] = print,
                 progress_callback: Callable[[int], None] = lambda x: None):
        """
        Initialize Flutter Setup
        
        Args:
            install_dir: Custom installation directory
            log_callback: Function to call for log messages
            progress_callback: Function to call for progress updates (0-100)
        """
        self.install_dir = install_dir or self.DEFAULT_INSTALL_DIR
        self.log = log_callback
        self.progress = progress_callback
        
        self.flutter_path = self.install_dir / "flutter"
        self.android_sdk_path = self.install_dir / "android-sdk"
    
    def is_flutter_installed(self) -> bool:
        """Check if Flutter is available in PATH or local installation"""
        # Check PATH
        try:
            result = subprocess.run(
                ["flutter", "--version"],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Check local installation
        flutter_bin = self.flutter_path / "bin" / "flutter.bat"
        return flutter_bin.exists()
    
    def get_flutter_path(self) -> Optional[str]:
        """Get Flutter executable path - prioritizes local installation"""
        # Check local installation FIRST (more reliable)
        flutter_bin = self.flutter_path / "bin" / "flutter.bat"
        if flutter_bin.exists():
            return str(flutter_bin)
        
        # Also check flutter (without .bat) for compatibility
        flutter_bin_no_ext = self.flutter_path / "bin" / "flutter"
        if flutter_bin_no_ext.exists():
            return str(flutter_bin_no_ext)
        
        # Check system PATH - actually verify it works
        try:
            result = subprocess.run(
                ["flutter", "--version"],
                capture_output=True,
                text=True,
                timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode == 0:
                # Find actual path using 'where' command
                if os.name == 'nt':
                    where_cmd = ["where", "flutter"]
                else:
                    where_cmd = ["which", "flutter"]
                    
                where_result = subprocess.run(
                    where_cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if where_result.returncode == 0 and where_result.stdout.strip():
                    # Return the first path found
                    return where_result.stdout.strip().split('\n')[0].strip()
                return "flutter"  # Fallback to command name
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        
        return None
    
    def ensure_flutter_ready(self) -> bool:
        """
        Ensure Flutter is ready to use.
        Downloads and installs if not available.
        
        Returns:
            True if Flutter is ready
        """
        if self.is_flutter_installed():
            self.log("✅ Flutter SDK sudah terinstall")
            return True
        
        self.log("📥 Flutter SDK tidak ditemukan. Memulai download otomatis...")
        
        try:
            # Step 1: Create install directory
            self.install_dir.mkdir(parents=True, exist_ok=True)
            self.progress(5)
            
            # Step 2: Download Flutter SDK
            if not self._download_flutter():
                return False
            
            # Step 3: Download Android command-line tools
            if not self._download_android_tools():
                return False
            
            # Step 4: Setup Android SDK
            if not self._setup_android_sdk():
                return False
            
            # Step 5: Configure environment
            if not self._configure_environment():
                return False
            
            # Step 6: Run flutter doctor
            self._run_flutter_doctor()
            
            self.progress(100)
            self.log("✅ Flutter SDK berhasil diinstall!")
            return True
            
        except Exception as e:
            self.log(f"❌ Error: {str(e)}")
            return False
    
    def _download_with_progress(self, url: str, dest_path: Path, description: str) -> bool:
        """Download file with progress updates"""
        try:
            self.log(f"⬇️ Downloading {description}...")
            
            # Get file size
            req = urllib.request.urlopen(url, timeout=30)
            total_size = int(req.headers.get('Content-Length', 0))
            
            # Download with progress
            downloaded = 0
            block_size = 8192 * 16  # 128KB blocks
            
            with open(dest_path, 'wb') as f:
                while True:
                    buffer = req.read(block_size)
                    if not buffer:
                        break
                    
                    f.write(buffer)
                    downloaded += len(buffer)
                    
                    if total_size > 0:
                        percent = int(downloaded * 100 / total_size)
                        size_mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        self.log(f"   {size_mb:.1f} / {total_mb:.1f} MB ({percent}%)")
            
            self.log(f"✅ Download {description} selesai")
            return True
            
        except Exception as e:
            self.log(f"❌ Download gagal: {e}")
            return False
    
    def _download_flutter(self) -> bool:
        """Download Flutter SDK"""
        self.progress(10)
        
        flutter_zip = self.install_dir / "flutter.zip"
        
        # Download if not exists
        if not flutter_zip.exists():
            if not self._download_with_progress(
                self.FLUTTER_URL,
                flutter_zip,
                "Flutter SDK (~1GB)"
            ):
                return False
        
        self.progress(40)
        
        # Extract
        self.log("📦 Extracting Flutter SDK...")
        try:
            with zipfile.ZipFile(flutter_zip, 'r') as zip_ref:
                zip_ref.extractall(self.install_dir)
            
            self.log("✅ Flutter SDK extracted")
            
            # Clean up zip
            flutter_zip.unlink()
            
        except Exception as e:
            self.log(f"❌ Extract gagal: {e}")
            return False
        
        self.progress(50)
        return True
    
    def _download_android_tools(self) -> bool:
        """Download Android command-line tools"""
        self.progress(55)
        
        android_zip = self.install_dir / "cmdline-tools.zip"
        
        # Download if not exists
        if not android_zip.exists():
            if not self._download_with_progress(
                self.ANDROID_CMDLINE_URL,
                android_zip,
                "Android Command-line Tools (~100MB)"
            ):
                return False
        
        self.progress(65)
        
        # Extract
        self.log("📦 Extracting Android tools...")
        try:
            self.android_sdk_path.mkdir(parents=True, exist_ok=True)
            cmdline_path = self.android_sdk_path / "cmdline-tools"
            cmdline_path.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(android_zip, 'r') as zip_ref:
                zip_ref.extractall(cmdline_path)
            
            # Rename to 'latest' as expected by sdkmanager
            extracted = cmdline_path / "cmdline-tools"
            latest_path = cmdline_path / "latest"
            
            if extracted.exists():
                if latest_path.exists():
                    shutil.rmtree(latest_path)
                extracted.rename(latest_path)
            
            self.log("✅ Android tools extracted")
            
            # Clean up zip
            android_zip.unlink()
            
        except Exception as e:
            self.log(f"❌ Extract gagal: {e}")
            return False
        
        self.progress(70)
        return True
    
    def _setup_android_sdk(self) -> bool:
        """Setup Android SDK with sdkmanager"""
        self.progress(75)
        
        sdkmanager = self.android_sdk_path / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
        
        if not sdkmanager.exists():
            self.log("⚠️ sdkmanager tidak ditemukan, skip Android SDK setup")
            return True  # Continue without Android SDK
        
        self.log("📦 Installing Android SDK components...")
        self.log("   (Ini akan accept licenses otomatis)")
        
        try:
            # Set ANDROID_SDK_ROOT environment for this process
            env = os.environ.copy()
            env["ANDROID_SDK_ROOT"] = str(self.android_sdk_path)
            env["ANDROID_HOME"] = str(self.android_sdk_path)
            
            # Accept licenses
            self.log("   Accepting licenses...")
            subprocess.run(
                [str(sdkmanager), "--licenses"],
                input="y\n" * 10,  # Accept all
                capture_output=True,
                text=True,
                env=env,
                timeout=120
            )
            
            # Install required packages
            packages = [
                "platform-tools",
                "platforms;android-33",
                "build-tools;33.0.0"
            ]
            
            for pkg in packages:
                self.log(f"   Installing {pkg}...")
                subprocess.run(
                    [str(sdkmanager), pkg],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=300
                )
            
            self.log("✅ Android SDK components installed")
            
        except subprocess.TimeoutExpired:
            self.log("⚠️ Timeout installing Android SDK, akan coba lagi nanti")
        except Exception as e:
            self.log(f"⚠️ Android SDK setup warning: {e}")
        
        self.progress(85)
        return True
    
    def _configure_environment(self) -> bool:
        """Configure environment variables"""
        self.progress(90)
        self.log("⚙️ Configuring environment...")
        
        flutter_bin = self.flutter_path / "bin"
        android_tools = self.android_sdk_path / "cmdline-tools" / "latest" / "bin"
        android_platform_tools = self.android_sdk_path / "platform-tools"
        
        paths_to_add = [
            str(flutter_bin),
            str(android_tools),
            str(android_platform_tools)
        ]
        
        # Add to current process PATH
        current_path = os.environ.get("PATH", "")
        for p in paths_to_add:
            if p not in current_path:
                os.environ["PATH"] = p + os.pathsep + current_path
        
        # Set ANDROID environment variables
        os.environ["ANDROID_SDK_ROOT"] = str(self.android_sdk_path)
        os.environ["ANDROID_HOME"] = str(self.android_sdk_path)
        
        # Try to add to system PATH permanently (for current user)
        try:
            self._add_to_user_path(paths_to_add)
            self.log("✅ PATH updated untuk user saat ini")
        except Exception as e:
            self.log(f"⚠️ Tidak bisa update PATH permanen: {e}")
            self.log("   Anda mungkin perlu restart aplikasi")
        
        self.progress(95)
        return True
    
    def _add_to_user_path(self, paths: list):
        """Add paths to user PATH environment variable (Windows)"""
        if sys.platform != "win32":
            return
        
        try:
            # Open user environment variables
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_ALL_ACCESS
            )
            
            # Get current PATH
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
            
            # Add new paths
            new_paths = []
            for p in paths:
                if p not in current_path:
                    new_paths.append(p)
            
            if new_paths:
                if current_path:
                    updated_path = ";".join(new_paths) + ";" + current_path
                else:
                    updated_path = ";".join(new_paths)
                
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, updated_path)
            
            winreg.CloseKey(key)
            
            # Broadcast environment change
            import ctypes
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x1A
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment")
            
        except Exception as e:
            raise Exception(f"Could not update PATH: {e}")
    
    def _run_flutter_doctor(self):
        """Run flutter doctor to verify installation"""
        self.log("\n🏥 Running flutter doctor...")
        
        flutter_path = self.get_flutter_path()
        if not flutter_path:
            self.log("⚠️ Flutter path not found")
            return
        
        try:
            result = subprocess.run(
                [flutter_path, "doctor", "-v"],
                capture_output=True,
                text=True,
                timeout=120,
                env=os.environ
            )
            
            # Log output
            for line in result.stdout.split('\n')[:20]:  # First 20 lines
                self.log(f"   {line}")
            
            if "[✓]" in result.stdout or "[√]" in result.stdout:
                self.log("✅ Flutter doctor passed basic checks")
            else:
                self.log("⚠️ Some flutter doctor checks may need attention")
                
        except Exception as e:
            self.log(f"⚠️ Flutter doctor warning: {e}")
    
    def get_install_info(self) -> dict:
        """Get information about current installation"""
        return {
            "flutter_installed": self.is_flutter_installed(),
            "flutter_path": self.get_flutter_path(),
            "install_dir": str(self.install_dir),
            "flutter_sdk_path": str(self.flutter_path),
            "android_sdk_path": str(self.android_sdk_path)
        }


# ============================================================================
# Standalone test
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Flutter SDK Auto-Setup Test")
    print("=" * 60)
    print()
    
    setup = FlutterSetup()
    
    print(f"Install directory: {setup.install_dir}")
    print(f"Flutter installed: {setup.is_flutter_installed()}")
    print()
    
    # Ask to install
    if not setup.is_flutter_installed():
        answer = input("Flutter tidak terinstall. Download sekarang? (y/n): ")
        if answer.lower() == 'y':
            setup.ensure_flutter_ready()
    else:
        info = setup.get_install_info()
        print(f"Flutter path: {info['flutter_path']}")
