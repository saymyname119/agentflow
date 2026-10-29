"""One-command launcher; uses only the Python standard library until dependencies are ready."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(args, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def usable(python):
    if not python.is_file():
        return False
    result = subprocess.run([str(python), "-c", "import fastapi, uvicorn, sqlalchemy, httpx, psycopg"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def prepare_python():
    suffix = Path("Scripts/python.exe" if os.name == "nt" else "bin/python")
    for folder in (ROOT / ".venv", ROOT.parent / ".venv"):
        candidate = folder / suffix
        if usable(candidate):
            return candidate
    python = ROOT / ".venv" / suffix
    if not python.is_file():
        print("Creating a local Python environment...", flush=True)
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    print("Installing Python dependencies...", flush=True)
    run([python, "-m", "pip", "install", "-e", "."])
    return python


def frontend_digest():
    paths = [ROOT / "frontend/package.json", ROOT / "frontend/package-lock.json",
             ROOT / "frontend/index.html", ROOT / "frontend/tsconfig.json", ROOT / "frontend/vite.config.ts"]
    paths += sorted((ROOT / "frontend/src").rglob("*"))
    paths += sorted((ROOT / "evaluation").glob("*.json"))
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare_frontend(rebuild=False):
    stamp = ROOT / ".local/frontend.sha256"
    digest = frontend_digest()
    if not rebuild and (ROOT / "frontend/dist/index.html").is_file() and stamp.is_file() and stamp.read_text() == digest:
        return
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise RuntimeError("Install Node.js 22.12+ (including npm), reopen your terminal, and run this command again.")
    frontend = ROOT / "frontend"
    lock = hashlib.sha256((frontend / "package-lock.json").read_bytes()).hexdigest()
    lock_stamp = ROOT / ".local/npm-lock.sha256"
    if not (frontend / "node_modules").is_dir() or not lock_stamp.is_file() or lock_stamp.read_text() != lock:
        print("Installing frontend dependencies...", flush=True)
        run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend)
        lock_stamp.parent.mkdir(exist_ok=True)
        lock_stamp.write_text(lock)
    print("Building the review workspace...", flush=True)
    run([npm, "run", "build"], cwd=frontend)
    stamp.parent.mkdir(exist_ok=True)
    stamp.write_text(digest)


def main():
    parser = argparse.ArgumentParser(description="Start ApprovalFlow. First run installs dependencies and builds the UI.")
    parser.add_argument("--sandbox", action="store_true", help="Guided real-GitHub sandbox setup")
    parser.add_argument("--reset", action="store_true", help="Reconfigure the sandbox without deleting review history")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the frontend")
    parser.add_argument("--prepare-only", action="store_true", help="Install/build without starting services")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        python = prepare_python()
        prepare_frontend(args.rebuild)
        if args.prepare_only:
            print("Setup complete. Run python start.py to open the demo.")
            return 0
        command = [python, "-m", "approvalflow.cli", "sandbox" if args.sandbox else "demo", "--port", args.port]
        if args.sandbox and args.reset:
            command.append("--reset")
        run(command)
    except KeyboardInterrupt:
        print("\nStopped ApprovalFlow.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"Setup or service exited with code {exc.returncode}. Fix the error above and rerun the same command.", file=sys.stderr)
        return exc.returncode
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
