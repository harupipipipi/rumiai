"""defaultspack backend compatibility package."""

from .agent import AgentOrchestrator, AgentRole, AgentSpec, TaskStatus, VisibilityScope
from .chat import ChatManager, ChatMessage
from .frontend_support import LayoutConfig, LayoutEngine, PaneConfig
from .knowledge import KnowledgeEntry, KnowledgeManager, KnowledgeStore
from .memory import MemoryEntry, MemoryManager, MemorySurface, MemoryStore, MemoryType, UserModel
from .migration import DefaultsMigrator
from .pack_extension import ExtensionManager, ExtensionRequest, PatchMode
from .sandbox import SandboxManager
from .cli.cli_adapter import CLIAdapter, get_cli_adapter
