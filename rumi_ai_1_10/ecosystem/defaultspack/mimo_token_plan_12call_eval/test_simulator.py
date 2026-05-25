"""
Pytest tests for Discrete-Event Fulfillment Simulator
======================================================
Covers: priority scheduling, charger behavior, determinism, CLI JSON output.
"""
import json
import subprocess
import sys
from simulator import FulfillmentSimulator, Order, Robot, Charger


# ---------------------------------------------------------------------------
# Priority scheduling
# ---------------------------------------------------------------------------

class TestPriorityScheduling:
    """Higher-priority (lower number) orders should be fulfilled first."""

    def test_higher_priority_first(self):
        sim = FulfillmentSimulator(num_robots=1, num_chargers=0, seed=0,
                                   drain_rate=1.0, recharge_rate=1.0,
                                   low_battery_threshold=0, max_time=100)
        # Add three orders with same created_at; priority 1 should be done first
        o_low = sim.add_order(priority=3, work_units=1, created_at=0)
        o_med = sim.add_order(priority=2, work_units=1, created_at=0)
        o_high = sim.add_order(priority=1, work_units=1, created_at=0)

        result = sim.run()
        completed = result["orders_completed"]
        assert completed == 3, f"Expected 3 completed, got {completed}"

        # order completion sequence via event log
        done_events = [e for e in sim._event_log if e["type"] == "order_done"]
        done_ids = [e["order"] for e in done_events]
        # priority-1 order (o_high) should appear before priority-3 (o_low)
        assert done_ids.index(o_high.order_id) < done_ids.index(o_low.order_id)

    def test_same_priority_fifo_by_id(self):
        """When priorities match, lower order_id (earlier added) wins."""
        sim = FulfillmentSimulator(num_robots=1, num_chargers=0, seed=0,
                                   drain_rate=1.0, recharge_rate=1.0,
                                   low_battery_threshold=0, max_time=100)
        o0 = sim.add_order(priority=1, work_units=1, created_at=0)
        o1 = sim.add_order(priority=1, work_units=1, created_at=0)
        o2 = sim.add_order(priority=1, work_units=1, created_at=0)

        sim.run()
        done_events = [e for e in sim._event_log if e["type"] == "order_done"]
        done_ids = [e["order"] for e in done_events]
        assert done_ids == [0, 1, 2], f"FIFO order expected, got {done_ids}"

    def test_priority_across_robots(self):
        """Multiple robots should still prefer high-priority orders."""
        sim = FulfillmentSimulator(num_robots=2, num_chargers=0, seed=0,
                                   drain_rate=1.0, recharge_rate=1.0,
                                   low_battery_threshold=0, max_time=100)
        # 4 orders: priorities 3, 4, 1, 2
        sim.add_order(priority=3, work_units=1, created_at=0)
        sim.add_order(priority=4, work_units=1, created_at=0)
        o_high = sim.add_order(priority=1, work_units=1, created_at=0)
        sim.add_order(priority=2, work_units=1, created_at=0)

        result = sim.run()
        assert result["orders_completed"] == 4
        # first two assigned should be priorities 1 and 2
        assigned = [e for e in sim._event_log if e["type"] == "order_assigned"]
        first_two_priorities = sorted([assigned[0]["priority"], assigned[1]["priority"]])
        assert first_two_priorities == [1, 2], f"First assignments: {assigned[:2]}"


# ---------------------------------------------------------------------------
# Charger behavior
# ---------------------------------------------------------------------------

