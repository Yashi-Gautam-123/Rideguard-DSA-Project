"""Road graph and shortest-path algorithms for the illustrative demo map."""
from __future__ import annotations

import heapq
import math
import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RoadGraph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[str, dict[str, float]] = field(default_factory=dict)
    safe_places: list[dict] = field(default_factory=list)

    def add_node(self, node_id: str, name: str, lat: float, lon: float) -> None:
        self.nodes[node_id] = {"id": node_id, "name": name, "lat": lat, "lon": lon}
        self.edges.setdefault(node_id, {})

    def add_road(self, a: str, b: str, distance_km: float, bidirectional: bool = True) -> None:
        self.edges[a][b] = distance_km
        if bidirectional:
            self.edges[b][a] = distance_km

    @staticmethod
    def distance_m(a: dict, b: dict) -> float:
        lat_mid = math.radians((a["lat"] + b["lat"]) / 2)
        dy = (a["lat"] - b["lat"]) * 111_000
        dx = (a["lon"] - b["lon"]) * 111_000 * math.cos(lat_mid)
        return math.hypot(dx, dy)

    def nearest_node(self, point: dict) -> tuple[str, float]:
        node_id = min(self.nodes, key=lambda key: self.distance_m(point, self.nodes[key]))
        return node_id, self.distance_m(point, self.nodes[node_id])

    def shortest_path(self, start: str, goal: str, use_astar: bool = False) -> tuple[list[str], float]:
        if start not in self.nodes or goal not in self.nodes:
            return [], math.inf
        min_cost_ratio = 0.0
        if use_astar:
            ratios = []
            for a, neighbors in self.edges.items():
                for b, weight in neighbors.items():
                    direct_km = self.distance_m(self.nodes[a], self.nodes[b]) / 1000
                    if direct_km > 0:
                        ratios.append(weight / direct_km)
            min_cost_ratio = min(ratios, default=0.0)
        frontier: list[tuple[float, float, str]] = [(0.0, 0.0, start)]
        previous: dict[str, str | None] = {start: None}
        cost = {start: 0.0}
        while frontier:
            _, current_cost, current = heapq.heappop(frontier)
            if current_cost != cost.get(current):
                continue
            if current == goal:
                break
            for neighbor, length in self.edges[current].items():
                candidate = current_cost + length
                if candidate < cost.get(neighbor, math.inf):
                    cost[neighbor] = candidate
                    previous[neighbor] = current
                    heuristic = self.distance_m(self.nodes[neighbor], self.nodes[goal]) / 1000 * min_cost_ratio if use_astar else 0
                    heapq.heappush(frontier, (candidate + heuristic, candidate, neighbor))
        if goal not in previous:
            return [], math.inf
        path, cursor = [], goal
        while cursor is not None:
            path.append(cursor)
            cursor = previous[cursor]
        return list(reversed(path)), cost[goal]

    def nearest_safe_places(self, node_id: str, limit: int = 3) -> list[dict]:
        found = []
        for place in self.safe_places:
            path, distance = self.shortest_path(node_id, place["node"])
            if path:
                found.append({**place, "distance_km": round(distance, 2), "path": path})
        return sorted(found, key=lambda item: item["distance_km"])[:limit]

    def as_dict(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": self.edges, "safe_places": self.safe_places}


def demo_graph() -> RoadGraph:
    """Build the planned route from the supplied CSV plus illustrative side roads."""
    graph = RoadGraph()
    route_file = Path(__file__).resolve().parent.parent / "data" / "planned_route.csv"
    with route_file.open(newline="", encoding="utf-8-sig") as handle:
        route_points = [{"lat": float(row["lat"]), "lon": float(row["lon"])} for row in csv.DictReader(handle)]
    graph.route_points = ["T" if i == 0 else "F" if i == len(route_points) - 1 else f"R{i:03d}"
                          for i in range(len(route_points))]
    for i, point in enumerate(route_points):
        node_id = graph.route_points[i]
        name = "Taj Mahal · route start" if i == 0 else "Agra Fort · route end" if i == len(route_points) - 1 else f"Planned route point {i:02d}"
        graph.add_node(node_id, name, point["lat"], point["lon"])
    for i in range(len(graph.route_points) - 1):
        a, b = graph.route_points[i], graph.route_points[i + 1]
        km = graph.distance_m(graph.nodes[a], graph.nodes[b]) / 1000
        graph.add_road(a, b, max(km, 0.001))

    # These junctions are illustrative connectors: the supplied CSV only describes
    # the planned route, not the full surrounding road network.
    points = [
        ("S", "Sample South Junction", 27.1698, 78.0410), ("M", "Sample Moti Bagh Junction", 27.1769, 78.0350),
        ("R", "Sample Raja Ki Mandi Junction", 27.1830, 78.0330), ("C", "Sample City Centre Junction", 27.1872, 78.0400),
        ("E", "Sample East Junction", 27.1810, 78.0500), ("N", "Sample North Connector", 27.1910, 78.0470),
        ("W", "Sample West Connector", 27.1880, 78.0250), ("P", "Sample Police Help Point", 27.1900, 78.0310),
        ("H", "Sample Hospital", 27.1850, 78.0520), ("Q", "Sample Clinic", 27.1710, 78.0300),
    ]
    for values in points:
        graph.add_node(*values)
    route_nodes = graph.route_points
    for side_id, _, lat, lon in points:
        side_point = {"lat": lat, "lon": lon}
        anchor = min(route_nodes, key=lambda key: graph.distance_m(side_point, graph.nodes[key]))
        connector_km = graph.distance_m(side_point, graph.nodes[anchor]) / 1000
        graph.add_road(side_id, anchor, max(connector_km, 0.1))
    for a, b, km in [("S", "M", .8), ("M", "R", .9), ("R", "C", .8), ("C", "E", .9),
                     ("M", "F", 1.5), ("F", "W", .8), ("W", "R", 1.0), ("C", "N", .7),
                     ("N", "E", .8), ("R", "P", .7), ("E", "H", .4), ("S", "Q", 1.2),
                     ("Q", "F", 1.0), ("W", "P", 1.0)]:
        graph.add_road(a, b, km)
    graph.safe_places = [
        {"name": "Sample Police Help Point", "kind": "Police", "node": "P"},
        {"name": "Sample Hospital", "kind": "Hospital", "node": "H"},
        {"name": "Sample Clinic", "kind": "Clinic", "node": "Q"},
    ]
    return graph
