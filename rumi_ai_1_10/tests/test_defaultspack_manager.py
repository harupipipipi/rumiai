from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core_runtime.defaultspack_manager import DefaultspackManager
from core_runtime.event_bus import EventBus


class TestDefaultspackManager(unittest.TestCase):
    def _write_module(
        self,
        root: Path,
        area: str,
        name: str,
        payload: dict,
    ) -> None:
        module_dir = root / area / name
        module_dir.mkdir(parents=True, exist_ok=True)
        (module_dir / "module.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_catalog_and_dependency_degrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_module(
                root,
                "backend",
                "tool",
                {
                    "module_id": "tool",
                    "display_name": "Tool",
                    "dependencies": [],
                },
            )
            self._write_module(
                root,
                "backend",
                "agent",
                {
                    "module_id": "agent",
                    "display_name": "Agent",
                    "dependencies": ["tool"],
                },
            )
            state_file = root / "state.json"
            manager = DefaultspackManager(pack_root=root, state_file=state_file)
            catalog = manager.get_catalog()
            self.assertEqual(catalog["count"], 2)
            self.assertEqual(catalog["dependency_graph"]["agent"], ["tool"])

            result = manager.disable("tool")
            self.assertEqual(result["state"], "disabled")
            agent = manager.get_module("agent")
            self.assertEqual(agent["state"], "degraded")
            self.assertIn("tool", agent["last_error"])

    def test_failure_threshold_and_recovery_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_module(
                root,
                "backend",
                "memory",
                {
                    "module_id": "memory",
                    "display_name": "Memory",
                    "dependencies": [],
                    "failure_threshold": 2,
                },
            )
            bus = EventBus()
            seen = []
            bus.subscribe("module.degraded", lambda payload: seen.append(("degraded", payload)))
            bus.subscribe("module.error_disabled", lambda payload: seen.append(("error_disabled", payload)))
            bus.subscribe("module.recovered", lambda payload: seen.append(("recovered", payload)))
            manager = DefaultspackManager(
                pack_root=root,
                state_file=root / "state.json",
                event_bus=bus,
            )

            first = manager.record_failure("memory", "temporary")
            self.assertEqual(first["state"], "degraded")
            second = manager.record_failure("memory", "permanent")
            self.assertEqual(second["state"], "error_disabled")

            recovered = manager.recover("memory")
            self.assertEqual(recovered["state"], "enabled")
            self.assertEqual([name for name, _ in seen], ["degraded", "error_disabled", "recovered"])


if __name__ == "__main__":
    unittest.main()
