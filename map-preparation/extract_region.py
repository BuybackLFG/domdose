"""Извлечение слоёв карты из локальной PBF-выгрузки OSM в region.json.

Один FileProcessor pyosmium с индексом локаций и сборкой площадей: линии
(coastline, дороги, реки, ж/д) из way, площади (здания, леса, парки,
водоёмы, landuse, районы) из замкнутых way и мультиполигонов, подписи из нод.

Использование (из корня репозитория, PYTHONPATH = корень):
    python extract_region.py <input.pbf> <west> <south> <east> <north> <out.json>
"""

import json
import math
import sys
import time
from pathlib import Path

import osmium

from core.logging import ServiceName, get_logger, load_logging_settings, setup_logging

_logger = get_logger("map-preparation.extract_region", service=ServiceName.MAP)
USAGE = "usage: extract_region.py <input.pbf> <west> <south> <east> <north> <out.json>"

REGION_FORMAT = 2
GEO_MARGIN_DEG = 0.03
# Быстрый отсев по первой ноде: way короче этих размахов не может войти в bbox.
LINE_PREFILTER_DEG = 0.5
LONG_PREFILTER_DEG = 1.5
LOCATION_STORAGE = "flex_mem"
FILTER_KEYS = ("building", "landuse", "natural", "leisure", "water", "waterway",
               "amenity", "highway", "railway", "place", "boundary")
HIGHWAY_CLASSES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary", "residential",
    "unclassified", "living_street", "service", "motorway_link", "trunk_link",
    "primary_link", "secondary_link", "tertiary_link", "track", "path",
    "footway", "cycleway", "pedestrian", "steps", "bridleway",
})
WATERWAY_LINES = frozenset({"river", "canal", "stream", "drain", "ditch"})
RAILWAY_LINES = frozenset({"rail", "light_rail", "subway", "tram", "narrow_gauge"})
PLACE_VALUES = frozenset({"city", "town", "suburb", "quarter", "neighbourhood",
                          "locality", "village", "hamlet", "island", "islet"})
LABEL_NATURAL = frozenset({"bay", "strait"})
ISLAND_PLACES = frozenset({"island", "islet"})
# Первое совпадение (ключ, значение) определяет слой площади.
AREA_RULES = (
    ("natural", "water", "water"), ("waterway", "riverbank", "water"),
    ("waterway", "dock", "water"), ("landuse", "reservoir", "water"),
    ("landuse", "basin", "water"), ("natural", "wetland", "wetland"),
    ("landuse", "forest", "forest"), ("natural", "wood", "forest"),
    ("natural", "scrub", "scrub"), ("natural", "heath", "scrub"),
    ("landuse", "grass", "grass"), ("landuse", "meadow", "grass"),
    ("landuse", "village_green", "grass"), ("natural", "grassland", "grass"),
    ("leisure", "common", "grass"), ("leisure", "park", "park"),
    ("leisure", "garden", "park"), ("landuse", "recreation_ground", "park"),
    ("leisure", "playground", "park"), ("leisure", "pitch", "pitch"),
    ("leisure", "stadium", "pitch"), ("leisure", "sports_centre", "pitch"),
    ("leisure", "track", "pitch"), ("landuse", "cemetery", "cemetery"),
    ("amenity", "grave_yard", "cemetery"), ("natural", "beach", "sand"),
    ("natural", "sand", "sand"), ("natural", "bare_rock", "rock"),
    ("natural", "scree", "rock"), ("landuse", "residential", "residential"),
    ("landuse", "industrial", "industrial"), ("landuse", "railway", "industrial"),
    ("landuse", "garages", "industrial"), ("landuse", "port", "industrial"),
    ("landuse", "construction", "industrial"), ("landuse", "commercial", "commercial"),
    ("landuse", "retail", "commercial"), ("landuse", "farmland", "farmland"),
    ("landuse", "allotments", "farmland"), ("landuse", "orchard", "farmland"),
    ("landuse", "farmyard", "farmland"), ("landuse", "plant_nursery", "farmland"),
)


