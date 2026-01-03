"""
Build script for creating standalone EXE
Run: python build.py
"""
import os
import subprocess
import sys

def main():
    print("=" * 70)
    print("Building Download Internet Video - Standalone EXE")
    print("=" * 70)
    
    # Step 1: Install PyInstaller if needed
    print("\n[1/4] Checking PyInstaller...")
    try:
        import PyInstaller
        print("✓ PyInstaller found")
    except ImportError:
        print("⚠ Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Step 2: Build spec file
    print("\n[2/4] Creating build specification...")
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('locales', 'locales'),
        ('ffmpeg', 'ffmpeg'),
    ],
    hiddenimports=['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'yt_dlp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DownloadInternetVideo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DownloadInternetVideo',
)
'''
    
    with open('build.spec', 'w') as f:
        f.write(spec_content)
    print("✓ Spec file created: build.spec")
    
    # Step 3: Run PyInstaller
    print("\n[3/4] Building executable (this may take a few minutes)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "build.spec", "--onedir"],
            capture_output=False
        )
        if result.returncode == 0:
            print("✓ Build successful!")
        else:
            print("✗ Build failed!")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    
    # Step 4: Copy additional files
    print("\n[4/4] Copying additional files...")
    exe_dir = os.path.join("dist", "DownloadInternetVideo")
    
    # Copy locales if not already copied
    if not os.path.exists(os.path.join(exe_dir, "locales")):
        import shutil
        if os.path.exists("locales"):
            shutil.copytree("locales", os.path.join(exe_dir, "locales"))
            print("✓ Copied locales/")
    
    # Copy ffmpeg if not already copied
    if not os.path.exists(os.path.join(exe_dir, "ffmpeg")):
        import shutil
        if os.path.exists("ffmpeg"):
            shutil.copytree("ffmpeg", os.path.join(exe_dir, "ffmpeg"))
            print("✓ Copied ffmpeg/")
    
    print("\n" + "=" * 70)
    print("✓ BUILD COMPLETE!")
    print("=" * 70)
    print(f"\nExecutable location: dist/DownloadInternetVideo/DownloadInternetVideo.exe")
    print("\nYou can now:")
    print("  1. Run directly: double-click DownloadInternetVideo.exe")
    print("  2. Share the 'DownloadInternetVideo' folder to other computers")
    print("  3. No Python or additional software needed on target computers!")
    print("\n" + "=" * 70)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
