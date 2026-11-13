"""Извлечение слоёв карты из локальной PBF-выгрузки OSM в region.json.

Два прохода pyosmium без полного location index: ноды расширенного bbox
и подписи (place, natural=bay/strait) в bbox; затем way с тегами рендера
получают геометрию из запомненных нод. Только OSM way, без relations.

Использование:
    python extract_region.py <input.pbf> <west> <south> <east> <north> <out.json>
"""

import json
import sys

import osmium

WATER_AREA_TAGS = (
    ("natural", "water"),
    ("waterway", "riverbank"),
    ("waterway", "dock"),
    ("landuse", "reservoir"),
    ("landuse", "basin"),
)
GREEN_TAGS = (
    ("leisure", "park"),
    ("leisure", "garden"),
    ("leisure", "common"),
    ("landuse", "forest"),
    ("landuse", "grass"),
    ("landuse", "recreation_ground"),
    ("landuse", "cemetery"),
    ("natural", "wood"),
    ("natural", "scrub"),
    ("natural", "grassland"),
    ("natural", "beach"),
    ("natural", "sand"),
)
HIGHWAY_CLASSES = {
    "motorway": 14.0, "trunk": 12.0, "primary": 11.0, "secondary": 10.0,
    "tertiary": 9.0, "residential": 8.0, "unclassified": 8.0,
    "living_street": 7.0, "service": 6.0, "motorway_link": 8.0,
    "trunk_link": 8.0, "primary_link": 8.0, "secondary_link": 8.0,
    "tertiary_link": 7.0, "track": 4.0, "path": 3.0, "footway": 3.0,
    "cycleway": 3.0, "pedestrian": 6.0, "steps": 3.0,
}
MINOR_HIGHWAYS = {"track", "path", "footway", "cycleway", "steps", "pedestrian"}
WATERWAY_LINES = {"river": 10.0, "canal": 8.0, "stream": 5.0, "drain": 4.0}
PLACE_VALUES = {"suburb", "quarter", "neighbourhood", "locality", "village",
                "hamlet", "town", "city"}


class NodePass(osmium.SimpleHandler):
    """Первый проход: координаты нод и подписанные ноды."""

    def __init__(self, geo_box, label_box):
        super().__init__()
        self.geo_box = geo_box  # (w, s, e, n) с запасом на геометрию way
        self.label_box = label_box  # (w, s, e, n) bbox рендера
        self.nodes = {}
        self.labels = []

    def node(self, n):
        lon, lat = n.location.lon, n.location.lat
        w, s, e, north = self.geo_box
        if not (w <= lon <= e and s <= lat <= north):
            return
        self.nodes[n.id] = (lat, lon)
        tags = n.tags
        if tags:
            place = tags.get("place")
            natural = tags.get("natural")
            name = tags.get("name")
            lw, ls, le, ln = self.label_box
            if name and ls <= lat <= ln and lw <= lon <= le:
                if (place in PLACE_VALUES) or natural in ("bay", "strait"):
                    self.labels.append({"name": name, "lat": lat, "lon": lon,
                                        "kind": place or natural})


class WayPass(osmium.SimpleHandler):
    """Второй проход: геометрия way с тегами рендеринга."""

    def __init__(self, node_index, geo_box):
        super().__init__()
        self.node_index = node_index
        self.geo_box = geo_box
        self.coastline = []
        self.water_areas = []
        self.green = []
        self.buildings = []
        self.roads = []
        self.waterways = []
        self.railways = []

    def way(self, w):
        tags = w.tags
        if not tags:
            return
        coords = []
        for ref in w.nodes:
            pt = self.node_index.get(ref.ref)
            if pt is not None:
                coords.append(pt)
        if len(coords) < 2:
            return
        gw, gs, ge, gn = self.geo_box
        inside = any(gs <= lat <= gn and gw <= lon <= ge
                     for lat, lon in coords)
        if not inside:
            return

        if tags.get("natural") == "coastline":
            self.coastline.append(coords)
            return

        tag_pairs = set((t.k, t.v) for t in tags)
        if tag_pairs & set(WATER_AREA_TAGS):
            self.water_areas.append(coords)
            return
        if tag_pairs & set(GREEN_TAGS):
            self.green.append(coords)
            return

        building = tags.get("building")
        highway = tags.get("highway")
        waterway = tags.get("waterway")
        railway = tags.get("railway")

        if building:
            self.buildings.append(coords)
        elif highway in HIGHWAY_CLASSES:
            self.roads.append({
                "cls": highway,
                "minor": highway in MINOR_HIGHWAYS,
                "name": tags.get("name"),
                "coords": coords,
            })
        elif waterway in WATERWAY_LINES:
            self.waterways.append({"cls": waterway, "coords": coords})
        elif railway in ("rail", "light_rail", "subway", "tram"):
            self.railways.append(coords)


def main():
    pbf, west, south, east, north, out = (
        sys.argv[1], *[float(v) for v in sys.argv[2:6]], sys.argv[6])
    margin = 0.03  # градуса запаса на геометрию way у края bbox
    geo_box = (west - margin, south - margin, east + margin, north + margin)
    label_box = (west, south, east, north)

    print("[extract] pass 1: nodes ...", flush=True)
    np = NodePass(geo_box, label_box)
    np.apply_file(pbf)

    print(f"[extract] nodes kept: {len(np.nodes)}, labels: {len(np.labels)}",
          flush=True)
    print("[extract] pass 2: ways ...", flush=True)
    wp = WayPass(np.nodes, geo_box)
    wp.apply_file(pbf)

    region = {
        "bbox": [west, south, east, north],
        "coastline": wp.coastline,
        "water_areas": wp.water_areas,
        "green": wp.green,
        "buildings": wp.buildings,
        "roads": wp.roads,
        "waterways": wp.waterways,
        "railways": wp.railways,
        "labels": np.labels,
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(region, fh)
    print(f"[extract] coastline={len(wp.coastline)} "
          f"water={len(wp.water_areas)} green={len(wp.green)} "
          f"buildings={len(wp.buildings)} roads={len(wp.roads)} "
          f"waterways={len(wp.waterways)} railways={len(wp.railways)}",
          flush=True)


if __name__ == "__main__":
    main()