def area_layer(tags):
    """Слой площади по тегам OSM либо None; районы - admin_level=9 с именем."""
    if tags.get("boundary") == "administrative":
        return "district" if tags.get("admin_level") == "9" and tags.get("name") else None
    if tags.get("place") in ISLAND_PLACES and tags.get("name"):
        return "island"
    building = tags.get("building")
    if building and building != "no":
        return "building"
    for key, value, layer in AREA_RULES:
        if tags.get(key) == value:
            return layer
    return None


class RelationFilter:
    """Фильтр первого прохода: мультиполигоны только известных слоёв."""

    def relation(self, rel):
        """True отбрасывает relation до сборки площади."""
        return area_layer(rel.tags) is None


def _box(bbox, margin):
    """bbox (w, s, e, n), расширенный на margin градусов."""
    west, south, east, north = bbox
    return west - margin, south - margin, east + margin, north + margin


def _inside(box, lon, lat):
    """Точка внутри bbox (w, s, e, n) включительно."""
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def _coords(nodes):
    """[[lat, lon], ...] нод way/кольца с точностью OSM (1e-7 градуса)."""
    return [[round(n.lat, 7), round(n.lon, 7)] for n in nodes]


class Collector:
    """Отбор объектов в bbox и раскладка по слоям region.json."""

    def __init__(self, bbox):
        self.bbox = bbox
        self.geo_box = _box(bbox, GEO_MARGIN_DEG)
        self.line_box = _box(bbox, LINE_PREFILTER_DEG)
        self.long_box = _box(bbox, LONG_PREFILTER_DEG)
        self.layers = {name: [] for name in
                       ("coastline", "areas", "roads", "waterways", "railways", "labels")}
        self.invalid_locations = 0

    def node(self, node):
        """Подпись места или бухты внутри bbox."""
        tags = node.tags
        name = tags.get("name")
        kind = tags.get("place") if tags.get("place") in PLACE_VALUES else tags.get("natural")
        if not name or (kind not in PLACE_VALUES and kind not in LABEL_NATURAL):
            return
        lon, lat = node.location.lon, node.location.lat
        if _inside(self.bbox, lon, lat):
            self.layers["labels"].append(
                (node.id, {"name": name, "lat": round(lat, 7), "lon": round(lon, 7),
                           "kind": kind}))

    def way(self, way):
        """Линейные слои: coastline, дороги, водотоки, железные дороги."""
        tags = way.tags
        highway, waterway, railway = (tags.get("highway"), tags.get("waterway"),
                                      tags.get("railway"))
        if tags.get("natural") == "coastline":
            layer, record = "coastline", None
        elif highway in HIGHWAY_CLASSES and tags.get("area") != "yes":
            layer = "roads"
            record = {"cls": highway, "name": tags.get("name"),
                      "tunnel": tags.get("tunnel") not in (None, "no")}
        elif waterway in WATERWAY_LINES:
            layer, record = "waterways", {"cls": waterway, "name": tags.get("name")}
        elif railway in RAILWAY_LINES:
            layer, record = "railways", {"cls": railway,
                                         "service": tags.get("service") is not None}
        else:
            return
        prefilter = self.long_box if layer == "coastline" else self.line_box
        try:
            first = way.nodes[0]
            if not _inside(prefilter, first.lon, first.lat):
                return
            coords = _coords(way.nodes)
        except (osmium.InvalidLocationError, IndexError):
            self.invalid_locations += 1
            return
        if len(coords) < 2 or not any(_inside(self.geo_box, lon, lat) for lat, lon in coords):
            return
        if record is None:
            self.layers[layer].append((way.id, coords))
        else:
            record["coords"] = coords
            self.layers[layer].append((way.id, record))

    def area(self, area):
        """Площади с внутренними кольцами; рамка проверяется по внешним кольцам."""
        layer = area_layer(area.tags)
        if layer is None:
            return
        try:
            if area.from_way():
                box = self.line_box if layer == "building" else self.long_box
                first = next(iter(next(iter(area.outer_rings()))))
                if not _inside(box, first.lon, first.lat):
                    return
            polygons = []
            for outer in area.outer_rings():
                rings = [_coords(outer)]
                rings += [_coords(inner) for inner in area.inner_rings(outer)]
                polygons.append(rings)
        except (osmium.InvalidLocationError, StopIteration):
            self.invalid_locations += 1
            return
        lats = [lat for rings in polygons for lat, _ in rings[0]]
        lons = [lon for rings in polygons for _, lon in rings[0]]
        west, south, east, north = self.geo_box
        if not lats or max(lons) < west or min(lons) > east or max(lats) < south \
                or min(lats) > north:
            return
        record = {"layer": layer, "polygons": polygons}
        if layer in ("district", "island"):
            record["name"] = area.tags.get("name")
        self.layers["areas"].append((area.id, record))

    def region(self):
        """Словарь region.json: слои отсортированы по id OSM (детерминизм)."""
        out = {"format": REGION_FORMAT, "bbox": list(self.bbox)}
        for name, items in self.layers.items():
            out[name] = [record for _, record in sorted(items, key=lambda item: item[0])]
        return out


