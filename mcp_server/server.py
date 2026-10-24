"""boston-civic MCP server: live MBTA and National Weather Service data for the
Longwood/Fenway study area, exposed as tools Kiro (and the Storm Twin agent) can call.

Run: python mcp_server/server.py   (Kiro starts it from .kiro/settings/mcp.json)
Env: MBTA_API_KEY (optional, raises rate limits), NWS_USER_AGENT (required by NWS,
     e.g. "StormTwin (team-email@example.com)").
"""
from __future__ import annotations

import os

import httpx

try:  # mcp SDK 2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # mcp SDK 1.x
    from mcp.server.fastmcp import FastMCP

MBTA = "https://api-v3.mbta.com"
NWS = "https://api.weather.gov"
TIMEOUT = 10.0

# Center of the study area (Longwood Medical Area)
LONGWOOD_LAT, LONGWOOD_LON = 42.3378, -71.1050
DEFAULT_ROUTES = "Green-D,Green-E"

mcp = FastMCP("boston-civic")


def _mbta_headers() -> dict[str, str]:
    key = os.environ.get("MBTA_API_KEY")
    return {"x-api-key": key} if key else {}


def _nws_headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("NWS_USER_AGENT", "StormTwin (set NWS_USER_AGENT)"),
        "Accept": "application/geo+json",
    }


@mcp.tool()
def mbta_alerts(routes: str = DEFAULT_ROUTES, stop: str = "") -> list[dict]:
    """Active MBTA service alerts. `routes` is a comma-separated list of route ids
    (e.g. "Green-D,Green-E,39"); `stop` optionally filters to one stop id.
    Returns effect, severity, header, active periods and affected routes/stops."""
    params = {"filter[activity]": "ALL"}
    if routes:
        params["filter[route]"] = routes
    if stop:
        params["filter[stop]"] = stop
    r = httpx.get(f"{MBTA}/alerts", params=params, headers=_mbta_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for a in r.json().get("data", []):
        at = a["attributes"]
        out.append({
            "id": a["id"],
            "effect": at.get("effect"),
            "severity": at.get("severity"),
            "header": at.get("header"),
            "active_period": at.get("active_period"),
            "informed_entity": [
                {k: e.get(k) for k in ("route", "stop", "direction_id", "activities")}
                for e in at.get("informed_entity", [])
            ],
        })
    return out


@mcp.tool()
def mbta_elevators(stop: str) -> dict:
    """Elevators at an MBTA stop (parent station id, e.g. from /stops), plus the
    headers of any active ELEVATOR_CLOSURE alerts at that stop."""
    r = httpx.get(
        f"{MBTA}/facilities",
        params={"filter[stop]": stop, "filter[type]": "ELEVATOR"},
        headers=_mbta_headers(),
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    elevators = [{"id": f["id"], "name": f["attributes"].get("long_name") or f["attributes"].get("short_name")}
                 for f in r.json().get("data", [])]
    closures = [a["header"] for a in mbta_alerts(routes="", stop=stop)
                if a["effect"] == "ELEVATOR_CLOSURE"] if elevators else []
    return {"stop": stop, "elevators": elevators, "active_closures": closures}


@mcp.tool()
def nws_alerts(lat: float = LONGWOOD_LAT, lon: float = LONGWOOD_LON) -> list[dict]:
    """Active National Weather Service alerts for a point (defaults to Longwood)."""
    r = httpx.get(f"{NWS}/alerts/active", params={"point": f"{lat},{lon}"},
                  headers=_nws_headers(), timeout=TIMEOUT)
    r.raise_for_status()
    return [
        {k: f["properties"].get(k) for k in ("event", "severity", "headline", "onset", "ends")}
        for f in r.json().get("features", [])
    ]


@mcp.tool()
def nws_storm_inputs(lat: float = LONGWOOD_LAT, lon: float = LONGWOOD_LON) -> dict:
    """Raw gridded forecast series the storm generator needs: snowfallAmount,
    windSpeed and windGust for the NWS grid cell containing the point.
    Each series is a list of {validTime, value}; check 'uom' for units."""
    p = httpx.get(f"{NWS}/points/{lat},{lon}", headers=_nws_headers(), timeout=TIMEOUT)
    p.raise_for_status()
    grid_url = p.json()["properties"]["forecastGridData"]
    g = httpx.get(grid_url, headers=_nws_headers(), timeout=TIMEOUT)
    g.raise_for_status()
    props = g.json()["properties"]
    return {
        k: {"uom": props.get(k, {}).get("uom"), "values": props.get(k, {}).get("values", [])[:24]}
        for k in ("snowfallAmount", "windSpeed", "windGust")
    }


if __name__ == "__main__":
    mcp.run()