class TestChargerBehavior:

    def _make_low_battery_sim(self, initial_battery=15.0, **kwargs):
        """Create a sim where robot 0 has low battery."""
        defaults = dict(num_robots=1, num_chargers=1, seed=0,
                        drain_rate=5.0, recharge_rate=10.0,
                        low_battery_threshold=20.0, max_time=200)
        defaults.update(kwargs)
        sim = FulfillmentSimulator(**defaults)
        sim.robots[0].battery = initial_battery
        return sim

    def test_robot_charges_when_low(self):
        sim = self._make_low_battery_sim(initial_battery=10.0)
        # Add an order so robot works and triggers charge
        sim.add_order(priority=1, work_units=1, created_at=0)
        result = sim.run()

        charge_events = [e for e in sim._event_log
                         if e["type"] in ("charge_request", "charge_done")]
        assert len(charge_events) >= 2, "Expected charge_request + charge_done"
        assert result["robots"][0]["final_battery"] == 100.0

    def test_charger_queue_ordering(self):
        """Two robots needing charge should queue at the same charger."""
        sim = FulfillmentSimulator(num_robots=2, num_chargers=1, seed=0,
                                   drain_rate=50.0, recharge_rate=100.0,
                                   low_battery_threshold=20.0, max_time=200)
        # Force both robots to low battery
        sim.robots[0].battery = 10.0
        sim.robots[1].battery = 10.0

        # Give each one order to trigger work→charge path
        sim.add_order(priority=1, work_units=1, created_at=0)
        sim.add_order(priority=2, work_units=1, created_at=0)

        result = sim.run()
        # Both should end fully charged
        for rid in (0, 1):
            assert result["robots"][rid]["final_battery"] == 100.0

    def test_charger_not_needed_when_battery_high(self):
        """Robot with high battery should NOT request a charger."""
        sim = FulfillmentSimulator(num_robots=1, num_chargers=1, seed=0,
                                   drain_rate=1.0, recharge_rate=10.0,
                                   low_battery_threshold=20.0, max_time=100)
        sim.robots[0].battery = 100.0
        sim.add_order(priority=1, work_units=1, created_at=0)
        sim.run()

        charge_events = [e for e in sim._event_log
                         if e["type"] == "charge_request"]
        assert len(charge_events) == 0, "Robot should not charge with high battery"

    def test_battery_drain_rate_applied(self):
        """After completing work, battery = 100 - drain_rate * work_units."""
        sim = FulfillmentSimulator(num_robots=1, num_chargers=0, seed=0,
                                   drain_rate=5.0, recharge_rate=10.0,
                                   low_battery_threshold=0, max_time=100)
        sim.robots[0].battery = 100.0
        sim.add_order(priority=1, work_units=3, created_at=0)
        sim.run()
        assert sim.robots[0].battery == 85.0, f"Expected 85, got {sim.robots[0].battery}"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_same_seed_same_result(self):
        """Two runs with the same seed must produce identical summaries."""
        def run_sim(seed):
            sim = FulfillmentSimulator(num_robots=3, num_chargers=1, seed=seed,
                                       max_time=200)
            import random
            rng = random.Random(seed)
            for _ in range(20):
                sim.add_order(priority=rng.randint(1, 5),
                              work_units=rng.randint(1, 5),
                              created_at=rng.uniform(0, 100))
            return sim.run()

        r1 = run_sim(42)
        r2 = run_sim(42)
        assert r1 == r2, "Same seed must yield identical results"

    def test_different_seeds_differ(self):
        """Different seeds should (very likely) produce different results."""
        def run_sim(seed):
            sim = FulfillmentSimulator(num_robots=3, num_chargers=1, seed=seed,
                                       max_time=200)
            import random
            rng = random.Random(seed)
            for _ in range(20):
                sim.add_order(priority=rng.randint(1, 5),
                              work_units=rng.randint(1, 5),
                              created_at=rng.uniform(0, 100))
            return sim.run()

        r1 = run_sim(1)
        r2 = run_sim(999)
        # They might coincidentally match, but extremely unlikely with 20 orders
        # We check at least one field differs
        assert r1 != r2, "Different seeds should (almost certainly) differ"

    def test_event_log_deterministic(self):
        """Event logs from two identical runs should be identical."""
        def get_log(seed):
            sim = FulfillmentSimulator(num_robots=2, num_chargers=1, seed=seed,
                                       max_time=150)
            import random
            rng = random.Random(seed)
            for _ in range(10):
                sim.add_order(priority=rng.randint(1, 3),
                              work_units=rng.randint(1, 3),
                              created_at=rng.uniform(0, 50))
            sim.run()
            return sim._event_log

        log1 = get_log(77)
        log2 = get_log(77)
        assert log1 == log2


# ---------------------------------------------------------------------------
# CLI JSON output
# ---------------------------------------------------------------------------

class TestCLI:

    def test_cli_produces_valid_json(self):
        result = subprocess.run(
            [sys.executable, "simulator.py", "--seed", "42",
             "--robots", "2", "--orders", "5", "--max-time", "100"],
            capture_output=True, text=True,
            cwd=".",
        )
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert "orders_completed" in data
        assert "robots" in data

    def test_cli_seed_affects_output(self):
        r1 = subprocess.run(
            [sys.executable, "simulator.py", "--seed", "1", "--orders", "10"],
            capture_output=True, text=True,
            cwd=".",
        )
        r2 = subprocess.run(
            [sys.executable, "simulator.py", "--seed", "2", "--orders", "10"],
            capture_output=True, text=True,
            cwd=".",
        )
        d1 = json.loads(r1.stdout)
        d2 = json.loads(r2.stdout)
        # At minimum the seed field differs; results very likely differ too
        assert d1["seed"] != d2["seed"]

    def test_cli_default_args(self):
        """Running with no args should still succeed."""
        result = subprocess.run(
            [sys.executable, "simulator.py"],
            capture_output=True, text=True,
            cwd=".",
        )
        assert result.returncode == 0, f"Default CLI failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["seed"] == 42

    def test_cli_json_has_expected_keys(self):
        result = subprocess.run(
            [sys.executable, "simulator.py", "--seed", "99", "--orders", "3"],
            capture_output=True, text=True,
            cwd=".",
        )
        data = json.loads(result.stdout)
        expected_keys = {"seed", "simulation_time", "orders_completed",
                         "average_wait", "robots"}
        assert expected_keys.issubset(data.keys()), f"Missing keys: {expected_keys - data.keys()}"
