"""Build script for Master Sentinal — creates a single-file .exe via PyInstaller."""

import PyInstaller.__main__
import customtkinter
import os
import shutil

# Get CustomTkinter path for data inclusion
ctk_path = os.path.dirname(customtkinter.__file__)

print(f"CustomTkinter path: {ctk_path}")

# Clean previous build
if os.path.exists('dist'):
    shutil.rmtree('dist')
if os.path.exists('build'):
    shutil.rmtree('build')

PyInstaller.__main__.run([
    'UnifiedDiagnostics/main.py',
    '--name=Master Sentinal',
    '--noconfirm',
    '--windowed',
    '--onefile',
    f'--add-data={ctk_path};customtkinter',
    # TODO: Replace --icon=NONE with a proper .ico file when one is available.
    #       e.g. '--icon=assets/icon.ico'
    '--icon=NONE',
    '--clean',
    '--uac-admin',
])

print("Build complete. Please check the 'dist' folder (NOT 'build').")
print("Executable: dist/Master Sentinal/Master Sentinal.exe")
