"""Check Redis queue depths and task formats."""
import json
import os
import sys
sys.path.insert(0, "/app")

import redis

r = redis.from_url("redis://redis:6379/1")
print("Queue depths:")
for q in ["celery", "checkout", "reconciliation", "webhooks"]:
    depth = r.llen(q)
    print(f"  {q}: {depth} items")
    if depth > 0:
        item = r.lindex(q, 0)
        if item:
            try:
                parsed = json.loads(item)
                task_name = parsed.get("headers", {}).get("task", parsed.get("task", "?"))
                print(f"    first task: {task_name}")
            except Exception as e:
                print(f"    parse error: {e}")
