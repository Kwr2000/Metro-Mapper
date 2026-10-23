# P1-07 — Access (outline)

- **Agent:** Codex. Wave 1b. **Depends on:** P1-02.

- Geofabrik `texas-latest.osm.pbf` (725.6 MB), clipped to the three counties plus a 5 km buffer,
  downloaded once per monthly run (budget 1/day).
- Walk and bike networks with OSMnx (or pyrosm + networkx). Multi-source shortest paths from
  each destination type to every node, then block-group values as the population-weighted
  (2020 block centroids) median minutes.
- Destinations: grocery (`shop=supermarket|grocery|greengrocer`), park (`leisure=park`),
  school (`amenity=school`), daily-needs basket (pharmacy, cafe/restaurant, hardware, bank,
  library). Document the OSM tags.
- Transit: CapMetro GTFS scheduled departures on a representative weekday, 7–9 am, at stops
  within a 10-minute walk. "No fixed-route service" where there is none.
- Attribution "© OpenStreetMap contributors (ODbL)". Derived values are published as a
  produced work; record the share-alike reasoning in DECISIONS.
