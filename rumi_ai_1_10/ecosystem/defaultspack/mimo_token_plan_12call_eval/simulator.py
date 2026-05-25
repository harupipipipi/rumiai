"""
Discrete-Event Fulfillment Simulator
=====================================
Robots pick priority orders, drain battery while working, and recharge at chargers.
Fully deterministic given a seed.
"""
from __future__ import annotations

import heapq
import json
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass
class Order:
    order_id: int
    priority: int          # lower number = higher priority
    work_units: int        # time-units a robot needs to fulfil it
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def __lt__(self, other: "Order"):
        # heapq pops smallest first → higher priority (lower int) wins
        return (self.priority, self.order_id) < (other.priority, other.order_id)


@dataclass
class Robot:
    robot_id: int
    battery: float = 100.0            # percent
    drain_rate: float = 5.0           # percent per time-unit while working
    recharge_rate: float = 10.0       # percent per time-unit while charging
    low_battery_threshold: float = 20.0
    current_order: Optional[Order] = None
    charger: Optional["Charger"] = None
    busy_until: float = 0.0
    orders_completed: int = 0

    @property
    def is_charging(self) -> bool:
        return self.charger is not None

    @property
    def needs_charge(self) -> bool:
        return self.battery <= self.low_battery_threshold


@dataclass
class Charger:
    charger_id: int
    queue: List[Robot] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return len(self.queue) == 0


# ---------------------------------------------------------------------------
# Event system (heap-based discrete-event simulation)
# ---------------------------------------------------------------------------

_EVENT_COUNTER = 0

def _next_seq():
    global _EVENT_COUNTER
    _EVENT_COUNTER += 1
    return _EVENT_COUNTER


@dataclass
class Event:
    time: float
    event_type: str
    payload: Any = None

    def __lt__(self, other: "Event"):
        if self.time != other.time:
            return self.time < other.time
        return _next_seq() < _next_seq()  # stable ordering fallback


# ---------------------------------------------------------------------------
# Simulator core
# ---------------------------------------------------------------------------

