"""
端到端测试：PM 发任务 → Centurion 分活 → Worker 执行 → 验收

验证完整的 File-as-Bus 协作链路。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.base.llm_backend import MockLLMProvider, LLMResponse, ToolCallRequest
from src.bus.naming import TaskStatus, parse_filename, build_filename
from src.bus.task_card import TaskCard, TaskCardStore
from src.bus.artifact import ArtifactStore
from src.bees.pm_bee import PMBee
from src.bees.centurion_bee import CenturionBee
from src.bees.worker_bee import WorkerBee


class TestNaming(unittest.TestCase):
    """命名规范测试。"""

    def test_parse_valid_filename(self):
        parsed = parse_filename("pm_001_goals_pending.json")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.prefix, "pm")
        self.assertEqual(parsed.task_id, "001_goals")
        self.assertEqual(parsed.status, TaskStatus.PENDING)
        self.assertEqual(parsed.full_id, "pm_001_goals")

    def test_parse_worker_filename(self):
        parsed = parse_filename("worker_001_01_write_file_done.json")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.prefix, "worker")
        self.assertEqual(parsed.status, TaskStatus.DONE)

    def test_parse_invalid_filename(self):
        self.assertIsNone(parse_filename("random_file.txt"))
        self.assertIsNone(parse_filename("pm_task.json"))  # 缺少状态

    def test_build_filename(self):
        fname = build_filename("pm_test_task", TaskStatus.CLAIMED)
        self.assertEqual(fname, "pm_test_task_claimed.json")
        parsed = parse_filename(fname)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.full_id, "pm_test_task")


class TestTaskCardStore(unittest.TestCase):
    """任务卡片存储测试。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = TaskCardStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_create_and_get(self):
        card = TaskCard(
            task_id="worker_test_01",
            type="worker",
            title="Test task",
            description="A test task",
            tool="read_file",
            tool_params={"path": "test.txt"},
        )
        self.store.create(card)

        # 检查文件存在
        fpath = self.tmpdir / "task_pool" / "worker_test_01_pending.json"
        self.assertTrue(fpath.exists())

        # 读取回来
        loaded = self.store.get("worker_test_01")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Test task")
        self.assertEqual(loaded.status, TaskStatus.PENDING)
        self.assertEqual(loaded.tool, "read_file")

    def test_claim_task(self):
        card = TaskCard(
            task_id="worker_claim_test",
            type="worker",
            title="Claim test",
        )
        self.store.create(card)

        claimed = self.store.claim("worker_claim_test", "test_bee")
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.status, TaskStatus.CLAIMED)
        self.assertEqual(claimed.assigned_to, "test_bee")

        # task_pool 中应该没有了
        pending = self.store.list_pending("worker")
        self.assertEqual(len(pending), 0)

        # in_progress 中应该有
        in_prog = self.store.list_in_progress("worker")
        self.assertEqual(len(in_prog), 1)

    def test_claim_already_claimed(self):
        card = TaskCard(
            task_id="worker_double_claim",
            type="worker",
            title="Double claim test",
        )
        self.store.create(card)

        # 第一次领取成功
        claimed1 = self.store.claim("worker_double_claim", "bee1")
        self.assertIsNotNone(claimed1)

        # 第二次领取应该失败
        claimed2 = self.store.claim("worker_double_claim", "bee2")
        self.assertIsNone(claimed2)

    def test_complete_task(self):
        card = TaskCard(
            task_id="worker_complete_test",
            type="worker",
            title="Complete test",
        )
        self.store.create(card)
        claimed = self.store.claim("worker_complete_test", "test_bee")
        self.assertIsNotNone(claimed)

        self.store.complete(claimed, result="All done!")

        done = self.store.get("worker_complete_test")
        self.assertIsNotNone(done)
        self.assertEqual(done.status, TaskStatus.DONE)
        self.assertEqual(done.result, "All done!")

        # in_progress 应该空了
        in_prog = self.store.list_in_progress("worker")
        self.assertEqual(len(in_prog), 0)

    def test_fail_task(self):
        card = TaskCard(
            task_id="worker_fail_test",
            type="worker",
            title="Fail test",
        )
        self.store.create(card)
        claimed = self.store.claim("worker_fail_test", "test_bee")
        self.assertIsNotNone(claimed)

        self.store.complete(claimed, failed=True, error="Something went wrong")

        done = self.store.get("worker_fail_test")
        self.assertIsNotNone(done)
        self.assertEqual(done.status, TaskStatus.FAILED)
        self.assertEqual(done.error, "Something went wrong")


