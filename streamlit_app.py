from __future__ import annotations

import pandas as pd
import streamlit as st

from rideguard.simulator import build_demo_monitor
from rideguard.storage import load_history, save_completed_trip


st.set_page_config(page_title="Rideguard", page_icon="🚕", layout="wide")

SCENARIOS = {
    "Normal journey": "normal",
    "GPS interruption": "gps-loss",
    "Route deviation": "deviation",
    "Speed anomaly": "speeding",
    "Driver device offline": "driver-offline",
    "Passenger device offline": "passenger-offline",
    "Multiple anomalies": "multiple",
    "Full fleet test": "fleet-test",
}

if "rideguard_monitor" not in st.session_state:
    st.session_state.rideguard_monitor = build_demo_monitor()
if "rideguard_selected_trip" not in st.session_state:
    st.session_state.rideguard_selected_trip = None

st.title("🚕 Rideguard")
st.caption("Taxi journey safety monitor · DSA end-semester project · Simulated trip data")

with st.sidebar:
    st.header("Demo controls")
    scenario_label = st.selectbox("Choose a scenario", list(SCENARIOS))
    if st.button("Load scenario", use_container_width=True):
        st.session_state.rideguard_monitor = build_demo_monitor(SCENARIOS[scenario_label])
        st.session_state.rideguard_selected_trip = None
        st.rerun()
    if st.button("Next update", type="primary", use_container_width=True):
        st.session_state.rideguard_monitor.advance()
        st.rerun()
    if st.button("Reset to normal", use_container_width=True):
        st.session_state.rideguard_monitor = build_demo_monitor("normal")
        st.session_state.rideguard_selected_trip = None
        st.rerun()
    st.divider()
    st.caption("This optional Streamlit dashboard runs separately from the existing HTML/CSS/JavaScript dashboard.")

monitor = st.session_state.rideguard_monitor
snapshot = monitor.snapshot()
trips = snapshot["trips"]
normal_count = sum(t["status"] == "Normal Journey" for t in trips)
attention_count = len(trips) - normal_count

metric_columns = st.columns(4)
metric_columns[0].metric("Active trips", len(trips))
metric_columns[1].metric("Normal journeys", normal_count)
metric_columns[2].metric("Trips needing attention", attention_count)
metric_columns[3].metric("Sample safe locations", len(snapshot["graph"]["safe_places"]))

st.subheader("Fleet status")
status_rows = [
    {"Trip": trip["trip_id"], "Taxi": trip["taxi"], "Status": trip["status"],
     "Last known location": trip["last_location"]["name"], "Speed (km/h)": trip["speed_kmh"],
     "Driver device": "Online" if trip["driver_online"] else "Offline",
     "Passenger device": "Online" if trip["passenger_online"] else "Offline"}
    for trip in trips
]
st.dataframe(pd.DataFrame(status_rows), hide_index=True, use_container_width=True)

if trips:
    trip_ids = [trip["trip_id"] for trip in trips]
    saved_selection = st.session_state.rideguard_selected_trip
    selected_id = st.selectbox(
        "Inspect a trip",
        trip_ids,
        index=trip_ids.index(saved_selection) if saved_selection in trip_ids else 0,
    )
    st.session_state.rideguard_selected_trip = selected_id
    trip = next(item for item in trips if item["trip_id"] == selected_id)

    if trip["status"] == "Normal Journey":
        st.success(trip["status"])
    elif "Multiple" in trip["status"]:
        st.error(trip["status"])
    elif "deviation" in trip["status"] or "Speed" in trip["status"]:
        st.warning(trip["status"])
    else:
        st.info(trip["status"])

    left, right = st.columns([1, 1.2])
    with left:
        st.subheader("Trip details")
        st.write(f"**Last known position:** {trip['last_location']['name']}")
        st.write(f"**Last speed:** {trip['speed_kmh']} km/h")
        st.write(f"**Driver device:** {'Online' if trip['driver_online'] else 'Offline'}")
        st.write(f"**Passenger device:** {'Online' if trip['passenger_online'] else 'Offline'}")
        st.write("**Alert explanation**")
        if trip["explanations"]:
            for explanation in trip["explanations"]:
                st.write(f"- {explanation}")
        else:
            st.write("No active anomaly. Conditions are within expected ranges.")

        st.write("**Alternative route to destination**")
        node_names = {node["id"]: node["name"] for node in snapshot["graph"]["nodes"]}
        route_text = " → ".join(node_names.get(node_id, node_id) for node_id in trip["alternative_route"])
        st.caption(f"{route_text} · {trip['alternative_distance_km'] or 0} km")

        st.write("**Nearest sample safe locations · road distance**")
        if trip["safe_places"]:
            st.dataframe(pd.DataFrame([
                {"Location": place["name"], "Type": place["kind"], "Distance (km)": place["distance_km"]}
                for place in trip["safe_places"]
            ]), hide_index=True, use_container_width=True)
        else:
            st.caption("No sample safe location is reachable from this point.")

        if st.button("Finish trip and save to history"):
            record = monitor.finish_trip(selected_id)
            if record is not None:
                save_completed_trip(record)
                st.session_state.rideguard_selected_trip = None
                st.rerun()

    with right:
        st.subheader("Journey map")
        nodes = snapshot["graph"]["nodes"]
        route_nodes = set(trip["route"])
        safe_node_ids = {place["node"] for place in snapshot["graph"]["safe_places"]}
        markers = []
        for node in nodes:
            color = "#16836B" if node["id"] in route_nodes else "#A5B5AF"
            size = 55 if node["id"] in route_nodes else 25
            if node["id"] in safe_node_ids:
                color, size = "#40884F", 140
            markers.append({"lat": node["lat"], "lon": node["lon"], "color": color, "size": size})
        current = trip["last_location"]
        markers.append({"lat": current["lat"], "lon": current["lon"], "color": "#E18736", "size": 260})
        st.map(pd.DataFrame(markers), latitude="lat", longitude="lon", color="color", size="size", height=410)
        st.caption("Map markers show planned-route points, sample safe locations, and the selected taxi. Sample roads and facilities are illustrative.")

    st.subheader("Recent trip events")
    if trip["events"]:
        st.dataframe(pd.DataFrame([
            {"Time": event["time"], "Event": event["kind"], "Details": event["detail"]}
            for event in reversed(trip["events"][-10:])
        ]), hide_index=True, use_container_width=True)
    else:
        st.caption("No events yet. Select a scenario and click Next update.")

    if trip["patterns"]:
        st.subheader("Risk patterns")
        for pattern in trip["patterns"]:
            st.write(f"- {pattern}")
else:
    st.info("No active trips. Reset the demo to load trips again.")

with st.expander("Completed trip history"):
    history = load_history()
    if history:
        st.dataframe(pd.DataFrame([
            {"Trip": item.get("trip_id", ""), "Taxi": item.get("taxi", ""),
             "Status": item.get("status", ""), "Completed": item.get("completed_at", "")}
            for item in history
        ]), hide_index=True, use_container_width=True)
    else:
        st.caption("No trips have been completed in this demo yet.")

st.caption("Educational prototype. Trip updates are simulated; the sample safe locations are not verified real-world facilities.")
