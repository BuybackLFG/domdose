"""Рендер offline-подложки пилотной зоны Владивостока в PNG и manifest.

Читает region.json (extract_region.py) и каталог pilotHouses.ts, строит
рамку EPSG:3857 по 20 домам с отступом PAD_M, рисует слои Pillow с
суперсэмплингом и пишет manifest для L.imageOverlay без абсолютных путей.

Использование (из корня репозитория, PYTHONPATH = корень):
    python render_map.py <region.json> <pilotHouses.ts> <PBF> <out.png>
        <out.manifest.json> [--font <FONT>] [--font-bold <FONT_BOLD>]
"""

import argparse
import hashlib
import importlib.metadata
import itertools
import json
import math
import platform
import re
from pathlib import Path

import shapely
from PIL import Image, ImageDraw, ImageFont
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.ops import linemerge, polygonize, substring, unary_union

from core.logging import ServiceName, get_logger, load_logging_settings, setup_logging

_logger = get_logger("map-preparation.render_map", service=ServiceName.MAP)

R_EARTH = 6378137.0
PILOT_SIZE = 20
PAD_M = 1500.0
WIDTH = 2048
SS = 2
VOTE_OFFSET_M = 0.25
IMAGE_URL = "/maps/vladivostok-pilot.png"
DEFAULT_FONT = r"C:\Windows\Fonts\arial.ttf"
DEFAULT_FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
EXTRACT_BBOX_ARGS = "131.848 43.0835 132.0715 43.2954"

WATER = (170, 211, 223)
LAND = (242, 239, 233)
PARK = (205, 235, 176)
BUILDING = (217, 208, 201)
BUILDING_EDGE = (196, 186, 177)
RAIL = (140, 140, 140)
MINOR_WAY = (212, 196, 186)
STREET_TEXT = (72, 72, 92)
PLACE_TEXT = (50, 50, 50)
BAY_TEXT = (38, 88, 140)
HALO = (255, 255, 255)

# Класс дороги: (ширина заливки в итоговых px, обводка, заливка, ранг подписи).
ROAD_STYLES = {
    "motorway": (3.6, (200, 78, 87), (232, 146, 162), 0),
    "trunk": (3.6, (200, 78, 87), (232, 146, 162), 0),
    "primary": (3.2, (193, 126, 71), (252, 214, 164), 1),
    "secondary": (2.8, (160, 158, 100), (247, 250, 191), 2),
    "tertiary": (2.4, (170, 170, 170), (255, 255, 255), 3),
    "motorway_link": (2.0, (200, 78, 87), (232, 146, 162), 4),
    "trunk_link": (2.0, (200, 78, 87), (232, 146, 162), 4),
    "primary_link": (2.0, (193, 126, 71), (252, 214, 164), 4),
    "secondary_link": (1.8, (160, 158, 100), (247, 250, 191), 4),
    "tertiary_link": (1.8, (170, 170, 170), (255, 255, 255), 4),
    "residential": (1.8, (190, 190, 190), (255, 255, 255), 5),
    "unclassified": (1.8, (190, 190, 190), (255, 255, 255), 5),
    "living_street": (1.6, (190, 190, 190), (255, 255, 255), 6),
    "pedestrian": (1.6, (190, 190, 190), (250, 245, 240), 6),
    "service": (1.0, (200, 200, 200), (255, 255, 255), 7),
}
MINOR_WAY_WIDTH = 0.7
WATERWAY_WIDTH = {"river": 2.4, "canal": 1.8, "stream": 1.0, "drain": 0.8}
STREET_ABBREVIATIONS = {
    "улица": "ул.", "проспект": "просп.", "переулок": "пер.",
    "бульвар": "бул.", "шоссе": "ш.", "набережная": "наб.",
    "площадь": "пл.", "проезд": "пр-д", "тупик": "туп.",
}
PLACE_PRIORITY = {"city": 0, "town": 1, "suburb": 1, "bay": 2, "strait": 2,
                  "quarter": 3, "neighbourhood": 3, "locality": 4,
                  "village": 4, "hamlet": 4}
