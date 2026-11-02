# PyInstaller spec — builds ZoteroMCP (Windows: folder app; macOS: .app bundle)
import sys
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas, binaries, hiddenimports = [], [], []
for pkg in ("zotero_mcp", "fastmcp", "mcp", "uvicorn", "starlette", "sse_starlette", "pydantic", "pydantic_core",
            "pydantic_settings", "httpx", "httpcore", "anyio", "pyzotero", "mistune", "fitz", "pymupdf", "platformdirs",
            "pystray", "PIL", "cryptography", "psutil", "authlib", "rich", "dotenv", "itsdangerous", "jsonschema",
            "openapi_pydantic", "cyclopts", "exceptiongroup", "websockets", "certifi"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass
for dist in ("zotero-mcp-lite", "fastmcp", "mcp", "pydantic", "pydantic_core", "uvicorn", "starlette", "httpx",
             "pyzotero", "pymupdf", "platformdirs", "pystray", "authlib", "rich", "cyclopts", "jsonschema"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

IS_MAC = sys.platform == "darwin"
ICON = "build_assets/icon.icns" if IS_MAC else "build_assets/icon.ico"

a = Analysis(["../launcher.py"], pathex=[".."], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports + ["app", "app.__main__", "app.serve", "app.ai4paper"], excludes=["tkinter"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ZoteroMCP", console=False, icon=ICON,
          target_arch="arm64" if IS_MAC else None)
coll = COLLECT(exe, a.binaries, a.datas, name="ZoteroMCP")
if IS_MAC:
    app = BUNDLE(coll, name="ZoteroMCP.app", icon=ICON, bundle_identifier="com.robertxiong.zoteromcp",
                 info_plist={"LSUIElement": True, "CFBundleName": "Zotero MCP", "CFBundleDisplayName": "Zotero MCP",
                             "CFBundleShortVersionString": "1.1.0", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "12.0"})
