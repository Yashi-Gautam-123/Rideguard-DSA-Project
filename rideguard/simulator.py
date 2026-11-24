"""Repeatable taxi fleet scenarios for demonstrating Rideguard."""
from .engine import Monitor, Trip
from .graph import demo_graph


def build_demo_monitor(scenario: str = "normal") -> Monitor:
    valid = {"normal", "gps-loss", "driver-offline", "passenger-offline", "deviation", "speeding", "multiple", "mixed", "fleet-test"}
    if scenario not in valid:
        scenario = "normal"
    graph = demo_graph()
    trips = []
    for trip_id, taxi, start, goal in [("TR-1001", "RG-201", "T", "F"), ("TR-1002", "RG-202", "S", "C"),
                                      ("TR-1003", "RG-203", "T", "F"), ("TR-1004", "RG-204", "M", "F"),
                                      ("TR-1005", "RG-205", "R", "T"), ("TR-1006", "RG-206", "E", "T"),
                                      ("TR-1007", "RG-207", "W", "F"), ("TR-1008", "RG-208", "Q", "C")]:
        path = list(graph.route_points) if start == "T" and goal == "F" else graph.shortest_path(start, goal)[0]
        trips.append(Trip(trip_id=trip_id, taxi=taxi, route=path, destination=goal, last_node=start))
    return Monitor(graph, trips, scenario)