HOUSE_BLOCK_RE = re.compile(r"\{[^{}]*?house_id:\s*'[^']+'[^{}]*\}")

KNOWN_APPROXIMATIONS = [
    "Учтены только OSM way; мультиполигоны (relations) зданий, водоёмов и "
    "зелени не отрисованы, часть крупных объектов может отсутствовать.",
    "Площадные way без замыкания пропущены; их число указано в render_notes.",
    "Суша/вода определяется направлением coastline (суша слева); при "
    "разрывах coastline внутри рамки возможны локальные ошибки заливки.",
    "Вся зелень (парки, леса, газоны, пляжи) одним тоном.",
    "Ширина дорог картографическая по классу, не в масштабе; пешеходные "
    "дорожки, лестницы, тропы и грунтовки - тонкой линией без обводки.",
    "Подписи: не более одной на имя улицы, без пересечений; часть имён не "
    "поместилась и не подписана; типовые слова сокращены (ул., просп.).",
    "Координаты домов в каталоге приближённы (центроид здания OSM или "
    "данные владельца) и не являются геодезическими точками входов.",
    "Один растр 2048 px по ширине рамки без уровней приближения: "
    "детализация ограничена масштабом изображения.",
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
    """Рамка EPSG:3857 (xmin, ymin, xmax, ymax) и высота PNG в px.

    Отступ PAD_M от крайних домов; высота round(WIDTH * dy / dx), затем
    рамка симметрично подгоняется по y (менее 0,5 px), чтобы пиксель был
    квадратным в проекции и imageOverlay не растягивал изображение.
    """
    pts = [lonlat_to_mercator(lon, lat) for _, lat, lon in houses]
    xmin = min(x for x, _ in pts) - PAD_M
    xmax = max(x for x, _ in pts) + PAD_M
    ymin = min(y for _, y in pts) - PAD_M
    ymax = max(y for _, y in pts) + PAD_M
    height = round(WIDTH * (ymax - ymin) / (xmax - xmin))
    extra = (height * (xmax - xmin) / WIDTH - (ymax - ymin)) / 2
    return (xmin, ymin - extra, xmax, ymax + extra), height


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


class Canvas:
    """Холст суперсэмплинга и проекция EPSG:3857 -> пиксели холста."""

    def __init__(self, frame, height):
        self.xmin, self.ymin, self.xmax, self.ymax = frame
        self.w = WIDTH * SS
        self.h = height * SS
        self.scale = self.w / (self.xmax - self.xmin)
        self.img = Image.new("RGB", (self.w, self.h), WATER)
        self.draw = ImageDraw.Draw(self.img)

    def px(self, x, y):
        """Пиксель холста для точки EPSG:3857."""
        return (x - self.xmin) * self.scale, (self.ymax - y) * self.scale

    def ring(self, coords):
        """Пиксели холста для списка [lat, lon] из region.json."""
        return [self.px(*lonlat_to_mercator(lon, lat)) for lat, lon in coords]


def classify_coast(coastline, frame_rect, seeds):
    """Грани рамки, разрезанной coastline, с классом суша/вода.

    По соглашению OSM суша слева от направления coastline. Каждый сегмент
    голосует своей длиной: точка слева - за сушу грани, справа - за воду.
    Грань без голосов - вода при семени bay/strait внутри, иначе суша.
    Возвращает [(polygon, is_land)] и счётчики диагностики.
    """
    directed = [[lonlat_to_mercator(lon, lat) for lat, lon in way]
                for way in coastline if len(way) >= 2]
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


def closed_ring(coords):
    """True для замкнутого контура площадного объекта (не менее 4 точек)."""
    return len(coords) >= 4 and coords[0] == coords[-1]


def draw_line(cv, pts, width_px, fill):
    """Линия шириной width_px итоговых пикселей на холсте суперсэмплинга."""
    width = max(1, round(width_px * SS))
    cv.draw.line(pts, fill=fill, width=width, joint="curve" if width > 2 else None)


def abbreviate(name):
    """Короткая подпись улицы: типовые слова заменяются сокращениями."""
    for word, short in STREET_ABBREVIATIONS.items():
        name = re.sub(rf"(?<!\w){word}(?!\w)", short, name)
    return name


class LabelPlacer:
    """Подписи с белым ореолом и запретом пересечения повёрнутых рамок."""

    def __init__(self, cv):
        self.cv = cv
        self.placed = []
        self.inner = box(4 * SS, 4 * SS, cv.w - 4 * SS, cv.h - 4 * SS)

    def try_place(self, text, font, fill, center, angle):
        """Ставит подпись, если рамка внутри холста и ни с чем не пересекается."""
        stroke = max(1, SS)
        left, top, right, bottom = font.getbbox(text, stroke_width=stroke)
        w, h = right - left + 2, bottom - top + 2
        cx, cy = center
        footprint = affinity.rotate(
            box(cx - w / 2 - SS, cy - h / 2 - SS, cx + w / 2 + SS, cy + h / 2 + SS),
            -angle, origin=(cx, cy))
        if not self.inner.contains(footprint):
            return False
        if self.placed and shapely.intersects(self.placed, footprint).any():
            return False
        tmp = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((1 - left, 1 - top), text, font=font, fill=fill,
                                 stroke_width=stroke, stroke_fill=HALO)
        rotated = tmp.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
        self.cv.img.paste(rotated, (round(cx - rotated.width / 2),
                                    round(cy - rotated.height / 2)), rotated)
        self.placed.append(footprint)
        return True

    def place_along(self, text, font, fill, line):
        """Подпись вдоль линии холста: позиции от середины к краям."""
        width = font.getlength(text) + 4 * SS
        if line.length < width * 1.1:
            return False
        for frac in (0.5, 0.35, 0.65, 0.2, 0.8):
            t = line.length * frac
            if t - width / 2 < 0 or t + width / 2 > line.length:
                continue
            p1, p2 = line.interpolate(t - width / 2), line.interpolate(t + width / 2)
            chord = LineString([p1, p2])
            piece = substring(line, t - width / 2, t + width / 2)
            if (chord.length < 0.9 * width
                    or piece.hausdorff_distance(chord) > 0.4 * font.size):
                continue
            angle = math.degrees(math.atan2(-(p2.y - p1.y), p2.x - p1.x))
            if angle > 90:
                angle -= 180
            elif angle <= -90:
                angle += 180
            center = ((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
            if self.try_place(text, font, fill, center, angle):
                return True
        return False


def place_labels(cv, region, styled, fonts):
    """Подписи мест и бухт, затем улиц по рангу класса и длине."""
    placer = LabelPlacer(cv)
    font_street, font_place, font_bay = fonts
    placed_places = 0
    for lb in sorted(region["labels"],
                     key=lambda lb: (PLACE_PRIORITY.get(lb["kind"], 5), lb["name"])):
        is_bay = lb["kind"] in ("bay", "strait")
        center = cv.px(*lonlat_to_mercator(lb["lon"], lb["lat"]))
        placed_places += placer.try_place(
            lb["name"], font_bay if is_bay else font_place,
            BAY_TEXT if is_bay else PLACE_TEXT, center, 0.0)

    by_name = {}
    for item, pts in styled:
        if item["name"] and len(pts) >= 2:
            rank = ROAD_STYLES.get(item["cls"], (0, 0, 0, 8))[3]
            entry = by_name.setdefault(item["name"], [9, []])
            entry[0] = min(entry[0], rank)
            entry[1].append(pts)
    candidates = []
    for name, (rank, parts) in by_name.items():
        merged = linemerge(MultiLineString(parts))
        lines = sorted(getattr(merged, "geoms", [merged]), key=lambda g: -g.length)
        candidates.append((rank, -sum(g.length for g in lines), name, lines))
    candidates.sort(key=lambda c: c[:3])
    placed_streets = 0
    for _, _, name, lines in candidates:
        text = abbreviate(name)
        placed_streets += any(placer.place_along(text, font_street, STREET_TEXT, line)
                              for line in lines[:3])
    return {"place_labels": placed_places, "street_names": len(by_name),
            "street_labels": placed_streets}


def render(region, frame, height, fonts):
    """Рисует все слои; возвращает итоговое изображение и счётчики."""
    cv = Canvas(frame, height)
    frame_rect = box(*frame)
    seeds = [Point(lonlat_to_mercator(lb["lon"], lb["lat"]))
             for lb in region["labels"] if lb["kind"] in ("bay", "strait")]
    faces, coast = classify_coast(region["coastline"], frame_rect, seeds)
    for face, is_land in sorted(faces, key=lambda pair: -pair[0].area):
        pts = [cv.px(x, y) for x, y in face.exterior.coords]
        cv.draw.polygon(pts, fill=LAND if is_land else WATER)

    counts = {"green": 0, "water_areas": 0, "buildings": 0, "skipped_open_areas": 0}
    for layer, color in (("green", PARK), ("water_areas", WATER)):
        for coords in region[layer]:
            if not closed_ring(coords):
                counts["skipped_open_areas"] += 1
                continue
            cv.draw.polygon(cv.ring(coords), fill=color)
            counts[layer] += 1
    for item in region["waterways"]:
        draw_line(cv, cv.ring(item["coords"]), WATERWAY_WIDTH[item["cls"]], WATER)
    for coords in region["buildings"]:
        if not closed_ring(coords):
            counts["skipped_open_areas"] += 1
            continue
        cv.draw.polygon(cv.ring(coords), fill=BUILDING, outline=BUILDING_EDGE)
        counts["buildings"] += 1
    for coords in region["railways"]:
        draw_line(cv, cv.ring(coords), 1.0, RAIL)

    styled = [(item, cv.ring(item["coords"])) for item in region["roads"]]
    minor = [pts for item, pts in styled if item["cls"] not in ROAD_STYLES]
    major = sorted(((item, pts) for item, pts in styled if item["cls"] in ROAD_STYLES),
                   key=lambda pair: ROAD_STYLES[pair[0]["cls"]][0])
    for pts in minor:
        draw_line(cv, pts, MINOR_WAY_WIDTH, MINOR_WAY)
    for item, pts in major:
        width, casing, _, _ = ROAD_STYLES[item["cls"]]
        draw_line(cv, pts, width + 1.2, casing)
    for item, pts in major:
        width, _, fill, _ = ROAD_STYLES[item["cls"]]
        draw_line(cv, pts, width, fill)
    counts["roads_major"], counts["roads_minor"] = len(major), len(minor)

    counts.update(place_labels(cv, region, styled, fonts))
    final = cv.img.resize((WIDTH, height), Image.Resampling.LANCZOS)
    return final, coast, counts


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


def build_manifest(frame, height, paths, tools, coast, counts):
    """Manifest L.imageOverlay: bounds, проекция, источник, воспроизведение.

    paths: словарь png, pbf, region; в manifest попадают только имена и sha256.
    """
    xmin, ymin, xmax, ymax = frame
    west, south = mercator_to_lonlat(xmin, ymin)
    east, north = mercator_to_lonlat(xmax, ymax)
    py = "map-preparation\\.venv\\Scripts\\python.exe"
    return {
        "image": IMAGE_URL,
        "crs": "EPSG:3857",
        "width": WIDTH,
        "height": height,
        "bounds": {"south": south, "west": west, "north": north, "east": east},
        "projected_bounds": {"min_x": xmin, "min_y": ymin, "max_x": xmax, "max_y": ymax},
        "image_sha256": sha256_file(paths["png"]),
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
            f"{py} map-preparation\\extract_region.py <PBF> {EXTRACT_BBOX_ARGS} "
            "map-preparation\\region.json",
            f"{py} map-preparation\\render_map.py map-preparation\\region.json "
            "frontend\\src\\features\\dossier\\pilotHouses.ts <PBF> "
            "output\\maps\\vladivostok-pilot.png "
            "output\\maps\\vladivostok-pilot.manifest.json "
            "--font <FONT_REGULAR> --font-bold <FONT_BOLD>",
        ],
        "tools": tools,
        "known_approximations": KNOWN_APPROXIMATIONS,
        "render_notes": {
            "projection": "Web Mercator, сфера R=6378137 м, y растёт к северу",
            "frame": f"крайние 20 домов + {PAD_M:g} м EPSG:3857; по y подгонка "
                     "до целой высоты в px (менее 0,5 px)",
            "meters_per_pixel_epsg3857": (xmax - xmin) / WIDTH,
            "ground_meters_per_pixel_at_center":
                (xmax - xmin) / WIDTH * math.cos(math.radians((south + north) / 2)),
            "supersampling": SS,
            "extract_bbox": EXTRACT_BBOX_ARGS,
            "region_json_sha256": sha256_file(paths["region"]),
            "coastline": coast,
            "drawn": counts,
            "road_width": "картографическая по классу дороги, не метрическая",
            "street_abbreviations": STREET_ABBREVIATIONS,
        },
    }


def render_files(args):
    """Рендер PNG и manifest по аргументам CLI; сводка для журнала.

    Ожидаемые отказы входа и записи — RenderError с кодом причины.
    """
    fonts = (load_font(args.font, 11 * SS), load_font(args.font_bold, 13 * SS),
             load_font(args.font_bold, 12 * SS))
    if not Path(args.pbf).is_file():
        raise RenderError("pbf_not_found", f"PBF не найден: {args.pbf}")
    try:
        region = json.loads(Path(args.region).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RenderError("region_read_failed", f"region.json не прочитан: {exc}") from exc
    try:
        houses = parse_houses(args.houses)
    except (OSError, UnicodeDecodeError) as exc:
        raise RenderError("houses_read_failed", f"каталог домов не прочитан: {exc}") from exc
    frame, height = compute_frame(houses)
    west, south = mercator_to_lonlat(frame[0], frame[1])
    east, north = mercator_to_lonlat(frame[2], frame[3])
    e_west, e_south, e_east, e_north = region["bbox"]
    if not (e_west <= west and e_south <= south and east <= e_east and north <= e_north):
        raise RenderError("frame_outside_region",
                          "рамка карты выходит за bbox region.json; "
                          "повторите extract_region.py с большим bbox")

    image, coast, counts = render(region, frame, height, fonts)
    try:
        image.save(args.out_png, optimize=True)
    except OSError as exc:
        raise RenderError("output_write_failed", f"PNG не записан: {exc}") from exc
    tools = tool_versions([("regular", args.font), ("bold", args.font_bold)])
    paths = {"png": args.out_png, "pbf": args.pbf, "region": args.region}
    manifest = build_manifest(frame, height, paths, tools, coast, counts)
    try:
        Path(args.out_manifest).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise RenderError("output_write_failed", f"manifest не записан: {exc}") from exc
    return {
        "png_name": Path(args.out_png).name,
        "manifest_name": Path(args.out_manifest).name,
        "width": WIDTH,
        "height": height,
        "image_sha256": manifest["image_sha256"],
        "manifest_sha256": sha256_file(args.out_manifest),
        "bounds": {"south": south, "west": west, "north": north, "east": east},
        "coastline": coast,
        "drawn": counts,
    }


def main():
    """CLI: рендер PNG и manifest; события MAP_RENDER_* в журнал карты.

    Журнал настраивается до разбора аргументов (fail-fast). Ожидаемый отказ —
    событие и SystemExit с текстом; непредвиденный пробрасывается после события.
    """
    setup_logging(load_logging_settings(ServiceName.MAP))
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("region", "houses", "pbf", "out_png", "out_manifest"):
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
    _logger.info("MAP_RENDER_COMPLETED", "map image and manifest written", **summary)


if __name__ == "__main__":
    main()
