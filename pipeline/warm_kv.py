#!/usr/bin/env python3
"""Publish every route snapshot through the protected Worker publisher.
The pipeline is the sole caller/owner; publication failure fails the pipeline.
"""
import argparse, json, os, urllib.request

def publish(base_url=None, key=None):
    url = (base_url or os.environ.get("SNAPSHOT_PUBLISH_URL") or "").rstrip("/") + "/api/admin/snapshots"
    secret = key or os.environ.get("SNAPSHOT_PUBLISH_KEY")
    if not url.startswith("https://") or not secret:
        raise RuntimeError("SNAPSHOT_PUBLISH_URL (https) and SNAPSHOT_PUBLISH_KEY are required")
    req = urllib.request.Request(url, method="POST", headers={"x-aac-key": secret, "content-type": "application/json"}, data=b"{}")
    with urllib.request.urlopen(req, timeout=120) as response:
        body = json.load(response)
    if not body.get("ok") or len(body.get("published", {})) != 4:
        raise RuntimeError(f"incomplete snapshot publication: {body}")
    print(json.dumps(body, sort_keys=True)); return body

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--url"); ap.add_argument("--key")
    a = ap.parse_args(); publish(a.url, a.key)
