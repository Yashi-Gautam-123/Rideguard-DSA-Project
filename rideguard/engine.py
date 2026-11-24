"""Streaming anomaly monitor: queue, trip hash map, deadline heap and windows."""
from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .graph import RoadGraph

LOCATION_GAP = "LOCATION_GAP"
DRIVER_DEVICE = "DRIVER_DEVICE_UNAVAILABLE"
PASSENGER_DEVICE = "PASSENGER_DEVICE_UNAVAILABLE"
ROUTE_DEVIATION = "ROUTE_DEVIATION"
SPEED_ANOMALY = "SPEED_ANOMALY"


@dataclass
class Trip:
    trip_id: str
    taxi: str
    route: list[str]
    destination: str
    route_index: int = 0
    last_node: str = "T"
    last_update: str = ""
    anomalies: set[str] = field(default_factory=set)
    speeds: deque = field(default_factory=lambda: deque(maxlen=5))
    off_route_readings: deque = field(default_factory=lambda: deque(maxlen=4))
    updates: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    anomaly_history: list[dict] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    explanations: dict[str, str] = field(default_factory=dict)
    driver_online: bool = True
    passenger_online: bool = True
    status: str = "Normal Journey"
    tick: int = 0


class Monitor:
    def __init__(self, graph: RoadGraph, trips: list[Trip], scenario: str = "normal") -> None:
        self.graph = graph
        self.trips = {trip.trip_id: trip for trip in trips}
        self.scenario = scenario
        self.input_queue: deque[dict] = deque()
        self.deadlines: list[tuple[int, int, str]] = []
        self.deadline_versions = {trip.trip_id: 0 for trip in trips}
        self.sim_tick = 0
        self.clock = datetime.now(timezone.utc).replace(microsecond=0)
        for trip in trips:
            self.deadlines.append((2, 0, trip.trip_id))
        heapq.heapify(self.deadlines)
        self._refresh_all()

    def _refresh_all(self) -> None:
        for trip in self.trips.values():
            self._status(trip)

    def _status(self, trip: Trip) -> None:
        a = trip.anomalies
        if len(a) >= 2:
            trip.status = "Multiple anomalies detected"
        elif ROUTE_DEVIATION in a:
            trip.status = "Route deviation detected"
        elif SPEED_ANOMALY in a:
            trip.status = "Speed anomaly detected"
        elif DRIVER_DEVICE in a:
            trip.status = "Driver device unavailable"
        elif PASSENGER_DEVICE in a:
            trip.status = "Passenger device unavailable"
        elif LOCATION_GAP in a:
            trip.status = "Location temporarily unavailable"
        else:
            trip.status = "Normal Journey"

    def _event(self, trip: Trip, kind: str, detail: str, timestamp: str | None = None) -> None:
        trip.events.append({"time": timestamp or self.clock.isoformat(), "kind": kind, "detail": detail, "status": trip.status})

    def _toggle(self, trip: Trip, anomaly: str, active: bool, explanation: str) -> None:
        was_active = anomaly in trip.anomalies
        if active:
            trip.anomalies.add(anomaly)
            trip.explanations[anomaly] = explanation
        else:
            trip.anomalies.discard(anomaly)
            trip.explanations.pop(anomaly, None)
        if was_active != active:
            self._status(trip)
            self._event(trip, "Anomaly raised" if active else "Anomaly cleared", explanation)
            if active:
                trip.anomaly_history.append({"tick": self.sim_tick, "anomaly": anomaly})
                self._detect_pattern(trip)

    def _detect_pattern(self, trip: Trip) -> None:
        """Flag two different anomaly types that begin within three simulation ticks."""
        recent = [item for item in trip.anomaly_history if self.sim_tick - item["tick"] <= 3]
        types = list(dict.fromkeys(item["anomaly"] for item in recent))
        if len(types) < 2:
            return
        labels = {
            LOCATION_GAP: "location interruption", DRIVER_DEVICE: "driver device offline",
            PASSENGER_DEVICE: "passenger device offline", ROUTE_DEVIATION: "route deviation",
            SPEED_ANOMALY: "speed anomaly",
        }
        pattern = "Rapid sequence: " + " followed by ".join(labels.get(value, value) for value in types[-2:])
        if pattern not in trip.patterns:
            trip.patterns.append(pattern)
            self._event(trip, "Risk pattern detected", pattern)

    def _consume(self, item: dict) -> None:
        trip = self.trips[item["trip_id"]]
        trip.tick += 1
        trip.driver_online = item.get("driver_online", True)
        trip.passenger_online = item.get("passenger_online", True)
        self._toggle(trip, DRIVER_DEVICE, not trip.driver_online, "Driver phone is marked offline." if not trip.driver_online else "Driver phone is back online.")
        self._toggle(trip, PASSENGER_DEVICE, not trip.passenger_online, "Passenger phone is marked offline." if not trip.passenger_online else "Passenger phone is back online.")
        if item.get("location_available", True):
            if "lat" in item and "lon" in item:
                point = {"lat": float(item["lat"]), "lon": float(item["lon"])}
                node, snap_distance_m = self.graph.nearest_node(point)
            else:
                node = item["node"]
                point = item.get("location", self.graph.nodes[node])
                snap_distance_m = 0.0
            trip.last_node = node
            trip.last_update = self.clock.isoformat()
            trip.route_index = max(trip.route_index, item.get("route_index", trip.route_index))
            trip.updates.append({"time": trip.last_update, "node": node, "lat": point["lat"], "lon": point["lon"], "speed_kmh": item.get("speed_kmh", 32), "status": trip.status})
            trip.speeds.append(item.get("speed_kmh", 32))
            self._toggle(trip, LOCATION_GAP, False, "Location updates resumed.")
            route_distance_m = min(
                (self.graph.distance_m(point, self.graph.nodes[route_node]) for route_node in trip.route),
                default=float("inf"),
            )
            # A point more than 250 m from every planned route node is treated as
            # off-route. Requiring repeated readings reduces one-point false alarms.
            deviation = route_distance_m > 250
            trip.off_route_readings.append(deviation)
            if sum(trip.off_route_readings) >= 2:
                self._toggle(trip, ROUTE_DEVIATION, True,
                             f"{route_distance_m:.0f} m from the nearest planned-route point; at least two recent readings are off-route.")
            elif not deviation:
                self._toggle(trip, ROUTE_DEVIATION, False, "Recent GPS reading is back on the expected route.")
            average_speed = sum(trip.speeds) / len(trip.speeds)
            self._toggle(trip, SPEED_ANOMALY, average_speed > 90, f"Recent average speed is {average_speed:.0f} km/h; alert threshold is 90 km/h.")
            snap_note = f" · snapped {snap_distance_m:.0f} m to road graph" if snap_distance_m else ""
            self._event(trip, "Location update", f"{self.graph.nodes[node]['name']} · {item.get('speed_kmh', 32)} km/h{snap_note}")
            self.deadline_versions[trip.trip_id] += 1
            version = self.deadline_versions[trip.trip_id]
            heapq.heappush(self.deadlines, (self.sim_tick + 2, version, trip.trip_id))
        else:
            self._event(trip, "Location update missed", "No GPS update received; retaining the last known location.")
        self._status(trip)

    def _scenario_items(self, trip: Trip) -> list[dict]:
        route = trip.route
        next_index = min(trip.route_index + 1, len(route) - 1)
        item = {"trip_id": trip.trip_id, "node": route[next_index], "route_index": next_index, "speed_kmh": 34 + (trip.tick % 4) * 3,
                "driver_online": True, "passenger_online": True, "location_available": True}
        if self.scenario == "fleet-test":
            if trip.taxi == "RG-201" and 2 <= trip.tick <= 5:
                item["speed_kmh"] = 124
            elif trip.taxi == "RG-202" and 2 <= trip.tick <= 3:
                item["node"] = "W"
            elif trip.taxi == "RG-203" and 2 <= trip.tick <= 5:
                item["driver_online"] = False
            elif trip.taxi == "RG-204" and 2 <= trip.tick <= 5:
                item["location_available"] = False
                item["passenger_online"] = False
        elif self.scenario == "gps-loss" and trip.taxi == "RG-204" and 2 <= trip.tick <= 4:
            item["location_available"] = False
        elif self.scenario == "driver-offline" and trip.taxi == "RG-203" and 2 <= trip.tick <= 3:
            item["driver_online"] = False
        elif self.scenario == "passenger-offline" and trip.taxi == "RG-203" and 2 <= trip.tick <= 3:
            item["passenger_online"] = False
        elif self.scenario == "deviation" and trip.taxi == "RG-202" and 2 <= trip.tick <= 3:
            item["node"] = "W" if "W" in self.graph.nodes else route[next_index]
            item["off_route"] = True
        elif self.scenario == "speeding" and trip.taxi == "RG-201" and 2 <= trip.tick <= 5:
            item["speed_kmh"] = 124
        elif self.scenario == "multiple" and trip.taxi == "RG-204" and 2 <= trip.tick <= 4:
            item["location_available"] = False
            item["driver_online"] = False
        elif self.scenario == "mixed" and trip.taxi == "RG-201" and 2 <= trip.tick <= 3:
            item["speed_kmh"] = 118
        return item

    def advance(self) -> dict:
        self.sim_tick += 1
        self.clock += timedelta(seconds=30)
        for trip in self.trips.values():
            self.input_queue.append(self._scenario_items(trip))
        while self.input_queue:
            self._consume(self.input_queue.popleft())
        while self.deadlines and self.deadlines[0][0] <= self.sim_tick:
            _, version, trip_id = heapq.heappop(self.deadlines)
            if version != self.deadline_versions[trip_id]:
                continue
            trip = self.trips[trip_id]
            self._toggle(trip, LOCATION_GAP, True,
                         "No location update before its heap deadline; last known position is retained.")
        return self.snapshot()

    def finish_trip(self, trip_id: str) -> dict | None:
        """Close one trip and return its complete record for the history store."""
        trip = self.trips.get(trip_id)
        if trip is None:
            return None
        self.clock += timedelta(seconds=1)
        self._event(trip, "Trip completed", "Trip closed by the dashboard operator.")
        record = next(row for row in self.snapshot()["trips"] if row["trip_id"] == trip_id)
        record["completed_at"] = self.clock.isoformat()
        # Invalidate any outstanding heap entry before removing the active record.
        self.deadline_versions[trip_id] += 1
        del self.trips[trip_id]
        return record

    def snapshot(self) -> dict:
        trip_rows = []
        for trip in self.trips.values():
            # A* computes a fresh route from the last known position to the goal.
            path, distance = self.graph.shortest_path(trip.last_node, trip.destination, use_astar=True)
            trip_rows.append({"trip_id": trip.trip_id, "taxi": trip.taxi, "status": trip.status, "anomalies": sorted(trip.anomalies),
                              "last_node": trip.last_node, "last_location": self.graph.nodes[trip.last_node], "last_update": trip.last_update,
                              "destination": trip.destination, "route": trip.route, "route_index": trip.route_index,
                              "driver_online": trip.driver_online, "passenger_online": trip.passenger_online,
                              "speed_kmh": trip.speeds[-1] if trip.speeds else 0,
                              "alternative_route": path, "alternative_distance_km": None if distance == float("inf") else round(distance, 2),
                              "safe_places": self.graph.nearest_safe_places(trip.last_node), "events": trip.events[-40:],
                              "updates": trip.updates[-100:], "explanations": list(trip.explanations.values()),
                              "patterns": trip.patterns, "tick": trip.tick})
        counts = {}
        for row in trip_rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {"scenario": self.scenario, "graph": self.graph.as_dict(), "trips": trip_rows, "counts": counts,
                "clock": self.clock.isoformat(), "queued_updates": len(self.input_queue), "deadline_heap_size": len(self.deadlines)}
