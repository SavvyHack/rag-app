# Build with: python -m PyInstaller --noconfirm OfflineRAG.spec
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
for package in ('customtkinter', 'llama_cpp', 'fastembed', 'onnxruntime'):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
datas += copy_metadata('fastembed') + copy_metadata('huggingface_hub')

a = Analysis(
    ['app.py'], pathex=[], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports + ['pypdf', 'huggingface_hub', 'self_test'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['pytest', 'IPython', 'matplotlib', 'torch', 'tensorflow'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='OfflineRAG', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False,
)