class TestArtifactStore(unittest.TestCase):
    """产出物存储测试。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = ArtifactStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_write_and_read_file(self):
        path = self.store.write_file("task_01", "output.txt", "Hello, World!")
        self.assertTrue(path.exists())

        content = self.store.read_file("task_01", "output.txt")
        self.assertEqual(content, "Hello, World!")

    def test_write_and_read_json(self):
        data = {"key": "value", "list": [1, 2, 3]}
        self.store.write_json("task_01", "data.json", data)

        loaded = self.store.read_json("task_01", "data.json")
        self.assertEqual(loaded, data)

    def test_list_artifacts(self):
        self.store.write_file("task_multi", "a.txt", "a")
        self.store.write_file("task_multi", "sub/b.txt", "b")

        files = self.store.list_artifacts("task_multi")
        self.assertEqual(len(files), 2)


class TestEndToEnd(unittest.IsolatedAsyncioTestCase):
    """端到端测试：完整的 PM → Centurion → Worker 链路。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.workspace = self.tmpdir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    async def test_full_pipeline_with_heuristic(self):
        """
        测试完整链路：
        1. PM Bee 创建一个文档任务
        2. Centurion Bee 领取并拆分子任务（启发式，不需要 LLM）
        3. Worker Bee 执行每个子任务
        4. Centurion Bee 汇总完成
        """
        # 使用 Mock LLM（其实启发式路径不会调用 LLM）
        mock_provider = MockLLMProvider()

        # ---- Step 1: PM Bee 创建任务 ----
        pm = PMBee(
            workspace=self.workspace,
            provider=mock_provider,
            bee_name="pm_test",
        )
        pm_task = await pm.create_task(
            goal="为新项目创建 README 和架构文档",
            title="创建项目文档",
            acceptance_criteria=[
                "README.md 包含项目介绍",
                "架构文档包含系统设计说明",
            ],
        )

        # 验证 PM 任务已创建并在 task_pool 中
        self.assertEqual(pm_task.type, "pm")
        self.assertEqual(pm_task.status, TaskStatus.PENDING)
        self.assertTrue(
            (self.workspace / "task_pool" / pm_task.filename).exists()
        )
        print(f"[E2E] Step 1 PASS: PM created task {pm_task.task_id}")

        # ---- Step 2: Centurion Bee 领取并拆分 ----
        centurion = CenturionBee(
            workspace=self.workspace,
            provider=mock_provider,
            bee_name="centurion_test",
        )
        did_work = await centurion.run_once()
        self.assertTrue(did_work, "Centurion should have processed a task")

        # 验证 PM 任务已被领取（in_progress）
        pm_task_updated = pm.task_store.get(pm_task.task_id)
        self.assertEqual(pm_task_updated.status, TaskStatus.CLAIMED)
        self.assertGreater(len(pm_task_updated.subtasks), 0)
        print(f"[E2E] Step 2 PASS: Centurion decomposed into {len(pm_task_updated.subtasks)} subtasks")

        # 验证 worker 子任务已创建在 task_pool 中
        worker_pending = centurion.task_store.list_pending(prefix="worker")
        self.assertEqual(len(worker_pending), len(pm_task_updated.subtasks))
        for subtask_id in pm_task_updated.subtasks:
            subtask = centurion.task_store.get(subtask_id)
            self.assertIsNotNone(subtask)
            self.assertEqual(subtask.parent_id, pm_task.task_id)

        # ---- Step 3: Worker Bee 执行子任务 ----
        worker = WorkerBee(
            workspace=self.workspace,
            provider=mock_provider,
            bee_name="worker_test",
        )

        # 执行所有子任务
        num_subtasks = len(pm_task_updated.subtasks)
        for i in range(num_subtasks + 1):  # +1 保证覆盖
            did_work = await worker.run_once()
            if not did_work:
                break

        # 验证所有 worker 任务都完成了
        worker_done = worker.task_store.list_done(prefix="worker")
        completed_subtasks = [t for t in worker_done
                              if t.parent_id == pm_task.task_id
                              and t.status == TaskStatus.DONE]
        self.assertEqual(len(completed_subtasks), num_subtasks,
                         f"Expected {num_subtasks} done worker tasks")
        print(f"[E2E] Step 3 PASS: Worker completed {len(completed_subtasks)} subtasks")

        # 验证产出物存在
        for subtask in completed_subtasks:
            artifacts = worker.artifact_store.list_artifacts(subtask.task_id)
            # 有些子任务（如 write_file）会在 artifacts 目录产生文件
            if subtask.tool == "write_file":
                self.assertGreater(len(artifacts), 0,
                                   f"Subtask {subtask.task_id} should produce artifacts")

        # ---- Step 4: Centurion Bee 汇总 ----
        did_work = await centurion.run_once()
        self.assertTrue(did_work, "Centurion should have summarized")

        # 验证 PM 任务已完成
        pm_final = centurion.task_store.get(pm_task.task_id)
        self.assertEqual(pm_final.status, TaskStatus.DONE,
                         f"PM task should be done, but is {pm_final.status}")
        self.assertIsNotNone(pm_final.result)
        self.assertGreater(len(pm_final.result), 0)
        print(f"[E2E] Step 4 PASS: Centurion summarized PM task")

        # ---- 最终验收：验证完整的状态流转 ----
        # task_pool 中不应有任何相关任务
        all_pending = centurion.task_store.list_pending()
        related_pending = [t for t in all_pending
                          if t.task_id == pm_task.task_id
                          or t.parent_id == pm_task.task_id]
        self.assertEqual(len(related_pending), 0,
                         "No related tasks should remain in task_pool")

        # in_progress 中不应有任何相关任务
        all_in_prog = centurion.task_store.list_in_progress()
        related_in_prog = [t for t in all_in_prog
                          if t.task_id == pm_task.task_id
                          or t.parent_id == pm_task.task_id]
        self.assertEqual(len(related_in_prog), 0,
                         "No related tasks should remain in progress")

        # done 中应有 PM 任务 + 所有子任务
        all_done = centurion.task_store.list_done()
        related_done = [t for t in all_done
                       if t.task_id == pm_task.task_id
                       or t.parent_id == pm_task.task_id]
        self.assertEqual(len(related_done), num_subtasks + 1,
                         f"Expected {num_subtasks + 1} done tasks (PM + subtasks)")

        print(f"[E2E] All steps PASS: {num_subtasks + 1} tasks completed via File-as-Bus")

    async def test_worker_simple_tool_task(self):
        """测试 Worker Bee 直接执行指定工具的任务。"""
        mock_provider = MockLLMProvider()
        worker = WorkerBee(
            workspace=self.workspace,
            provider=mock_provider,
            bee_name="worker_direct",
        )

        # 创建一个直接指定工具的 worker 任务
        store = TaskCardStore(self.workspace)
        card = TaskCard(
            task_id="worker_direct_test",
            type="worker",
            title="Write a test file",
            description="Write hello world to a file",
            tool="write_file",
            tool_params={
                "path": "artifacts/worker_direct_test/hello.txt",
                "content": "Hello from Worker Bee!",
            },
        )
        store.create(card)

        # Worker 执行
        did_work = await worker.run_once()
        self.assertTrue(did_work)

        # 验证任务完成
        done = store.get("worker_direct_test")
        self.assertEqual(done.status, TaskStatus.DONE)
        self.assertIsNotNone(done.result)

        # 验证文件已写入 artifacts 目录
        artifact_file = self.workspace / "artifacts" / "worker_direct_test" / "hello.txt"
        self.assertTrue(artifact_file.exists())
        with open(artifact_file) as f:
            self.assertIn("Hello from Worker Bee", f.read())

        print("[E2E] Worker direct tool task PASS")

    async def test_concurrent_claim_safety(self):
        """测试并发领取任务的安全性（模拟）。"""
        store = TaskCardStore(self.workspace)

        # 创建一个任务
        card = TaskCard(
            task_id="worker_concurrent_test",
            type="worker",
            title="Concurrent claim test",
        )
        store.create(card)

        # 两个 bee 同时尝试领取
        claimed1 = store.claim("worker_concurrent_test", "bee_a")
        claimed2 = store.claim("worker_concurrent_test", "bee_b")

        # 只有一个能成功
        success_count = sum(1 for c in [claimed1, claimed2] if c is not None)
        self.assertEqual(success_count, 1, "Only one bee should claim the task")

        winner = claimed1 or claimed2
        self.assertIsNotNone(winner)
        self.assertIn(winner.assigned_to, ["bee_a", "bee_b"])

        print("[E2E] Concurrent claim safety PASS")


