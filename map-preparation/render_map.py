"""Рендер offline-подложки пилотной зоны Владивостока: два PNG и manifest.

Читает region.json (extract_region.py, формат 2) и каталог pilotHouses.ts,
строит рамку EPSG:3857 2:1 вокруг 20 домов и рисует один кадр в двух
уровнях (обзорный и детальный) с палитровым квантованием PNG.

Использование (из корня репозитория, PYTHONPATH = корень):
    python render_map.py <region.json> <pilotHouses.ts> <PBF> <overview.png>
        <detail.png> <out.manifest.json> [--font <FONT>] [--font-bold <FONT_BOLD>]
"""

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import math
import platform
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, polylabel, substring, unary_union

from core.logging import ServiceName, get_logger, load_logging_settings, setup_logging

_logger = get_logger("map-preparation.render_map", service=ServiceName.MAP)

R_EARTH = 6378137.0
TILE_M_PER_PX_Z0 = 156543.03392
PILOT_SIZE = 20
PAD_M = 1500.0
ASPECT = 2
OVERVIEW_STRETCH_LIMIT = 1.3
MAX_PNG_BYTES = 8_000_000
REGION_FORMAT = 2
VOTE_OFFSET_M = 0.25
MAX_GLYPH_TURN = 30.0
MAX_STROKE_TURN = 50.0
IMAGE_URL = "/maps/vladivostok-pilot.png"
DETAIL_URL = "/maps/vladivostok-pilot-detail.png"
DEFAULT_FONT = r"C:\Windows\Fonts\arial.ttf"
DEFAULT_FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
EXTRACT_BBOX_ARGS = "131.63 43.05 132.29 43.33"

WATER = (170, 211, 223)
LAND = (242, 239, 233)
BUILDING = (217, 208, 201)
BUILDING_EDGE = (196, 185, 175)
BUILDING_LIGHT = (219, 213, 207)
RAIL = (146, 146, 146)
MINOR_WAY = (205, 190, 180)
TUNNEL = (226, 222, 216)
STREET_TEXT = (64, 64, 84)
PLACE_TEXT = (44, 44, 44)
BAY_TEXT = (36, 86, 138)
DISTRICT_TEXT = (112, 96, 128)
HALO = (255, 255, 255)
LANDCOVER = {
    "residential": (229, 227, 224), "industrial": (234, 223, 230),
    "commercial": (241, 225, 222), "farmland": (237, 240, 214),
    "cemetery": (190, 214, 190), "grass": (207, 234, 181), "scrub": (198, 216, 170),
    "forest": (172, 208, 157), "park": (196, 236, 186), "pitch": (172, 224, 204),
    "sand": (244, 232, 197), "rock": (231, 225, 217), "wetland": (204, 226, 218),
}
# Класс дороги: (обводка, заливка, ранг подписи).
ROAD_CLASSES = {
    "motorway": ((196, 76, 86), (232, 146, 162), 0),
    "trunk": ((196, 76, 86), (232, 146, 162), 0),
    "primary": ((190, 124, 70), (252, 214, 164), 1),
    "secondary": ((156, 154, 98), (247, 250, 191), 2),
    "tertiary": ((168, 168, 168), (255, 255, 255), 3),
    "motorway_link": ((196, 76, 86), (232, 146, 162), 4),
    "trunk_link": ((196, 76, 86), (232, 146, 162), 4),
    "primary_link": ((190, 124, 70), (252, 214, 164), 4),
    "secondary_link": ((156, 154, 98), (247, 250, 191), 4),
    "tertiary_link": ((168, 168, 168), (255, 255, 255), 4),
    "residential": ((188, 188, 188), (255, 255, 255), 5),
    "unclassified": ((188, 188, 188), (255, 255, 255), 5),
    "living_street": ((188, 188, 188), (250, 250, 250), 6),
    "pedestrian": ((188, 188, 188), (250, 245, 240), 6),
    "service": ((196, 196, 196), (255, 255, 255), 7),
}
MINOR_RANK = 8
STREET_ABBREVIATIONS = {
    "улица": "ул.", "проспект": "просп.", "переулок": "пер.",
    "бульвар": "бул.", "шоссе": "ш.", "набережная": "наб.",
    "площадь": "пл.", "проезд": "пр-д", "тупик": "туп.",
}
PLACE_PRIORITY = {"city": 0, "town": 1, "suburb": 1, "island": 2, "village": 3,
                  "quarter": 4, "neighbourhood": 4, "locality": 5, "hamlet": 5,
                  "islet": 5}
HOUSE_BLOCK_RE = re.compile(r"\{[^{}]*?house_id:\s*'[^']+'[^{}]*\}")


@dataclass(frozen=True)
class Level:
    """Уровень кадра: ширина PNG, ширины линий (итоговые px) и подписи."""

    name: str
    url: str
    width: int
    road_widths: dict
    casing: float
    casing_max_rank: int
    minor_width: float
    waterway_widths: dict
    rail_width: float
    building_outline: bool
    fonts: dict
    place_kinds: frozenset
    street_max_rank: int
    street_repeat_px: int
    ss: int = 2

    @property
    def height(self):
        """Высота PNG: рамка строго ASPECT:1."""
        return self.width // ASPECT


OVERVIEW = Level(
    name="overview", url=IMAGE_URL, width=2048,
    road_widths={"motorway": 7.0, "trunk": 7.0, "primary": 6.0, "secondary": 5.0,
                 "tertiary": 4.0, "motorway_link": 3.0, "trunk_link": 3.0,
                 "primary_link": 3.0, "secondary_link": 2.6, "tertiary_link": 2.4,
                 "residential": 1.5, "unclassified": 1.5, "living_street": 1.2,
                 "pedestrian": 1.2},
    casing=1.6, casing_max_rank=4, minor_width=0.0,
    waterway_widths={"river": 2.4, "canal": 2.0, "stream": 0.9},
    rail_width=1.4, building_outline=False,
    fonts={"district": 30, "bay": 24, "place": 24, "place_minor": 20, "street": 17},
    place_kinds=frozenset({"city", "town", "suburb", "village", "island"}),
    street_max_rank=2, street_repeat_px=0)
