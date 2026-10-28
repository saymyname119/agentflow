import argparse
import json
import logging
import time
from pathlib import Path

from .models import Policy, Snapshot
from .policy import evaluate


def main():
    parser = argparse.ArgumentParser(description="ApprovalFlow PR triage")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("evaluate", help="Evaluate a local snapshot without credentials")
    demo.add_argument("snapshot")
    demo.add_argument("--policy", default="policy.json")
    commands.add_parser("serve")
    commands.add_parser("demo", help="Start the isolated fixture-backed web demo without credentials")
    worker = commands.add_parser("worker")
    worker.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "evaluate":
        snapshot = Snapshot.model_validate_json(Path(args.snapshot).read_text())
        policy = Policy.model_validate_json(Path(args.policy).read_text())
        print(evaluate(snapshot, policy).model_dump_json(indent=2))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("approvalflow.api:create_app", factory=True, host="0.0.0.0", port=8000)
    elif args.command == "demo":
        import uvicorn
        uvicorn.run("approvalflow.demo:create_demo_app", factory=True, host="127.0.0.1", port=8000)
    else:
        from .config import Settings
        from .github import GitHub
        from .service import process_one
        from .storage import Store
        settings = Settings.load()
        store, github = Store(settings.database_url), GitHub(settings.github_token)
        try:
            while True:
                processed = process_one(store, github, settings.policy)
                if args.once:
                    break
                if not processed:
                    time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            github.client.close()
            store.engine.dispose()


if __name__ == "__main__":
    main()