def _fail(reason, message, **data):
    """Событие MAP_EXTRACT_FAILED с кодом причины и выход с текстом message."""
    _logger.error("MAP_EXTRACT_FAILED", "extraction failed", reason=reason, **data)
    raise SystemExit(message)


def main():
    """CLI: один проход FileProcessor и запись region.json; отказ - событие.

    Журнал настраивается до разбора аргументов (fail-fast). Ожидаемый отказ
    завершается SystemExit, непредвиденный пробрасывается после события.
    """
    setup_logging(load_logging_settings(ServiceName.MAP))
    try:
        pbf, west, south, east, north, out = (
            sys.argv[1], *[float(v) for v in sys.argv[2:6]], sys.argv[6])
    except (IndexError, ValueError):
        _fail("invalid_arguments", USAGE, argument_count=len(sys.argv) - 1)
    if not all(math.isfinite(v) for v in (west, south, east, north)):
        _fail("invalid_arguments", USAGE + "; bbox must be finite",
              argument_count=len(sys.argv) - 1)
    if not Path(pbf).is_file():
        _fail("pbf_not_found", f"PBF не найден: {pbf}", pbf_name=Path(pbf).name)

    collector = Collector((west, south, east, north))
    _logger.info("MAP_EXTRACT_STARTED", "extraction started", pbf_name=Path(pbf).name,
                 bbox=list(collector.bbox), margin_deg=GEO_MARGIN_DEG,
                 location_storage=LOCATION_STORAGE)
    started = time.monotonic()
    handlers = {"n": collector.node, "w": collector.way, "a": collector.area}
    try:
        processor = (osmium.FileProcessor(pbf)
                     .with_locations(LOCATION_STORAGE)
                     .with_areas(RelationFilter())
                     .with_filter(osmium.filter.KeyFilter(*FILTER_KEYS)))
        for obj in processor:
            handler = handlers.get(obj.type_str())
            if handler is not None:
                handler(obj)
        index_bytes = processor.node_location_storage.used_memory()
    except Exception as exc:
        _logger.error("MAP_EXTRACT_FAILED", "extraction failed",
                      reason="pbf_read_failed", error_type=type(exc).__name__)
        raise

    region = collector.region()
    try:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(region, fh, ensure_ascii=False, separators=(",", ":"))
    except OSError as exc:
        _logger.error("MAP_EXTRACT_FAILED", "extraction failed",
                      reason="output_write_failed", error_type=type(exc).__name__)
        raise
    layers = {}
    for record in region["areas"]:
        layers[record["layer"]] = layers.get(record["layer"], 0) + 1
    _logger.info(
        "MAP_EXTRACT_COMPLETED", "region written",
        output_name=Path(out).name, elapsed_s=round(time.monotonic() - started, 1),
        location_index_bytes=index_bytes, invalid_locations=collector.invalid_locations,
        coastline=len(region["coastline"]), areas=dict(sorted(layers.items())),
        roads=len(region["roads"]), waterways=len(region["waterways"]),
        railways=len(region["railways"]), labels=len(region["labels"]))


if __name__ == "__main__":
    main()
