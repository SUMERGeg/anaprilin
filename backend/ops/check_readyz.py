from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime


def post_webhook(webhook_url: str, message: str) -> None:
    data = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check /readyz endpoint and exit non-zero on failure.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/readyz")
    parser.add_argument("--webhook-url", default="")
    args = parser.parse_args()

    now = datetime.now().isoformat(timespec="seconds")
    try:
        with urllib.request.urlopen(args.url, timeout=5) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200:
                raise RuntimeError(f"readyz status={response.status} body={body}")
            print(f"[{now}] readyz OK: {body}")
            return
    except Exception as exc:
        message = f"[{now}] readyz FAILED: {exc}"
        print(message, file=sys.stderr)
        if args.webhook_url:
            try:
                post_webhook(args.webhook_url, message)
            except Exception as hook_exc:
                print(f"[{now}] webhook send failed: {hook_exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