class TestConcurrentClaim(unittest.TestCase):
    """真并发领取测试：多线程同时 claim 同一任务，断言只有 1 个成功。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = TaskCardStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_true_concurrent_claim(self):
        import threading

        card = TaskCard(
            task_id="concurrent_race",
            type="worker",
            title="Race test",
        )
        self.store.create(card)

        results: list[TaskCard | None] = []
        lock = threading.Lock()

        def claim_worker(name: str) -> None:
            result = self.store.claim("concurrent_race", name)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=claim_worker, args=(f"bee_{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r is not None]
        self.assertEqual(len(successes), 1, f"Expected 1 winner, got {len(successes)}")
        print(f"[CONCURRENT] 20 threads claim, 1 winner: {successes[0].assigned_to}")


class TestReclaimStale(unittest.TestCase):
    """Stale claim 回收测试。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = TaskCardStore(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_reclaim_stale_task(self):
        card = TaskCard(
            task_id="worker_stale_task",
            type="worker",
            title="Stale test",
        )
        self.store.create(card)
        claimed = self.store.claim("worker_stale_task", "bee_old")
        self.assertIsNotNone(claimed)

        # 人为把 claimed_at 改成 10 分钟前
        claimed.claimed_at = (datetime.now(timezone.utc).replace(minute=datetime.now().minute - 10)).isoformat()
        self.store.update(claimed)

        # reclaim 超时 5 分钟
        reclaimed = self.store.reclaim_stale(timeout_seconds=300.0)
        self.assertIn("worker_stale_task", reclaimed)

        # 验证任务回到 pending
        pending = self.store.list_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].status, TaskStatus.PENDING)
        self.assertIsNone(pending[0].assigned_to)

    def test_no_reclaim_fresh_task(self):
        card = TaskCard(
            task_id="worker_fresh_task",
            type="worker",
            title="Fresh test",
        )
        self.store.create(card)
        self.store.claim("worker_fresh_task", "bee_fresh")

        # reclaim 超时 5 分钟，刚 claim 的不应被回收
        reclaimed = self.store.reclaim_stale(timeout_seconds=300.0)
        self.assertNotIn("worker_fresh_task", reclaimed)

        in_prog = self.store.list_in_progress()
        self.assertEqual(len(in_prog), 1)


def run_tests():
    """运行所有测试。"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestNaming))
    suite.addTests(loader.loadTestsFromTestCase(TestTaskCardStore))
    suite.addTests(loader.loadTestsFromTestCase(TestArtifactStore))
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEnd))
    suite.addTests(loader.loadTestsFromTestCase(TestConcurrentClaim))
    suite.addTests(loader.loadTestsFromTestCase(TestReclaimStale))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 返回成功/失败
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
