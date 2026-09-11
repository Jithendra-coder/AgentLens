"""
AgentLens Unified Single-Click Launcher.
Starts both the FastAPI Backend Engine and Next.js Frontend Studio,
verifies connectivity, and automatically launches the browser.
"""

import os
import sys
import time
import signal
import subprocess
import webbrowser
import urllib.request

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT_DIR, "web")

def check_port(url: str, timeout: float = 1.0) -> bool:
    try:
        res = urllib.request.urlopen(url, timeout=timeout)
        return res.status in (200, 404)
    except Exception:
        return False

def main():
    print("=" * 60)
    print("  🚀 Starting AgentLens AI Assistant & Observability Studio")
    print("=" * 60)

    processes = []

    # 1. Start Backend if not already alive
    if not check_port("http://127.0.0.1:8000/health/live"):
        print("[*] Launching Backend AI Engine on port 8000...")
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "--factory", "agentlens.api.app:create_app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(backend_proc)
    else:
        print("[✓] Backend AI Engine already running on port 8000.")

    # 2. Start Frontend if not already alive
    if not check_port("http://127.0.0.1:3000"):
        print("[*] Launching Frontend Studio on port 3000...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=WEB_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(frontend_proc)
    else:
        print("[✓] Frontend Studio already running on port 3000.")

    # 3. Wait for readiness
    print("[*] Verifying service connectivity...")
    backend_ready = False
    frontend_ready = False

    for _ in range(30):
        if not backend_ready and check_port("http://127.0.0.1:8000/health/live"):
            backend_ready = True
            print("[✓] Backend AI Engine is ONLINE (http://127.0.0.1:8000)")
        if not frontend_ready and check_port("http://127.0.0.1:3000"):
            frontend_ready = True
            print("[✓] Frontend Studio is ONLINE (http://localhost:3000)")
        if backend_ready and frontend_ready:
            break
        time.sleep(1)

    print("\n" + "=" * 60)
    print("  🎉 All Systems Operational!")
    print("  👉 Studio URL: http://localhost:3000")
    print("  👉 Backend API: http://127.0.0.1:8000")
    print("=" * 60 + "\n")

    # 4. Open default web browser
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass

    print("[*] Press Ctrl+C to stop all services.\n")

    def handle_exit(signum, frame):
        print("\n[*] Stopping AgentLens services...")
        for p in processes:
            try:
                p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_exit)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit(None, None)

if __name__ == "__main__":
    main()
