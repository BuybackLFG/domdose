"""Extract a small overview of OSM land polygons from the downloaded Mercator zip."""
import argparse
import json
import math
import zipfile
from pathlib import Path

import shapefile
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

R = 6378137.0
WEST, SOUTH, EAST, NORTH = 130.8, 42.7, 133.2, 43.7

def project(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def unproject(x, y, z=None):
    return (round(math.degrees(x / R), 6),
            round(math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2), 6))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    x1, y1 = project(WEST, SOUTH)
    x2, y2 = project(EAST, NORTH)
    clip = box(x1, y1, x2, y2)
    with zipfile.ZipFile(args.archive) as archive:
        shp = next(name for name in archive.namelist() if name.endswith('.shp'))
        shx = shp[:-4] + '.shx'
        with archive.open(shp) as source, archive.open(shx) as index:
            reader = shapefile.Reader(shp=source, shx=index)
            features = []
            for item in reader.iterShapes(bbox=(x1, y1, x2, y2)):
                geom = shape(item.__geo_interface__).intersection(clip)
                if not geom.is_empty:
                    features.append({'type': 'Feature', 'properties': {},
                                     'geometry': mapping(transform(unproject, geom))})
    args.output.write_text(json.dumps({'type': 'FeatureCollection', 'features': features},
                                      ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

if __name__ == '__main__':
    main()
