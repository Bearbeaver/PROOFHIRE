"""Start the ProofScore Engine (port 5001) and the web application (port 5000).

    python run_all.py            # demo data on (default)
    PROOFHIRE_SEED_DEMO=0 python run_all.py

Open http://127.0.0.1:5000
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
ENGINE_PORT = os.environ.get("ENGINE_PORT", "5001")
WEB_PORT = os.environ.get("PORT", "5000")


def wait_for(url, seconds=180):
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    env = dict(os.environ, ENGINE_PORT=ENGINE_PORT, PORT=WEB_PORT, ENGINE_URL=f"http://127.0.0.1:{ENGINE_PORT}")
    procs = []
    try:
        print("Starting ProofScore Engine (first start trains the model, ~30 s)...")
        procs.append(subprocess.Popen([sys.executable, "-m", "engine.server"], cwd=ROOT, env=env))
        if not wait_for(f"http://127.0.0.1:{ENGINE_PORT}/health"):
            print("Engine did not start in time."); return 1
        print("Engine ready. Starting web application...")
        procs.append(subprocess.Popen([sys.executable, "-m", "backend.app"], cwd=ROOT, env=env))
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
