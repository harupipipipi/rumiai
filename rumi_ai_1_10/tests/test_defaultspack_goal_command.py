"""Tests for slash command extension hooks and the /goal monitor command.

These tests exercise two layers:

1. The legacy ``pack_block`` execution type, kept for compatibility with
   file-added slash commands.

2. The live /goal slash command, which now starts an isolated goal monitor
   through a defaultspack ``rumi_function`` instead of running a public loop.

3. The old /goal block itself, which remains covered as a compatibility unit.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _ScriptedCallHandler:
    """Stand-in for the LLM gateway used by ``call_model``.

    Matches the call_handler signature ``handler(handler_id, payload) -> dict``
    expected by ``domain.ai_client.model_call.call_model`` and returns a
    pre-scripted response for each call.
    """

    def __init__(self, scripted_outputs):
        self._outputs = list(scripted_outputs)
        self.calls: list[dict] = []

    def __call__(self, handler_id, payload):
        self.calls.append({"handler_id": handler_id, "payload": payload})
        if not self._outputs:
            raise AssertionError("call_handler invoked more times than scripted")
        text = self._outputs.pop(0)
        return {"status": "ok", "data": {"content": text, "model": payload.get("model", "stub")}}


class TestPackBlockExecutionType(unittest.TestCase):
    """Cover the ``pack_block`` extension hook in ``SlashCommandRegistry``."""

    def test_pack_block_dispatches_to_block_run_for_default_origin(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "commands").mkdir(parents=True, exist_ok=True)
            (pack_root / "commands" / "default_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "echo",
                            "name": "echo",
                            "modes": ["chat"],
                            "args": [{"name": "message", "type": "string", "required": True}],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:goal.run",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)

            fake_run = Mock(return_value={"status": "ok", "data": {"echo": "hi"}})
            fake_module = SimpleNamespace(
                __file__=str(pack_root / "blocks" / "goal" / "run.py"),
                run=fake_run,
            )

            with patch(
                "domain.frontend.command_registry.importlib.import_module",
                return_value=fake_module,
            ):
                result = registry.execute(
                    {"command": "echo", "mode": "chat", "args": {"message": "hi"}},
                    {},
                )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["data"]["executed"])
        self.assertEqual(result["data"]["result"], {"echo": "hi"})
        fake_run.assert_called_once()
        call_args, _ = fake_run.call_args
        self.assertEqual(call_args[0]["message"], "hi")

    def test_pack_block_dispatches_for_pack_manifest_origin(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            manifest_dir = pack_root / "commands" / "manifests"
            manifest_dir.mkdir(parents=True, exist_ok=True)
            (manifest_dir / "echo.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "echo",
                            "name": "echo",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:goal.run",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)

            fake_run = Mock(return_value={"status": "ok", "data": {"echo": "ok"}})
            fake_module = SimpleNamespace(
                __file__=str(pack_root / "blocks" / "goal" / "run.py"),
                run=fake_run,
            )

            with patch(
                "domain.frontend.command_registry.importlib.import_module",
                return_value=fake_module,
            ):
                result = registry.execute({"command": "echo", "mode": "chat"}, {})

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["data"]["executed"])
        self.assertEqual(result["data"]["result"], {"echo": "ok"})
        fake_run.assert_called_once()

    def test_pack_block_rejects_unknown_pack_id(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "commands").mkdir(parents=True, exist_ok=True)
            (pack_root / "commands" / "default_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "echo",
                            "name": "echo",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "otherpack:goal.run",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)

            with patch("domain.frontend.command_registry.importlib.import_module") as mocked_import:
                result = registry.execute({"command": "echo", "mode": "chat"}, {})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_COMMAND")
        mocked_import.assert_not_called()

    def test_pack_block_rejects_modules_outside_pack_blocks_root(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "commands").mkdir(parents=True, exist_ok=True)
            (pack_root / "commands" / "default_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "echo",
                            "name": "echo",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:goal.run",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)
            fake_module = SimpleNamespace(__file__=str(pack_root / "escape.py"), run=lambda *_: None)

            with patch(
                "domain.frontend.command_registry.importlib.import_module",
                return_value=fake_module,
            ) as mocked_import:
                result = registry.execute({"command": "echo", "mode": "chat"}, {})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_COMMAND")
        mocked_import.assert_called_once()

    def test_pack_block_rejects_user_origin_manifest(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            user_dir = pack_root / "user_data" / "shared" / "commands"
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "evil.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "evil",
                            "name": "evil",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:goal.run",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)

            with patch("blocks.goal.run.run") as mocked_run:
                result = registry.execute({"command": "evil", "mode": "chat"}, {})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_COMMAND")
        mocked_run.assert_not_called()

    def test_pack_block_returns_execution_failed_when_module_missing(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "commands").mkdir(parents=True, exist_ok=True)
            (pack_root / "commands" / "default_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "ghost",
                            "name": "ghost",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:goal.does_not_exist",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)
            result = registry.execute({"command": "ghost", "mode": "chat"}, {})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "EXECUTION_FAILED")

    def test_pack_block_returns_invalid_when_run_missing(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            pack_root = Path(tmpdir)
            (pack_root / "commands").mkdir(parents=True, exist_ok=True)
            (pack_root / "commands" / "default_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "noop",
                            "name": "noop",
                            "modes": ["chat"],
                            "execution": {
                                "type": "pack_block",
                                "qualified_name": "defaultspack:_common",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            registry = SlashCommandRegistry(pack_root)

            fake_module = SimpleNamespace(__file__=str(pack_root / "blocks" / "_common.py"))

            with patch(
                "domain.frontend.command_registry.importlib.import_module",
                return_value=fake_module,
            ):
                result = registry.execute({"command": "noop", "mode": "chat"}, {})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_COMMAND")


class TestGoalSlashCommandRegistration(unittest.TestCase):
    """The /goal command should appear in the live defaultspack manifests."""

    def test_goal_command_is_registered(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
        commands = registry.list_commands()
        ids = {command["id"] for command in commands}
        self.assertIn("goal", ids)

        goal_cmd = next(command for command in commands if command["id"] == "goal")
        self.assertEqual(goal_cmd["execution"]["type"], "rumi_function")
        self.assertEqual(goal_cmd["execution"]["pack_id"], "defaultspack")
        self.assertEqual(goal_cmd["execution"]["function_id"], "goal_start")
        self.assertEqual(goal_cmd["modes"], ["chat", "coding"])
        # Required goal arg keeps the registry's MISSING_ARGUMENT validation honest.
        goal_arg = next(arg for arg in goal_cmd["args"] if arg["name"] == "goal")
        self.assertTrue(goal_arg.get("required"))
        self.assertEqual(goal_arg.get("capture"), "rest")

    def test_goal_command_rejects_missing_goal_argument(self):
        from domain.frontend.command_registry import SlashCommandRegistry

        registry = SlashCommandRegistry(DEFAULTSPACK_ROOT)
        result = registry.execute({"command": "goal", "mode": "chat", "args": {}}, {})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "MISSING_ARGUMENT")


class TestGoalMonitorStore(unittest.TestCase):
    """The new /goal path creates a monitor run and gates checker writes."""

    def test_start_goal_creates_surface_effect(self):
        from domain.goal.monitor import start_goal

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"RUMI_DEFAULTSPACK_GOAL_STORE_PATH": str(Path(tmpdir) / "goals.json")},
        ):
            result = start_goal(conversation_id="conv-1", objective="Ship the slice")

        self.assertEqual(result["status"], "running")
        self.assertEqual(result["conversation_id"], "conv-1")
        self.assertEqual(result["goal_run"]["objective"], "Ship the slice")
        effect = result["effects"][0]
        self.assertEqual(effect["type"], "surface.open")
        surface = effect["surface"]
        self.assertEqual(surface["kind"], "goal_monitor")
        self.assertEqual(surface["sourcePackId"], "defaultspack")
        self.assertEqual(surface["payload"]["objective"], "Ship the slice")

    def test_checker_verdict_requires_internal_writer(self):
        from domain.goal.store import GoalStore

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"RUMI_DEFAULTSPACK_GOAL_STORE_PATH": str(Path(tmpdir) / "goals.json")},
        ):
            store = GoalStore()
            run = store.create_run(conversation_id="conv-1", objective="Finish safely")
            with self.assertRaises(PermissionError):
                store.apply_checker_verdict(
                    run["goal_run_id"],
                    {"status": "achieved", "reason": "client says so"},
                )
            updated = store.apply_checker_verdict(
                run["goal_run_id"],
                {"status": "achieved", "reason": "checker verified it"},
                message_id="msg-1",
                internal=True,
            )

        self.assertEqual(updated["status"], "achieved")
        self.assertEqual(updated["latest_verdict"]["reason"], "checker verified it")
        self.assertEqual(updated["last_checked_message_id"], "msg-1")

    def test_list_runs_refreshes_subprocess_created_runs(self):
        from domain.goal.store import GoalStore

        with tempfile.TemporaryDirectory() as tmpdir, patch.dict(
            "os.environ",
            {"RUMI_DEFAULTSPACK_GOAL_STORE_PATH": str(Path(tmpdir) / "goals.json")},
        ):
            GoalStore._instance = None
            store = GoalStore()
            run = store.create_run(conversation_id="conv-1", objective="Initial goal")
            store_path = Path(tmpdir) / "goals.json"
            data = json.loads(store_path.read_text(encoding="utf-8"))
            external_run = {
                "goal_run_id": "external-run",
                "conversation_id": "conv-1",
                "objective": "Created by subprocess",
                "status": "running",
                "checker_policy": {},
                "last_checked_message_id": None,
                "latest_verdict": None,
                "created_at": int(run["created_at"]) + 1,
                "updated_at": int(run["updated_at"]) + 1,
                "metadata": {},
                "event_log": [],
            }
            data["runs"][external_run["goal_run_id"]] = external_run
            store_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            runs = store.list_runs(conversation_id="conv-1")

        self.assertIn("external-run", {item["goal_run_id"] for item in runs})


class TestGoalBlockLoop(unittest.TestCase):
    """The /goal block runs a worker + evaluator loop until the goal is achieved."""

    def test_goal_loop_stops_when_evaluator_marks_achieved_on_first_turn(self):
        from blocks.goal.run import run as goal_run

        handler = _ScriptedCallHandler(
            [
                "Wrote the haiku: silent code at dawn / commits whisper through the trees / branches reach for light.",
                json.dumps(
                    {
                        "achieved": True,
                        "reason": "Three-line haiku produced as requested.",
                        "next_instruction": "",
                    }
                ),
            ]
        )

        result = goal_run(
            {"goal": "Write a haiku about programming", "max_iterations": 3},
            {"call_handler": handler},
        )

        self.assertEqual(result["status"], "ok")
        data = result["data"]
        self.assertTrue(data["achieved"])
        self.assertEqual(data["iteration_count"], 1)
        self.assertEqual(data["stopped_reason"], "achieved")
        self.assertIn("haiku", data["final_output"].lower())

    def test_goal_loop_continues_until_evaluator_marks_achieved(self):
        from blocks.goal.run import run as goal_run

        handler = _ScriptedCallHandler(
            [
                "Initial draft: function add(a, b) { return a + b; }",
                json.dumps(
                    {
                        "achieved": False,
                        "reason": "Missing input validation requested by goal.",
                        "next_instruction": "Add input validation that throws on non-numeric arguments.",
                    }
                ),
                "Updated: function add(a, b) { if (typeof a !== 'number' || typeof b !== 'number') throw new TypeError('numeric arguments required'); return a + b; }",
                json.dumps(
                    {
                        "achieved": True,
                        "reason": "Implementation now validates inputs.",
                        "next_instruction": "",
                    }
                ),
            ]
        )

        result = goal_run(
            {
                "goal": "Implement an add(a,b) function with input validation",
                "max_iterations": 4,
            },
            {"call_handler": handler},
        )

        self.assertEqual(result["status"], "ok")
        data = result["data"]
        self.assertTrue(data["achieved"])
        self.assertEqual(data["iteration_count"], 2)
        self.assertEqual(data["stopped_reason"], "achieved")
        # Worker was prompted twice and evaluator was queried twice.
        worker_calls = [call for call in handler.calls if "Worker agent" in self._system_prompt(call)]
        evaluator_calls = [call for call in handler.calls if "Evaluator" in self._system_prompt(call)]
        self.assertEqual(len(worker_calls), 2)
        self.assertEqual(len(evaluator_calls), 2)
        self.assertIn(
            "Add input validation",
            self._user_prompt(worker_calls[1]),
        )

    def test_goal_loop_normalizes_invalid_evaluator_verdicts(self):
        from blocks.goal.run import run as goal_run

        cases = [
            ("invalid_json", "not json at all"),
            ("raw_text_object", json.dumps({"raw_text": "model could not comply"})),
            (
                "string_achieved",
                json.dumps(
                    {
                        "achieved": "yes",
                        "reason": "stringly typed verdict",
                        "next_instruction": "",
                    }
                ),
            ),
            (
                "missing_next_instruction",
                json.dumps({"achieved": False, "reason": "Need one more pass."}),
            ),
        ]

        for name, evaluator_output in cases:
            with self.subTest(name=name):
                handler = _ScriptedCallHandler(["Worker draft", evaluator_output])
                result = goal_run(
                    {"goal": "Refine the goal loop", "max_iterations": 1},
                    {"call_handler": handler},
                )

                self.assertEqual(result["status"], "ok")
                data = result["data"]
                self.assertFalse(data["achieved"])
                self.assertEqual(data["iteration_count"], 1)
                self.assertEqual(data["stopped_reason"], "max_iterations_reached")
                self.assertEqual(data["iterations"][0]["verdict"]["achieved"], False)
                self.assertEqual(
                    data["iterations"][0]["verdict"]["next_instruction"],
                    "Continue working toward the goal with concrete progress.",
                )

    def test_goal_loop_stops_at_max_iterations_when_never_achieved(self):
        from blocks.goal.run import run as goal_run

        handler = _ScriptedCallHandler(
            [
                "Attempt 1",
                json.dumps({"achieved": False, "reason": "Not yet.", "next_instruction": "Try harder."}),
                "Attempt 2",
                json.dumps({"achieved": False, "reason": "Still not there.", "next_instruction": "Keep going."}),
            ]
        )

        result = goal_run(
            {"goal": "Solve P=NP", "max_iterations": 2},
            {"call_handler": handler},
        )

        self.assertEqual(result["status"], "ok")
        data = result["data"]
        self.assertFalse(data["achieved"])
        self.assertEqual(data["iteration_count"], 2)
        self.assertEqual(data["stopped_reason"], "max_iterations_reached")

    def test_goal_loop_requires_goal_argument(self):
        from blocks.goal.run import run as goal_run

        result = goal_run({"goal": ""}, {})
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "MISSING_PARAM")

    def test_goal_loop_clamps_excessive_max_iterations(self):
        from blocks.goal.run import run as goal_run
        from blocks.goal.run import HARD_MAX_ITERATIONS

        handler = _ScriptedCallHandler(
            [
                "First attempt.",
                json.dumps(
                    {"achieved": True, "reason": "Done immediately.", "next_instruction": ""}
                ),
            ]
        )

        result = goal_run(
            {"goal": "Trivial goal", "max_iterations": "9999"},
            {"call_handler": handler},
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["max_iterations"], HARD_MAX_ITERATIONS)
        self.assertTrue(result["data"]["achieved"])

    def test_goal_loop_surfaces_worker_failure_with_partial_iterations(self):
        from blocks.goal.run import run as goal_run

        def failing_handler(_handler_id, _payload):
            # call_model() converts RuntimeError into a PROVIDER_ERROR response,
            # which the goal block must propagate as a WORKER_FAILED outcome.
            raise RuntimeError("provider exploded")

        result = goal_run(
            {"goal": "Anything", "max_iterations": 2},
            {"call_handler": failing_handler},
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "WORKER_FAILED")
        self.assertEqual(len(result["error"]["iterations"]), 1)
        self.assertEqual(result["error"]["iterations"][0]["phase"], "worker_error")

    @staticmethod
    def _system_prompt(call: dict) -> str:
        messages = call.get("payload", {}).get("messages", [])
        for message in messages:
            if message.get("role") == "system":
                content = message.get("content")
                return content if isinstance(content, str) else json.dumps(content)
        return ""

    @staticmethod
    def _user_prompt(call: dict) -> str:
        messages = call.get("payload", {}).get("messages", [])
        for message in messages:
            if message.get("role") == "user":
                content = message.get("content")
                return content if isinstance(content, str) else json.dumps(content)
        return ""


if __name__ == "__main__":
    unittest.main()