DETAIL = Level(
    name="detail", url=DETAIL_URL, width=6144,
    road_widths={"motorway": 8.0, "trunk": 8.0, "primary": 7.0, "secondary": 6.5,
                 "tertiary": 5.5, "motorway_link": 4.0, "trunk_link": 4.0,
                 "primary_link": 4.0, "secondary_link": 3.8, "tertiary_link": 3.6,
                 "residential": 3.6, "unclassified": 3.6, "living_street": 3.0,
                 "pedestrian": 3.0, "service": 1.8},
    casing=1.6, casing_max_rank=7, minor_width=0.9,
    waterway_widths={"river": 5.0, "canal": 4.0, "stream": 1.8, "drain": 1.3,
                     "ditch": 1.1},
    rail_width=2.2, building_outline=True,
    fonts={"district": 36, "bay": 24, "place": 24, "place_minor": 20, "street": 17},
    place_kinds=frozenset(PLACE_PRIORITY), street_max_rank=MINOR_RANK,
    street_repeat_px=1100)
LEVELS = (OVERVIEW, DETAIL)
FIXED_PALETTE = sorted({WATER, LAND, BUILDING, BUILDING_EDGE, BUILDING_LIGHT, RAIL,
                        MINOR_WAY, TUNNEL, STREET_TEXT, PLACE_TEXT, BAY_TEXT,
                        DISTRICT_TEXT, HALO, *LANDCOVER.values(),
                        *(c for casing, fill, _ in ROAD_CLASSES.values()
                          for c in (casing, fill))})

KNOWN_APPROXIMATIONS = [
    "Площади (здания, леса, парки, водоёмы, landuse, районы) собраны из замкнутых "
    "way и мультиполигонов; relations с неполными членами в выгрузке не собираются.",
    "Суша/вода определяется направлением coastline (суша слева); море повторно "
    "заливается поверх растительности, поэтому отмели за линией берега не видны.",
    "Цвета растительности и landuse обобщены до нескольких классов.",
    "Ширина дорог картографическая по классу, не в масштабе; на обзорном уровне "
    "служебные проезды и пешеходные дорожки не рисуются.",
    "Подписи без пересечений: часть имён не поместилась и не подписана; типовые "
    "слова сокращены (ул., просп.); районы - границы OSM admin_level=9.",
    "Координаты домов в каталоге приближённы (центроид здания OSM или данные "
    "владельца) и не являются геодезическими точками входов.",
    "Два растра одного кадра без тайлов: между целыми зумами Leaflet растр "
    "масштабируется; детализация ограничена детальным уровнем.",
    "PNG с палитрой 256 цветов без дизеринга: на сглаженных краях и подписях "
    "возможна лёгкая ступенчатость оттенков; заливки площадей точные.",
]


class RenderError(Exception):
    """Ожидаемый отказ рендера: reason — код причины для журнала."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


def lonlat_to_mercator(lon, lat):
    """WGS84 (градусы) -> EPSG:3857 (метры, сфера R_EARTH)."""
    x = R_EARTH * math.radians(lon)
    y = R_EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def mercator_to_lonlat(x, y):
    """EPSG:3857 (метры) -> WGS84 (градусы); обратна lonlat_to_mercator."""
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2)
    return lon, lat


def to_mercator(coords):
    """Массив (N, 2) EPSG:3857 для списка [lat, lon] из region.json."""
    arr = np.asarray(coords, dtype=float)
    x = R_EARTH * np.radians(arr[:, 1])
    y = R_EARTH * np.log(np.tan(np.pi / 4 + np.radians(arr[:, 0]) / 2))
    return np.column_stack((x, y))


def zoom_for(m_per_px):
    """Дробный зум Leaflet для масштаба EPSG:3857 (метры на пиксель)."""
    return math.log2(TILE_M_PER_PX_Z0 / m_per_px)


def _number(block, key):
    """Конечное число поля key объекта TS либо None (null или нет поля)."""
    match = re.search(rf"\b{key}:\s*(-?\d+(?:\.\d+)?)\s*,", block)
    if match is None:
        return None
    value = float(match.group(1))
    return value if math.isfinite(value) else None


def parse_houses(ts_path):
    """Дома PILOT_HOUSES из pilotHouses.ts: список (house_id, lat, lon).

    Учитываются только объектные литералы со строковым house_id.
    RenderError, если домов не PILOT_SIZE, id повторяются или у дома
    нет конечных координат: неполный каталог не даёт рамку карты.
    """
    text = Path(ts_path).read_text(encoding="utf-8")
    houses = []
    for block in HOUSE_BLOCK_RE.findall(text):
        house_id = re.search(r"house_id:\s*'([^']+)'", block).group(1)
        lat, lon = _number(block, "lat"), _number(block, "lon")
        if lat is None or lon is None:
            raise RenderError("invalid_house_catalog",
                              f"{house_id}: нет конечных координат lat/lon")
        houses.append((house_id, lat, lon))
    ids = {house_id for house_id, _, _ in houses}
    if len(houses) != PILOT_SIZE or len(ids) != PILOT_SIZE:
        raise RenderError("invalid_house_catalog",
                          f"ожидалось {PILOT_SIZE} уникальных домов, "
                          f"получено {len(houses)} (уникальных {len(ids)})")
    return houses


def compute_frame(houses):
    """Рамка EPSG:3857 (xmin, ymin, xmax, ymax) строго ASPECT:1.

    Охват 20 домов с отступом PAD_M симметрично расширяется вокруг центра
    по одной оси до соотношения ширина:высота = ASPECT.
    """
    pts = [lonlat_to_mercator(lon, lat) for _, lat, lon in houses]
    xmin = min(x for x, _ in pts) - PAD_M
    xmax = max(x for x, _ in pts) + PAD_M
    ymin = min(y for _, y in pts) - PAD_M
    ymax = max(y for _, y in pts) + PAD_M
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    half_w = max(xmax - xmin, ASPECT * (ymax - ymin)) / 2
    half_h = half_w / ASPECT
    return cx - half_w, cy - half_h, cx + half_w, cy + half_h


def sha256_file(path):
    """sha256 файла в нижнем регистре hex."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_font(path, size):
    """TrueType-шрифт размера size; RenderError с подсказкой, если файла нет."""
    if not Path(path).is_file():
        raise RenderError("font_not_found",
                          f"шрифт не найден: {path}; передайте путь к TTF "
                          "с кириллицей через --font / --font-bold")
    return ImageFont.truetype(path, size)


