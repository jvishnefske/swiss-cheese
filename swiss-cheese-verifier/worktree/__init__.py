"""Git Worktree Manager.

Manages git worktrees for concurrent subagent execution.
"""

from .manager import WorktreeManager, WorktreeInfo

__all__ = ["WorktreeManager", "WorktreeInfo"]
