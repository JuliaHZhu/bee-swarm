"""Swarm Supervisor — deploy-time process launcher & monitor.

Reads agent definitions and launches long-running worker-bee processes.
Each worker runs in its own subprocess and claims tasks via File-as-Bus.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from .agent_registry import AgentRegistry


class WorkerProcess:
    """Wraps a single worker subprocess."""

    def __init__(
        self,
        agent_name: str,
        workspace: Path,
        python_executable: str,
        extra_args: list[str] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.workspace = workspace
        self.python_executable = python_executable
        self.extra_args = extra_args or []
        self.proc: subprocess.Popen[Any] | None = None

    def start(self) -> None:
        cmd = [
            self.python_executable,
            "-m",
            "src.bees.worker_bee",
            "--workspace",
            str(self.workspace),
            "--agent",
            self.agent_name,
            *self.extra_args,
        ]
        self.proc = subprocess.Popen(cmd)
        print(f"[Supervisor] Started {self.agent_name} (pid {self.proc.pid})")

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def terminate(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
            print(f"[Supervisor] Stopped {self.agent_name} (pid {self.proc.pid})")

    def restart(self) -> None:
        self.terminate()
        self.start()


class SwarmSupervisor:
    """Monitors and manages a fleet of WorkerProcess instances."""

    def __init__(
        self,
        workspace: Path,
        agent_names: list[str] | None = None,
        poll_interval: float = 5.0,
        extra_args: list[str] | None = None,
    ) -> None:
        self.workspace = Path(workspace)
        self.poll_interval = poll_interval
        self.extra_args = extra_args or []
        self._shutdown = False
        self._reload = False

        # Resolve agent names
        reg = AgentRegistry()
        if agent_names:
            self.agent_names = agent_names
        else:
            self.agent_names = [a.name for a in reg.list_all()]

        if not self.agent_names:
            raise RuntimeError("No agents to supervise. Provide --agents or ensure agents/ has YAML files.")

        self.workers: list[WorkerProcess] = []
        for name in self.agent_names:
            self.workers.append(
                WorkerProcess(
                    agent_name=name,
                    workspace=self.workspace,
                    python_executable=sys.executable,
                    extra_args=self.extra_args,
                )
            )

    def start_all(self) -> None:
        for w in self.workers:
            w.start()

    def stop_all(self) -> None:
        for w in self.workers:
            w.terminate()

    def reload_all(self) -> None:
        print("[Supervisor] Reloading configuration...")
        self.stop_all()
        self.workers.clear()

        reg = AgentRegistry()
        self.agent_names = [a.name for a in reg.list_all()]
        for name in self.agent_names:
            self.workers.append(
                WorkerProcess(
                    agent_name=name,
                    workspace=self.workspace,
                    python_executable=sys.executable,
                    extra_args=self.extra_args,
                )
            )
        self.start_all()
        self._reload = False

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        if signum in (signal.SIGTERM, signal.SIGINT):
            print(f"[Supervisor] Received signal {signum}, shutting down...")
            self._shutdown = True
        elif signum == signal.SIGHUP:
            print("[Supervisor] Received SIGHUP, scheduling reload...")
            self._reload = True

    async def run(self) -> None:
        # Register Unix signals
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                asyncio.get_running_loop().add_signal_handler(sig, self._handle_signal, sig, None)
            except (NotImplementedError, ValueError):
                # Windows lacks SIGHUP; ignore gracefully
                pass

        self.start_all()

        while not self._shutdown:
            if self._reload:
                self.reload_all()

            for w in self.workers:
                if not w.is_alive():
                    print(f"[Supervisor] {w.agent_name} died, restarting...")
                    w.restart()

            await asyncio.sleep(self.poll_interval)

        self.stop_all()
        print("[Supervisor] All workers stopped. Exiting.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Swarm Supervisor — launch and monitor worker bees")
    parser.add_argument(
        "--workspace", type=str, default="./workspace",
        help="Path to the swarm workspace (default: ./workspace)",
    )
    parser.add_argument(
        "--agents", type=str, default="",
        help="Comma-separated agent names to launch (default: all builtin agents)",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=5.0,
        help="Health-check interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Start workers and exit immediately (no monitoring)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    agent_names = [a.strip() for a in args.agents.split(",") if a.strip()] or None

    supervisor = SwarmSupervisor(
        workspace=workspace,
        agent_names=agent_names,
        poll_interval=args.poll_interval,
    )

    if args.once:
        supervisor.start_all()
        print("[Supervisor] --once mode: workers launched, exiting supervisor.")
        return

    try:
        asyncio.run(supervisor.run())
    except KeyboardInterrupt:
        supervisor.stop_all()
        print("[Supervisor] Interrupted. All workers stopped.")


if __name__ == "__main__":
    main()
