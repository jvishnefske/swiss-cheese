"""Git Worktree Manager.

Manages git worktrees for concurrent subagent execution with linear rebasing.
Each subagent works in its own worktree, and changes are rebased linearly.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""
    name: str
    path: Path
    branch: str
    task_name: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    commits: list[str] = field(default_factory=list)  # Commit SHAs made in this worktree


class WorktreeError(Exception):
    """Error in worktree operations."""


class WorktreeManager:
    """Manages git worktrees for concurrent subagent execution.

    Workflow:
    1. Create worktrees for each concurrent task
    2. Subagents work in their worktrees
    3. Rebase worktrees linearly back to main branch
    4. Reverify after rebase
    5. Cleanup worktrees on success
    """

    def __init__(
        self,
        repo_path: str | Path,
        *,
        base_path: str = ".worktrees",
        branch_prefix: str = "swiss-cheese",
        main_branch: str = "main",
    ):
        self.repo_path = Path(repo_path).resolve()
        self.base_path = self.repo_path / base_path
        self.branch_prefix = branch_prefix
        self.main_branch = main_branch

        self._worktrees: dict[str, WorktreeInfo] = {}

    async def initialize(self) -> None:
        """Initialize the worktree manager."""
        # Ensure we're in a git repository
        if not (self.repo_path / ".git").exists():
            raise WorktreeError(f"Not a git repository: {self.repo_path}")

        # Create base path for worktrees
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Detect main branch
        result = await self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if result.returncode == 0:
            current = result.stdout.strip()
            if current in ("main", "master"):
                self.main_branch = current

    async def create_worktree(self, task_name: str) -> WorktreeInfo:
        """Create a new worktree for a task.

        Args:
            task_name: Name of the task (used for branch and directory naming).

        Returns:
            WorktreeInfo with worktree details.
        """
        # Sanitize task name for branch/path
        safe_name = task_name.replace("/", "-").replace(" ", "-").lower()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        branch_name = f"{self.branch_prefix}/{safe_name}-{timestamp}"
        worktree_path = self.base_path / safe_name

        # Remove existing worktree if present
        if worktree_path.exists():
            await self.remove_worktree(safe_name)

        # Create new branch from current HEAD
        result = await self._run_git([
            "worktree", "add",
            "-b", branch_name,
            str(worktree_path),
            self.main_branch,
        ])

        if result.returncode != 0:
            raise WorktreeError(f"Failed to create worktree: {result.stderr}")

        info = WorktreeInfo(
            name=safe_name,
            path=worktree_path,
            branch=branch_name,
            task_name=task_name,
        )

        self._worktrees[safe_name] = info
        return info

    async def remove_worktree(self, name: str) -> None:
        """Remove a worktree."""
        if name in self._worktrees:
            info = self._worktrees[name]
            path = info.path
            branch = info.branch
        else:
            path = self.base_path / name
            branch = None

        if path.exists():
            # Remove worktree
            await self._run_git(["worktree", "remove", "--force", str(path)])

            # Delete the branch
            if branch:
                await self._run_git(["branch", "-D", branch])

        self._worktrees.pop(name, None)

    async def get_worktree_commits(self, name: str) -> list[str]:
        """Get list of commit SHAs made in a worktree since branching."""
        if name not in self._worktrees:
            raise WorktreeError(f"Unknown worktree: {name}")

        info = self._worktrees[name]

        # Get commits between main and worktree branch
        result = await self._run_git(
            ["log", "--format=%H", f"{self.main_branch}..{info.branch}"],
            cwd=info.path,
        )

        if result.returncode != 0:
            return []

        commits = [c.strip() for c in result.stdout.strip().split("\n") if c.strip()]
        info.commits = commits
        return commits

    async def rebase_worktree(self, name: str) -> bool:
        """Rebase a worktree onto the latest main branch.

        Returns:
            True if rebase succeeded, False if conflicts occurred.
        """
        if name not in self._worktrees:
            raise WorktreeError(f"Unknown worktree: {name}")

        info = self._worktrees[name]

        # Fetch latest main
        await self._run_git(["fetch", "origin", self.main_branch])

        # Rebase onto main
        result = await self._run_git(
            ["rebase", f"origin/{self.main_branch}"],
            cwd=info.path,
        )

        if result.returncode != 0:
            # Abort failed rebase
            await self._run_git(["rebase", "--abort"], cwd=info.path)
            return False

        return True

    async def merge_worktree_to_main(self, name: str) -> bool:
        """Merge a worktree's changes back to main branch.

        Args:
            name: Worktree name to merge.

        Returns:
            True if merge succeeded.
        """
        if name not in self._worktrees:
            raise WorktreeError(f"Unknown worktree: {name}")

        info = self._worktrees[name]

        # Checkout main in the main repo
        result = await self._run_git(["checkout", self.main_branch])
        if result.returncode != 0:
            raise WorktreeError(f"Failed to checkout {self.main_branch}")

        # Merge the worktree branch
        result = await self._run_git(["merge", "--ff-only", info.branch])

        return result.returncode == 0

    async def linear_rebase_all(
        self,
        worktree_order: Sequence[str],
        *,
        reverify_callback: callable | None = None,
    ) -> list[tuple[str, bool]]:
        """Rebase all worktrees linearly in the specified order.

        This implements the "linear rebasing" strategy where each worktree's
        changes are rebased on top of the previous one, ensuring a clean
        linear history.

        Args:
            worktree_order: Order in which to rebase worktrees.
            reverify_callback: Optional async callback(worktree_name) to reverify
                              after each rebase. Should return True if verification passed.

        Returns:
            List of (worktree_name, success) tuples.
        """
        results: list[tuple[str, bool]] = []

        for name in worktree_order:
            if name not in self._worktrees:
                results.append((name, False))
                continue

            # Rebase this worktree onto current main
            success = await self.rebase_worktree(name)

            if not success:
                results.append((name, False))
                continue

            # Reverify if callback provided
            if reverify_callback:
                verify_passed = await reverify_callback(name)
                if not verify_passed:
                    results.append((name, False))
                    continue

            # Merge to main
            merge_success = await self.merge_worktree_to_main(name)
            results.append((name, merge_success))

        return results

    async def cleanup_all(self) -> None:
        """Remove all managed worktrees."""
        for name in list(self._worktrees.keys()):
            try:
                await self.remove_worktree(name)
            except Exception:
                pass  # Best effort cleanup

        # Also remove base path if empty
        if self.base_path.exists() and not any(self.base_path.iterdir()):
            self.base_path.rmdir()

    async def list_worktrees(self) -> list[WorktreeInfo]:
        """List all managed worktrees."""
        return list(self._worktrees.values())

    async def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a git command asynchronously."""
        cmd = ["git"] + args
        work_dir = cwd or self.repo_path

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode or 0,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
        )
