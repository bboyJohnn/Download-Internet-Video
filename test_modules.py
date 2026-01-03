"""
Quick test - Check if modular structure works
"""
import sys
import os

# Add path
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, base_dir)

print("=" * 60)
print("TESTING MODULAR STRUCTURE")
print("=" * 60)

# Test 1: config.py
print("\n[1/5] Testing config.py imports...")
try:
    from config import STYLESHEET_MAIN, YTDLP_EXE, YTDLP_MODULE, LOCAL_FFMPEG_BIN
    print("✓ config.py loaded successfully")
    print(f"  - YTDLP_EXE: {YTDLP_EXE}")
    print(f"  - LOCAL_FFMPEG_BIN: {LOCAL_FFMPEG_BIN}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Test 2: core module
print("\n[2/5] Testing core module...")
try:
    from core.downloader import DownloadWorker
    from core.tools import check_and_install_tools
    print("✓ core module loaded successfully")
    print(f"  - DownloadWorker: {DownloadWorker}")
    print(f"  - check_and_install_tools: {check_and_install_tools}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Test 3: ui.widgets
print("\n[3/5] Testing ui.widgets...")
try:
    from ui.widgets import DownloadItemWidget, ShadowGroupBox
    print("✓ ui.widgets loaded successfully")
    print(f"  - DownloadItemWidget: {DownloadItemWidget}")
    print(f"  - ShadowGroupBox: {ShadowGroupBox}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Test 4: tools.installer
print("\n[4/5] Testing tools.installer...")
try:
    from tools.installer import ToolInstallThread
    print("✓ tools.installer loaded successfully")
    print(f"  - ToolInstallThread: {ToolInstallThread}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

# Test 5: ui.dialogs
print("\n[5/5] Testing ui.dialogs...")
try:
    from ui.dialogs import ToolInstallDialog
    print("✓ ui.dialogs loaded successfully")
    print(f"  - ToolInstallDialog: {ToolInstallDialog}")
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL MODULES LOADED SUCCESSFULLY!")
print("=" * 60)
print("\nModular structure is ready to use.")
print("Run: python main.py")
