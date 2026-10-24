"""Twin package (owner A): base road network, road-class tagging, hospitals,
transit stops and accessibility.

Builds real OSM + MBTA geography for the Longwood + Fenway study area and caches
it so the rest of the team loads it without live network access. Per tech.md,
this package must not import from src/adapters/.
"""