def _bounds(arr):
    """bbox массива EPSG:3857: (xmin, ymin, xmax, ymax)."""
    return (float(arr[:, 0].min()), float(arr[:, 1].min()),
            float(arr[:, 0].max()), float(arr[:, 1].max()))


def _ring_area(arr):
    """Площадь кольца по формуле шнурования, м^2 EPSG:3857."""
    x, y = arr[:, 0], arr[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2


def prepare_region(region, frame):
    """Объекты region.json в EPSG:3857, отобранные по пересечению с рамкой."""
    fx0, fy0, fx1, fy1 = frame

    def near(bounds):
        return bounds[0] <= fx1 and bounds[2] >= fx0 and bounds[1] <= fy1 and bounds[3] >= fy0

    areas = []
    for item in region["areas"]:
        polygons = [[to_mercator(ring) for ring in rings] for rings in item["polygons"]
                    if len(rings[0]) >= 4]
        if not polygons:
            continue
        bounds = _bounds(np.vstack([rings[0] for rings in polygons]))
        if near(bounds):
            areas.append({"layer": item["layer"], "name": item.get("name"),
                          "polygons": polygons, "bounds": bounds,
                          "area": sum(_ring_area(rings[0]) for rings in polygons)})
    lines = {}
    for layer in ("roads", "waterways", "railways"):
        lines[layer] = []
        for item in region[layer]:
            arr = to_mercator(item["coords"])
            if near(_bounds(arr)):
                lines[layer].append((item, arr))
    coast = [to_mercator(c) for c in region["coastline"] if len(c) >= 2]
    return {"areas": areas, "coastline": coast, **lines,
            "labels": [lb for lb in region["labels"]]}


def classify_coast(coastline, frame_rect, seeds):
    """Грани рамки, разрезанной coastline, с классом суша/вода.

    По соглашению OSM суша слева от направления coastline. Каждый сегмент
    голосует своей длиной: точка слева - за сушу грани, справа - за воду.
    Грань без голосов - вода при семени bay/strait внутри, иначе суша.
    Возвращает [(polygon, is_land)] и счётчики диагностики.
    """
    directed = [[tuple(p) for p in arr.tolist()] for arr in coastline]
    clipped = unary_union([LineString(c) for c in directed]).intersection(frame_rect)
    linework = unary_union([clipped, frame_rect.exterior])
    faces = [g for g in polygonize(linework) if g.area > 1.0]
    xmin, ymin, xmax, ymax = frame_rect.bounds
    points, sides, weights = [], [], []
    for way in directed:
        for (x1, y1), (x2, y2) in itertools.pairwise(way):
            length = math.hypot(x2 - x1, y2 - y1)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if length == 0 or not (xmin < mx < xmax and ymin < my < ymax):
                continue
            k = min(VOTE_OFFSET_M, length / 4) / length
            nx, ny = -(y2 - y1) * k, (x2 - x1) * k
            points += [(mx + nx, my + ny), (mx - nx, my - ny)]
            sides += [True, False]
            weights += [length, length]
    votes = [[0.0, 0.0] for _ in faces]
    if points and faces:
        hits = shapely.STRtree(faces).query(shapely.points(points), predicate="within")
        for point_idx, face_idx in zip(*hits.tolist(), strict=True):
            votes[face_idx][0 if sides[point_idx] else 1] += weights[point_idx]
    stats = {"faces": len(faces), "by_votes": 0, "by_seed": 0, "by_default": 0,
             "mixed_votes": 0, "seed_conflicts": 0}
    classes = []
    for face, (land_w, water_w) in zip(faces, votes, strict=True):
        if land_w + water_w > 0:
            stats["by_votes"] += 1
            stats["mixed_votes"] += min(land_w, water_w) > 0.05 * (land_w + water_w)
            classes.append(land_w > water_w)
        elif any(face.contains(seed) for seed in seeds):
            stats["by_seed"] += 1
            classes.append(False)
        else:
            stats["by_default"] += 1
            classes.append(True)
    pairs = list(zip(faces, classes, strict=True))
    for seed in seeds:
        stats["seed_conflicts"] += any(land and f.contains(seed) for f, land in pairs)
    stats["open_ends"] = _open_ends(clipped, frame_rect)
    stats["land_area_share"] = round(
        sum(f.area for f, land in pairs if land) / frame_rect.area, 4)
    return pairs, stats


def _open_ends(clipped, frame_rect):
    """Число концов coastline внутри рамки (разрывы береговой линии)."""
    if clipped.is_empty:
        return 0
    merged = linemerge(clipped)
    count = 0
    for line in getattr(merged, "geoms", [merged]):
        if line.is_ring:
            continue
        for end in (Point(line.coords[0]), Point(line.coords[-1])):
            count += frame_rect.exterior.distance(end) > 1.0
    return count


def _shapely_polygons(polygons):
    """Полигоны shapely (с дырами) из колец EPSG:3857; невалидные чинятся."""
    shapes = []
    for rings in polygons:
        poly = Polygon(rings[0], [r for r in rings[1:] if len(r) >= 4])
        shapes.append(poly if poly.is_valid else shapely.make_valid(poly))
    return unary_union(shapes)


def check_houses(houses, faces, water_areas, frame_rect):
    """Число домов на суше; RenderError, если дом вне рамки или в воде."""
    land = unary_union([f for f, is_land in faces if is_land])
    water = unary_union([_shapely_polygons(a["polygons"]) for a in water_areas])
    for house_id, lat, lon in houses:
        pt = Point(lonlat_to_mercator(lon, lat))
        if not frame_rect.contains(pt):
            raise RenderError("house_outside_frame", f"{house_id} вне рамки карты")
        if not land.contains(pt) or water.contains(pt):
            raise RenderError("house_in_water", f"{house_id} попадает в воду")
    return len(houses)


class Canvas:
    """Холст суперсэмплинга уровня и проекция EPSG:3857 -> пиксели холста."""

    def __init__(self, frame, level):
        self.xmin, self.ymin, self.xmax, self.ymax = frame
        self.level = level
        self.w = level.width * level.ss
        self.h = level.height * level.ss
        self.scale = self.w / (self.xmax - self.xmin)
        self.img = Image.new("RGB", (self.w, self.h), WATER)
        self.draw = ImageDraw.Draw(self.img)

    def px(self, arr):
        """Массив (N, 2) пикселей холста для массива EPSG:3857."""
        out = np.empty_like(arr)
        out[:, 0] = (arr[:, 0] - self.xmin) * self.scale
        out[:, 1] = (self.ymax - arr[:, 1]) * self.scale
        return out

    def point(self, x, y):
        """Пиксель холста для точки EPSG:3857."""
        return (x - self.xmin) * self.scale, (self.ymax - y) * self.scale

    def width(self, final_px):
        """Целая ширина линии на холсте для ширины в итоговых пикселях."""
        return max(1, round(final_px * self.level.ss))

    def line(self, arr, final_px, color):
        """Линия по массиву EPSG:3857 шириной final_px итоговых пикселей."""
        width = self.width(final_px)
        self.draw.line(self.px(arr).ravel().tolist(), fill=color, width=width,
                       joint="curve" if width > 2 else None)

    def fill(self, rings, color, outline=None):
        """Полигон с дырами: без дыр - напрямую, с дырами - через маску bbox."""
        pts = [self.px(r) for r in rings]
        if len(pts) == 1:
            self.draw.polygon(pts[0].ravel().tolist(), fill=color, outline=outline)
            return
        x0, y0 = (max(0, math.floor(v)) for v in pts[0].min(axis=0))
        x1 = min(self.w, math.ceil(pts[0][:, 0].max()) + 1)
        y1 = min(self.h, math.ceil(pts[0][:, 1].max()) + 1)
        if x1 > x0 and y1 > y0:
            mask = Image.new("L", (x1 - x0, y1 - y0), 0)
            md = ImageDraw.Draw(mask)
            for i, p in enumerate(pts):
                md.polygon((p - (x0, y0)).ravel().tolist(), fill=0 if i else 255)
            self.img.paste(color, (x0, y0, x1, y1), mask)
        if outline:
            for p in pts:
                self.draw.line(p.ravel().tolist(), fill=outline, width=1)


def abbreviate(name):
    """Короткая подпись улицы: типовые слова заменяются сокращениями."""
    for word, short in STREET_ABBREVIATIONS.items():
        name = re.sub(rf"(?<!\w){word}(?!\w)", short, name)
    return name


def district_text(name):
    """Подпись района: прописные буквы вразрядку, «район» второй строкой."""
    base = re.sub(r"\s*район.*$", "", name, flags=re.IGNORECASE).strip() or name
    spaced = [" ".join("\u2009".join(word) for word in line.upper().split())
              for line in ((base, "район") if base != name else (name,))]
    return "\n".join(spaced)


def text_image(text, font, fill, stroke):
    """RGBA-изображение (многострочной) подписи с белым ореолом."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = probe.multiline_textbbox(
        (0, 0), text, font=font, stroke_width=stroke, align="center")
    img = Image.new("RGBA", (math.ceil(right - left) + 2, math.ceil(bottom - top) + 2),
                    (0, 0, 0, 0))
    ImageDraw.Draw(img).multiline_text(
        (1 - left, 1 - top), text, font=font, fill=fill, stroke_width=stroke,
        stroke_fill=HALO, align="center")
    return img


class LabelPlacer:
    """Подписи с ореолом и запретом пересечения повёрнутых рамок."""

    def __init__(self, cv):
        self.cv = cv
        self.ss = cv.level.ss
        self.placed = []
        self.by_text = {}
        margin = 4 * self.ss
        self.inner = box(margin, margin, cv.w - margin, cv.h - margin)

    def try_place(self, text, font, fill, center, angle):
        """Ставит подпись, если рамка внутри холста и ни с чем не пересекается."""
        img = text_image(text, font, fill, max(1, round(1.6 * self.ss)))
        w, h = img.size
        cx, cy = center
        pad = 2 * self.ss
        footprint = affinity.rotate(
            box(cx - w / 2 - pad, cy - h / 2 - pad, cx + w / 2 + pad, cy + h / 2 + pad),
            -angle, origin=(cx, cy))
        if not self.inner.contains(footprint):
            return False
        if self.placed and shapely.intersects(self.placed, footprint).any():
            return False
        if angle:
            img = img.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        self.cv.img.paste(img, (round(cx - img.width / 2), round(cy - img.height / 2)), img)
        self.placed.append(footprint)
        return True

    def _glyph_layout(self, text, font, line, t):
        """Центры и углы глифов подписи по кривой либо None, если не ложится.

        Подпись читается слева направо; соседние глифы поворачиваются не
        более чем на MAX_GLYPH_TURN, общий наклон не переворачивает текст.
        """
        total = font.getlength(text)
        start = t - total / 2
        if start < 0 or start + total > line.length:
            return None
        if line.interpolate(start + total).x < line.interpolate(start).x:
            line = LineString(line.coords[::-1])
            start = line.length - start - total
        step = font.size * 0.5
        layout, prev = [], None
        for i, ch in enumerate(text):
            d = start + (font.getlength(text[:i]) + font.getlength(text[:i + 1])) / 2
            a, b = line.interpolate(max(0.0, d - step)), line.interpolate(d + step)
            angle = math.degrees(math.atan2(-(b.y - a.y), b.x - a.x))
            if abs(angle) > 100 or (prev is not None and abs(angle - prev) > MAX_GLYPH_TURN):
                return None
            p = line.interpolate(d)
            layout.append((ch, p.x, p.y, angle))
            prev = angle
        return layout, substring(line, start, start + total)

    def place_on_path(self, text, font, fill, line, t, gap):
        """Подпись по кривой с центром на расстоянии t; та же подпись не ближе gap."""
        result = self._glyph_layout(text, font, line, t)
        if result is None:
            return False
        layout, piece = result
        footprint = piece.buffer(font.size * 0.6 + 2 * self.ss, cap_style="flat")
        if not self.inner.contains(footprint):
            return False
        if self.placed and shapely.intersects(self.placed, footprint).any():
            return False
        same = self.by_text.setdefault(text, [])
        if same and shapely.distance(same, footprint).min() < gap:
            return False
        same.append(footprint)
        stroke = max(1, round(1.6 * self.ss))
        side = 2 * font.size + 2 * stroke
        for layer in ("halo", "glyph"):
            for ch, x, y, angle in layout:
                img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                if layer == "halo":
                    draw.text((side / 2, side / 2), ch, font=font, fill=HALO, anchor="mm",
                              stroke_width=stroke, stroke_fill=HALO)
                else:
                    draw.text((side / 2, side / 2), ch, font=font, fill=fill, anchor="mm")
                img = img.rotate(angle, resample=Image.Resampling.BICUBIC)
                self.cv.img.paste(img, (round(x - side / 2), round(y - side / 2)), img)
        self.placed.append(footprint)
        return True

    def place_along(self, text, font, fill, line, repeat):
        """Подписи по кривой: одна (repeat=0) или по одной на отрезок repeat px."""
        if line.length < font.getlength(text) * 1.1:
            return 0
        if not repeat:
            return int(any(self.place_on_path(text, font, fill, line, line.length * f, 0)
                           for f in (0.5, 0.35, 0.65, 0.2, 0.8)))
        count = max(1, int(line.length // repeat))
        span = line.length / count
        placed = 0
        for k in range(count):
            centre = span * (k + 0.5)
            placed += any(self.place_on_path(text, font, fill, line, centre + shift * span,
                                             repeat * 0.6)
                          for shift in (0.0, -0.25, 0.25))
        return placed


def _heading(a, b):
    """Направление отрезка a -> b в градусах."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _turn(h1, h2):
    """Абсолютный поворот между направлениями, градусы в [0, 180]."""
    return abs((h2 - h1 + 180) % 360 - 180)


def build_strokes(parts):
    """Штрихи для подписей: way одного имени сцепляются с наименьшим поворотом.

    На стыке выбирается продолжение с поворотом не более MAX_STROKE_TURN;
    так двойные проезжие части и развилки не рвут улицу на короткие куски.
    """
    def key(p):
        return round(p[0], 1), round(p[1], 1)

    loops = [LineString(p) for p in parts if len(p) >= 3 and key(p[0]) == key(p[-1])]
    parts = [p for p in parts if len(p) >= 2 and key(p[0]) != key(p[-1])]
    ends = {}
    for i, pts in enumerate(parts):
        for end in (pts[0], pts[-1]):
            ends.setdefault(key(end), []).append(i)
    used = [False] * len(parts)
    strokes = []
    for i in sorted(range(len(parts)), key=lambda i: -LineString(parts[i]).length):
        if used[i]:
            continue
        used[i] = True
        stroke = list(parts[i])
        for forward in (True, False):
            while True:
                tail, prev = (stroke[-1], stroke[-2]) if forward else (stroke[0], stroke[1])
                heading = _heading(prev, tail)
                best = None
                for j in ends.get(key(tail), []):
                    if used[j]:
                        continue
                    pts = parts[j] if key(parts[j][0]) == key(tail) else parts[j][::-1]
                    turn = _turn(heading, _heading(pts[0], pts[1]))
                    if turn <= MAX_STROKE_TURN and (best is None or turn < best[0]):
                        best = (turn, j, pts)
                if best is None:
                    break
                used[best[1]] = True
                if forward:
                    stroke.extend(best[2][1:])
                else:
                    stroke[:0] = best[2][::-1][:-1]
        strokes.append(LineString(stroke))
    return sorted(strokes + loops, key=lambda g: -g.length)


def _area_label_points(area, land, weights):
    """Точки подписи площади на суше: части по убыванию числа зданий, затем площади.

    weights: (xs, ys) центров зданий EPSG:3857; полюс недоступности каждой части.
    """
    shape = _shapely_polygons(area["polygons"]).intersection(land)
    polys = [g for g in getattr(shape, "geoms", [shape])
             if not g.is_empty and g.geom_type == "Polygon"]
    xs, ys = weights
    ranked = sorted(polys, key=lambda g: (-int(shapely.contains_xy(g, xs, ys).sum()),
                                          -g.area))
    return [polylabel(g, tolerance=max(1.0, math.sqrt(g.area) / 200)) for g in ranked]


def place_labels(cv, data, land, fonts):
    """Подписи по приоритету: районы, бухты и острова, места, улицы."""
    level = cv.level
    placer = LabelPlacer(cv)
    counts = {"district_labels": 0, "bay_labels": 0, "place_labels": 0,
              "street_labels": 0}
    centres = np.array([[(a["bounds"][0] + a["bounds"][2]) / 2,
                         (a["bounds"][1] + a["bounds"][3]) / 2]
                        for a in data["areas"] if a["layer"] == "building"]).reshape(-1, 2)
    weights = (centres[:, 0], centres[:, 1])
    for area in data["areas"]:
        if area["layer"] != "district" or not area["name"]:
            continue
        counts["district_labels"] += any(
            placer.try_place(district_text(area["name"]), fonts["district"],
                             DISTRICT_TEXT, cv.point(p.x, p.y), 0.0)
            for p in _area_label_points(area, land, weights))

    island_names = set()
    frame_rect = box(cv.xmin, cv.ymin, cv.xmax, cv.ymax)
    for area in data["areas"]:
        if area["layer"] == "island" and area["name"] and "island" in level.place_kinds:
            points = _area_label_points(area, frame_rect, weights)[:1]
            if any(placer.try_place(area["name"], fonts["place_minor"], PLACE_TEXT,
                                    cv.point(p.x, p.y), 0.0) for p in points):
                counts["place_labels"] += 1
                island_names.add(area["name"])
    labels = sorted(data["labels"], key=lambda lb: (
        0 if lb["kind"] in ("bay", "strait") else 1 + PLACE_PRIORITY.get(lb["kind"], 9),
        lb["name"], lb["lat"], lb["lon"]))
    for lb in labels:
        is_bay = lb["kind"] in ("bay", "strait")
        if not is_bay and (lb["kind"] not in level.place_kinds or lb["name"] in island_names):
            continue
        center = cv.point(*lonlat_to_mercator(lb["lon"], lb["lat"]))
        major = PLACE_PRIORITY.get(lb["kind"], 9) <= 1
        font = fonts["bay"] if is_bay else fonts["place" if major else "place_minor"]
        ok = placer.try_place(lb["name"], font, BAY_TEXT if is_bay else PLACE_TEXT,
                              center, 0.0)
        counts["bay_labels" if is_bay else "place_labels"] += ok

    by_name = {}
    for item, arr in data["roads"]:
        rank = ROAD_CLASSES[item["cls"]][2] if item["cls"] in ROAD_CLASSES else MINOR_RANK
        if item["name"] and rank <= level.street_max_rank and not item["tunnel"]:
            entry = by_name.setdefault(item["name"], [MINOR_RANK + 1, []])
            entry[0] = min(entry[0], rank)
            entry[1].append(cv.px(arr).tolist())
    candidates = []
    for name, (rank, parts) in by_name.items():
        lines = build_strokes(parts)
        if lines:
            candidates.append((rank, -sum(g.length for g in lines), name, lines))
    candidates.sort(key=lambda c: c[:3])
    repeat = level.street_repeat_px * level.ss
    for _, _, name, lines in candidates:
        text = abbreviate(name)
        for line in lines[:3] if not repeat else lines:
            placed = placer.place_along(text, fonts["street"], STREET_TEXT, line, repeat)
            counts["street_labels"] += placed
            if placed and not repeat:
                break
    counts["street_names"] = len(by_name)
    return counts


def render_level(data, faces, frame, level, font_paths):
    """RGB-изображение уровня: слои по порядку, затем подписи; и счётчики."""
    regular, bold = font_paths
    size = {role: px * level.ss for role, px in level.fonts.items()}
    fonts = {"district": load_font(bold, size["district"]),
             "bay": load_font(bold, size["bay"]),
             "place": load_font(bold, size["place"]),
             "place_minor": load_font(regular, size["place_minor"]),
             "street": load_font(regular, size["street"])}
    cv = Canvas(frame, level)
    for face, is_land in sorted(faces, key=lambda pair: -pair[0].area):
        cv.fill([np.asarray(face.exterior.coords)], LAND if is_land else WATER)
    counts = {}
    by_layer = {}
    for area in data["areas"]:
        by_layer.setdefault(area["layer"], []).append(area)
    cover = sorted((a for a in data["areas"] if a["layer"] in LANDCOVER),
                   key=lambda a: -a["area"])
    for area in cover:
        for rings in area["polygons"]:
            cv.fill(rings, LANDCOVER[area["layer"]])
    counts["landcover"] = len(cover)
    for face, is_land in faces:
        if not is_land:
            rings = [np.asarray(face.exterior.coords)]
            rings += [np.asarray(r.coords) for r in face.interiors]
            cv.fill(rings, WATER)
    water = sorted(by_layer.get("water", []), key=lambda a: -a["area"])
    for area in water:
        for rings in area["polygons"]:
            cv.fill(rings, WATER)
    counts["water_areas"] = len(water)
    for item, arr in data["waterways"]:
        width = level.waterway_widths.get(item["cls"])
        if width:
            cv.line(arr, width, WATER)
    buildings = by_layer.get("building", [])
    for area in buildings:
        for rings in area["polygons"]:
            if level.building_outline:
                cv.fill(rings, BUILDING, BUILDING_EDGE)
            else:
                cv.fill(rings, BUILDING_LIGHT)
    counts["buildings"] = len(buildings)
    for item, arr in data["railways"]:
        cv.line(arr, level.rail_width * (0.6 if item["service"] else 1.0), RAIL)
    counts.update(_draw_roads(cv, data["roads"]))
    land = unary_union([f for f, is_land in faces if is_land])
    counts.update(place_labels(cv, data, land, fonts))
    final = cv.img.resize((level.width, level.height), Image.Resampling.LANCZOS)
    return final, counts


def _draw_roads(cv, roads):
    """Дороги уровня: тонкие второстепенные, затем обводки и заливки по классу."""
    level = cv.level
    major, minor = [], []
    for item, arr in roads:
        if item["cls"] in level.road_widths:
            major.append((level.road_widths[item["cls"]], item, arr))
        elif item["cls"] not in ROAD_CLASSES and level.minor_width:
            minor.append(arr)
    major.sort(key=lambda entry: entry[0])
    for arr in minor:
        cv.line(arr, level.minor_width, MINOR_WAY)
    for width, item, arr in major:
        casing, _, rank = ROAD_CLASSES[item["cls"]]
        if not item["tunnel"] and rank <= level.casing_max_rank:
            cv.line(arr, width + level.casing, casing)
    for width, item, arr in major:
        color = TUNNEL if item["tunnel"] else ROAD_CLASSES[item["cls"]][1]
        cv.line(arr, width, color)
    return {"roads_drawn": len(major), "minor_ways_drawn": len(minor)}


def quantize(img):
    """Палитра 256 цветов без дизеринга: FIXED_PALETTE + адаптивные (median cut).

    Каждый уникальный цвет отображается в ближайший цвет палитры (евклидова
    метрика RGB, при равенстве - меньший индекс), поэтому цвета заливок из
    FIXED_PALETTE сохраняются точно.
    """
    adaptive = img.quantize(colors=256 - len(FIXED_PALETTE),
                            method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    extra = adaptive.getpalette()[: 3 * (256 - len(FIXED_PALETTE))]
    palette = np.array([c for rgb in FIXED_PALETTE for c in rgb] + extra,
                       dtype=np.int32).reshape(-1, 3)
    rgb = np.asarray(img.convert("RGB"), dtype=np.int32)
    keys = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    uniq, inverse = np.unique(keys.ravel(), return_inverse=True)
    colors = np.stack(((uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255), axis=1)
    nearest = np.empty(len(uniq), dtype=np.uint8)
    for start in range(0, len(uniq), 4096):
        delta = colors[start:start + 4096, None, :] - palette[None, :, :]
        nearest[start:start + 4096] = np.argmin((delta * delta).sum(axis=2), axis=1)
    out = Image.frombytes("P", img.size, nearest[inverse].astype(np.uint8).tobytes())
    out.putpalette(palette.astype(np.uint8).ravel().tolist())
    return out


def tool_versions(font_paths):
    """Версии инструментов и имена/sha256 шрифтов без абсолютных путей."""
    return {
        "python": platform.python_version(),
        "osmium": importlib.metadata.version("osmium"),
        "shapely": importlib.metadata.version("shapely"),
        "pillow": importlib.metadata.version("pillow"),
        "numpy": importlib.metadata.version("numpy"),
        "fonts": [{"role": role, "file": Path(path).name, "sha256": sha256_file(path)}
                  for role, path in font_paths],
    }


def zoom_levels(frame):
    """Зумы уровней и границы переключения по масштабу EPSG:3857."""
    span = frame[2] - frame[0]
    z_overview = zoom_for(span / OVERVIEW.width)
    z_detail = zoom_for(span / DETAIL.width)
    detail_min = math.floor(z_overview + math.log2(OVERVIEW_STRETCH_LIMIT)) + 1
    max_zoom = math.floor(z_detail + 1)
    if detail_min > max_zoom:
        raise RenderError("zoom_levels_invalid", "detail.min_zoom больше max_zoom")
    return {"overview": z_overview, "detail": z_detail, "detail_min_zoom": detail_min,
            "max_zoom": max_zoom}


def build_manifest(frame, paths, levels, extra):
    """Manifest L.imageOverlay: bounds, уровни, зумы, источник, воспроизведение.

    paths: png, detail_png, pbf, region; в manifest только имена и sha256.
    levels: сводка уровней; extra: tools, coast, houses_on_land, zooms.
    """
    xmin, ymin, xmax, ymax = frame
    west, south = mercator_to_lonlat(xmin, ymin)
    east, north = mercator_to_lonlat(xmax, ymax)
    zooms = extra["zooms"]
    cos_c = math.cos(math.radians((south + north) / 2))
    py = "map-preparation\\.venv\\Scripts\\python.exe"
    return {
        "image": IMAGE_URL,
        "crs": "EPSG:3857",
        "width": OVERVIEW.width,
        "height": OVERVIEW.height,
        "bounds": {"south": south, "west": west, "north": north, "east": east},
        "projected_bounds": {"min_x": xmin, "min_y": ymin, "max_x": xmax, "max_y": ymax},
        "image_sha256": sha256_file(paths["png"]),
        "detail": {
            "image": DETAIL_URL, "width": DETAIL.width, "height": DETAIL.height,
            "image_sha256": sha256_file(paths["detail_png"]),
            "min_zoom": zooms["detail_min_zoom"],
        },
        "max_zoom": zooms["max_zoom"],
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
        "license_url": "https://opendatacommons.org/licenses/odbl/1-0/",
        "source": {
            "pbf_name": Path(paths["pbf"]).name,
            "pbf_sha256": sha256_file(paths["pbf"]),
            "pbf_size_bytes": Path(paths["pbf"]).stat().st_size,
        },
        "commands": [
            "py -3.13 -m venv map-preparation\\.venv",
            f"{py} -m pip install -r requirements-map.txt",
            "$env:PYTHONPATH = (Get-Location).Path",
            f"{py} map-preparation\\extract_region.py <PBF> {EXTRACT_BBOX_ARGS} "
            "map-preparation\\region.json",
            f"{py} map-preparation\\render_map.py map-preparation\\region.json "
            "frontend\\src\\features\\dossier\\pilotHouses.ts <PBF> "
            "output\\maps\\vladivostok-pilot.png output\\maps\\vladivostok-pilot-detail.png "
            "output\\maps\\vladivostok-pilot.manifest.json "
            "--font <FONT_REGULAR> --font-bold <FONT_BOLD>",
        ],
        "tools": extra["tools"],
        "known_approximations": KNOWN_APPROXIMATIONS,
        "render_notes": {
            "projection": "Web Mercator, сфера R=6378137 м, y растёт к северу",
            "frame": f"охват 20 домов + {PAD_M:g} м EPSG:3857, симметрично расширен "
                     f"вокруг центра до {ASPECT}:1",
            "zoom_formula": "z = log2(156543.03392 * cos(lat_center) / "
                            "ground_meters_per_pixel)",
            "detail_min_zoom_rule": "первый целый зум, где обзорный уровень растянут "
                                    f"более чем в {OVERVIEW_STRETCH_LIMIT:g} раза",
            "max_zoom_rule": "целая часть (зум детального уровня + 1)",
            "levels": {
                level.name: {
                    "image": level.url, "width": level.width, "height": level.height,
                    "meters_per_pixel_epsg3857": (xmax - xmin) / level.width,
                    "ground_meters_per_pixel_at_center": (xmax - xmin) / level.width * cos_c,
                    "zoom": zooms[level.name],
                    **levels[level.name],
                } for level in LEVELS
            },
            "supersampling": OVERVIEW.ss,
            "extract_bbox": EXTRACT_BBOX_ARGS,
            "region_json_sha256": sha256_file(paths["region"]),
            "coastline": extra["coast"],
            "houses_on_land": extra["houses_on_land"],
            "road_width": "картографическая по классу дороги, не метрическая",
            "street_abbreviations": STREET_ABBREVIATIONS,
        },
    }


def _load_region(path):
    """region.json формата REGION_FORMAT либо RenderError."""
    try:
        region = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RenderError("region_read_failed", f"region.json не прочитан: {exc}") from exc
    if region.get("format") != REGION_FORMAT:
        raise RenderError("region_format_unsupported",
                          f"нужен region.json формата {REGION_FORMAT}; "
                          "повторите extract_region.py")
    return region


def render_files(args):
    """Рендер двух PNG и manifest по аргументам CLI; сводка для журнала.

    Ожидаемые отказы входа, проверок и записи — RenderError с кодом причины.
    """
    font_paths = (args.font, args.font_bold)
    for path in font_paths:
        load_font(path, 10)
    if not Path(args.pbf).is_file():
        raise RenderError("pbf_not_found", f"PBF не найден: {args.pbf}")
    region = _load_region(args.region)
    try:
        houses = parse_houses(args.houses)
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError("houses_read_failed", f"каталог домов не прочитан: {exc}") from exc
    frame = compute_frame(houses)
    west, south = mercator_to_lonlat(frame[0], frame[1])
    east, north = mercator_to_lonlat(frame[2], frame[3])
    e_west, e_south, e_east, e_north = region["bbox"]
    if not (e_west <= west and e_south <= south and east <= e_east and north <= e_north):
        raise RenderError("frame_outside_region",
                          "рамка карты выходит за bbox region.json; "
                          "повторите extract_region.py с большим bbox")
    zooms = zoom_levels(frame)
    data = prepare_region(region, frame)
    frame_rect = box(*frame)
    seeds = [Point(lonlat_to_mercator(lb["lon"], lb["lat"]))
             for lb in data["labels"] if lb["kind"] in ("bay", "strait")]
    faces, coast = classify_coast(data["coastline"], frame_rect, seeds)
    water_areas = [a for a in data["areas"] if a["layer"] == "water"]
    houses_on_land = check_houses(houses, faces, water_areas, frame_rect)

    levels = {}
    outputs = {OVERVIEW.name: args.out_png, DETAIL.name: args.out_detail_png}
    for level in LEVELS:
        image, counts = render_level(data, faces, frame, level, font_paths)
        out = outputs[level.name]
        try:
            quantize(image).save(out, optimize=True)
        except OSError as exc:
            raise RenderError("output_write_failed", f"PNG не записан: {exc}") from exc
        png_bytes = Path(out).stat().st_size
        if png_bytes > MAX_PNG_BYTES:
            raise RenderError("png_too_large",
                              f"{Path(out).name}: {png_bytes} байт > {MAX_PNG_BYTES}")
        levels[level.name] = {"png_bytes": png_bytes, "palette_colors": 256,
                              "drawn": counts}
        _logger.info("MAP_RENDER_LEVEL_COMPLETED", "map level written",
                     level=level.name, png_name=Path(out).name, width=level.width,
                     height=level.height, png_bytes=png_bytes,
                     image_sha256=sha256_file(out), drawn=counts)

    tools = tool_versions([("regular", args.font), ("bold", args.font_bold)])
    paths = {"png": args.out_png, "detail_png": args.out_detail_png, "pbf": args.pbf,
             "region": args.region}
    extra = {"tools": tools, "coast": coast, "houses_on_land": houses_on_land,
             "zooms": zooms}
    manifest = build_manifest(frame, paths, levels, extra)
    try:
        Path(args.out_manifest).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RenderError("output_write_failed", f"manifest не записан: {exc}") from exc
    return {
        "manifest_name": Path(args.out_manifest).name,
        "manifest_sha256": sha256_file(args.out_manifest),
        "image_sha256": manifest["image_sha256"],
        "detail_image_sha256": manifest["detail"]["image_sha256"],
        "bounds": {"south": south, "west": west, "north": north, "east": east},
        "zooms": zooms,
        "coastline": coast,
        "houses_on_land": houses_on_land,
    }


def main():
    """CLI: рендер двух PNG и manifest; события MAP_RENDER_* в журнал карты.

    Журнал настраивается до разбора аргументов (fail-fast). Ожидаемый отказ —
    событие и SystemExit с текстом; непредвиденный пробрасывается после события.
    """
    setup_logging(load_logging_settings(ServiceName.MAP))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("region", "houses", "pbf", "out_png", "out_detail_png", "out_manifest"):
        parser.add_argument(name)
    parser.add_argument("--font", default=DEFAULT_FONT)
    parser.add_argument("--font-bold", default=DEFAULT_FONT_BOLD)
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        if exc.code not in (0, None):
            _logger.error("MAP_RENDER_FAILED", "render failed", reason="invalid_arguments")
        raise

    _logger.info("MAP_RENDER_STARTED", "render started",
                 region_name=Path(args.region).name, houses_name=Path(args.houses).name,
                 pbf_name=Path(args.pbf).name)
    try:
        summary = render_files(args)
    except RenderError as exc:
        _logger.error("MAP_RENDER_FAILED", "render failed", reason=exc.reason)
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        _logger.error("MAP_RENDER_FAILED", "render failed",
                      reason="render_failed", error_type=type(exc).__name__)
        raise
    _logger.info("MAP_RENDER_COMPLETED", "map images and manifest written", **summary)


if __name__ == "__main__":
    main()
