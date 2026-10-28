"""CI smoke test for a built binary: version prints, and the bundled MCP server rejects unauthenticated calls."""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

exe = sys.argv[1]
print(subprocess.run([exe, "version"], capture_output=True, text=True, timeout=120).stdout.strip())
env = dict(os.environ, ZOTERO_MCP_ADMIN_PASSWORD="x" * 40, ZOTERO_MCP_PUBLIC_URL="https://x.ngrok-free.dev")
p = subprocess.Popen([exe, "serve-mcp", "serve", "--transport", "streamable-http", "--host", "127.0.0.1",
                      "--port", "18777"], env=env)
code = 0
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        try:
            opener.open("http://127.0.0.1:18777/mcp", timeout=3)
        except urllib.error.HTTPError as e:
            code = e.code
            break
        except Exception:
            time.sleep(1)
finally:
    p.kill()
print("GET /mcp ->", code)
sys.exit(0 if code == 401 else 1)
