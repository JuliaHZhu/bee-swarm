"""Live E2E test: PM → Centurion → Worker with real LLM."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# repo root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.base.llm_backend import OpenAICompatProvider
from src.bees.pm_bee import PMBee
from src.bees.centurion_bee import CenturionBee
from src.bees.worker_bee import WorkerBee
from src.bus.task_card import TaskCardStore


async def main() -> None:
    workspace = ROOT / "e2e_workspace"
    workspace.mkdir(exist_ok=True)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    model = os.environ.get("OPENAI_MODEL", "kimi-k2.6")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    provider = OpenAICompatProvider(api_key=api_key, base_url=base_url or None, model=model)
    print(f"[E2E] LLM: {model} @ {base_url or 'default'}")

    # 1. PM creates a task
    pm = PMBee(workspace=workspace, provider=provider, bee_name="pm_e2e")
    card = await pm.create_task(
        goal="Create a file named hello.txt in the workspace with the content 'Hello from bee-swarm!'",
        title="Write hello.txt",
    )
    print(f"[E2E] PM created: {card.task_id}")

    # 2. Centurion decomposes
    centurion = CenturionBee(workspace=workspace, provider=provider, bee_name="centurion_e2e")
    did = await centurion.run_once()
    print(f"[E2E] Centurion did_work={did}")

    # 3. Worker executes (loop until no pending worker tasks or 50 iterations)
    worker = WorkerBee(workspace=workspace, provider=provider, bee_name="worker_e2e")
    for i in range(50):
        did = await worker.run_once()
        print(f"[E2E] Worker iteration {i+1} did_work={did}")
        if not did:
            # double-check: any pending worker tasks left?
            store = TaskCardStore(workspace)
            pending = store.list_pending()
            worker_pending = [c for c in pending if c.type == "worker"]
            if not worker_pending:
                break
            # If there are pending tasks but none claimed, maybe they are for a different agent
            # Continue a few more iterations to let other agents pick them up (none here)
            await asyncio.sleep(0.5)

    # 4. Inspect results
    store = TaskCardStore(workspace)
    for tid in sorted(store.list_all()):
        c = store.get(tid)
        if c:
            print(f"  {tid}: status={c.status.value} result={(c.result[:120] if c.result else None)!r}")

    # 5. Verify artifact
    hello = workspace / "hello.txt"
    if hello.exists():
        content = hello.read_text()
        print(f"[E2E] Artifact hello.txt: {content!r}")
        assert "Hello from bee-swarm" in content, "Content mismatch"
        print("[E2E] ✅ PASSED")
    else:
        print("[E2E] ❌ hello.txt not found")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