class FulfillmentSimulator:
    """
    Parameters
    ----------
    num_robots : int
    num_chargers : int
    seed : int – deterministic RNG seed
    drain_rate : float – battery % consumed per time-unit of work
    recharge_rate : float – battery % restored per time-unit of charging
    low_battery_threshold : float – robot must recharge when battery <= this
    max_time : float – simulation horizon
    """

    def __init__(
        self,
        num_robots: int = 3,
        num_chargers: int = 1,
        seed: int = 42,
        drain_rate: float = 5.0,
        recharge_rate: float = 10.0,
        low_battery_threshold: float = 20.0,
        max_time: float = 200.0,
    ):
        self.seed = seed
        self.rng = random.Random(seed)
        self.max_time = max_time
        self.current_time = 0.0

        # infrastructure
        self.robots: List[Robot] = [
            Robot(
                robot_id=i,
                drain_rate=drain_rate,
                recharge_rate=recharge_rate,
                low_battery_threshold=low_battery_threshold,
            )
            for i in range(num_robots)
        ]
        self.chargers: List[Charger] = [Charger(charger_id=j) for j in range(num_chargers)]

        # order backlog (priority queue)
        self._order_heap: List[Order] = []
        self._next_order_id = 0

        # event queue
        self._events: List[Event] = []

        # metrics
        self.completed_orders: List[Order] = []
        self._event_log: List[Dict[str, Any]] = []

    # ---- helpers ----

    def add_order(self, priority: int, work_units: int, created_at: float = 0.0):
        order = Order(order_id=self._next_order_id, priority=priority,
                      work_units=work_units, created_at=created_at)
        self._next_order_id += 1
        heapq.heappush(self._order_heap, order)
        heapq.heappush(self._events, Event(created_at, "new_order"))
        return order

    def _schedule(self, time: float, event_type: str, payload=None):
        heapq.heappush(self._events, Event(time, event_type, payload))

    def _log(self, entry: Dict[str, Any]):
        self._event_log.append(entry)

    # ---- event handlers ----

    def _handle_new_order(self, _evt: Event):
        self._assign_orders()

    def _assign_orders(self):
        """Try to assign pending orders to idle robots."""
        idle_robots = [r for r in self.robots
                       if r.current_order is None and not r.is_charging]
        idle_robots.sort(key=lambda r: r.robot_id)  # deterministic tie-break
        for robot in idle_robots:
            if not self._order_heap:
                break
            order = heapq.heappop(self._order_heap)
            order.started_at = self.current_time
            robot.current_order = order
            finish_time = self.current_time + order.work_units
            robot.busy_until = finish_time
            self._schedule(finish_time, "order_done", robot.robot_id)
            self._log({"time": self.current_time, "type": "order_assigned",
                       "robot": robot.robot_id, "order": order.order_id,
                       "priority": order.priority})

    def _handle_order_done(self, evt: Event):
        robot = self.robots[evt.payload]
        order = robot.current_order
        assert order is not None
        # drain battery
        robot.battery -= robot.drain_rate * order.work_units
        robot.battery = max(0.0, robot.battery)
        order.completed_at = self.current_time
        self.completed_orders.append(order)
        robot.orders_completed += 1
        robot.current_order = None
        self._log({"time": self.current_time, "type": "order_done",
                   "robot": robot.robot_id, "order": order.order_id,
                   "battery": round(robot.battery, 2)})
        # should we charge?
        if robot.needs_charge:
            self._request_charge(robot)
        else:
            self._assign_orders()  # try to grab next order

    def _request_charge(self, robot: Robot):
        # find least-queued charger (deterministic)
        charger = min(self.chargers, key=lambda c: (len(c.queue), c.charger_id))
        charger.queue.append(robot)
        robot.charger = charger
        self._log({"time": self.current_time, "type": "charge_request",
                   "robot": robot.robot_id, "charger": charger.charger_id})
        if len(charger.queue) == 1:
            # robot is first in line → start charging immediately
            self._start_charging(robot)

    def _start_charging(self, robot: Robot):
        # calculate time to reach 100 %
        deficit = 100.0 - robot.battery
        charge_time = deficit / robot.recharge_rate
        self._schedule(self.current_time + charge_time, "charge_done", robot.robot_id)

    def _handle_charge_done(self, evt: Event):
        robot = self.robots[evt.payload]
        robot.battery = 100.0
        charger = robot.charger
        assert charger is not None
        charger.queue.remove(robot)
        robot.charger = None
        self._log({"time": self.current_time, "type": "charge_done",
                   "robot": robot.robot_id, "battery": 100.0})
        # next robot in queue?
        if charger.queue:
            self._start_charging(charger.queue[0])
        # robot is free → try to work
        self._assign_orders()

    # ---- main loop ----

    def run(self) -> Dict[str, Any]:
        """Execute the simulation and return a summary dict."""
        # initial assignment
        self._assign_orders()

        while self._events:
            evt = heapq.heappop(self._events)
            if evt.time > self.max_time:
                break
            self.current_time = evt.time

            handlers = {
                "new_order": self._handle_new_order,
                "order_done": self._handle_order_done,
                "charge_done": self._handle_charge_done,
            }
            handler = handlers.get(evt.event_type)
            if handler:
                handler(evt)

        return self.summary()

    def summary(self) -> Dict[str, Any]:
        total = len(self.completed_orders)
        avg_wait = 0.0
        if total:
            avg_wait = sum(o.started_at - o.created_at for o in self.completed_orders) / total
        return {
            "seed": self.seed,
            "simulation_time": round(self.current_time, 2),
            "orders_completed": total,
            "average_wait": round(avg_wait, 2),
            "robots": {
                r.robot_id: {"orders_completed": r.orders_completed,
                              "final_battery": round(r.battery, 2)}
                for r in self.robots
            },
        }


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main():
    import argparse, sys
    parser = argparse.ArgumentParser(description="Discrete-Event Fulfillment Simulator")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--robots", type=int, default=3)
    parser.add_argument("--chargers", type=int, default=1)
    parser.add_argument("--orders", type=int, default=20)
    parser.add_argument("--max-time", type=float, default=200.0)
    parser.add_argument("--drain-rate", type=float, default=5.0)
    parser.add_argument("--recharge-rate", type=float, default=10.0)
    args = parser.parse_args()

    sim = FulfillmentSimulator(
        num_robots=args.robots,
        num_chargers=args.chargers,
        seed=args.seed,
        drain_rate=args.drain_rate,
        recharge_rate=args.recharge_rate,
        max_time=args.max_time,
    )

    rng = random.Random(args.seed)
    for i in range(args.orders):
        sim.add_order(
            priority=rng.randint(1, 5),
            work_units=rng.randint(1, 5),
            created_at=rng.uniform(0, args.max_time / 2),
        )

    result = sim.run()
    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
