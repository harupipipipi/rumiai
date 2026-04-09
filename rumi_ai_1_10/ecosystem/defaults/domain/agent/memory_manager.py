"""MemoryManager — manages project and workspace memory for agents."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class MemoryManager:
    """Handles long-term memory operations for agents.

    MVP: stub implementation. Future versions will persist to project.md.
    """

    def update_project_memory(self, session, agent_def, messages):
        """Update project memory based on conversation.

        MVP: no-op, returns True to indicate success.
        Future: extracts key information and persists to project.md.
        """
        return True

    def read_memory(self, memory_type, workspace):
        """Read memory of the given type from the workspace.

        MVP: returns empty string.
        Future: reads from project.md or other memory stores.
        """
        return ""
