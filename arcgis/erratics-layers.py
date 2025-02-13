"""
erratics_analysis_with_api_key.py

Demonstrates how to:
1) Read a CSV of glacial erratics (lat/lon).
2) Use ArcGIS Python API with an API key (anonymous-like user) to query real
   feature services for rivers and coastlines (in bounding box).
3) Perform local proximity analysis with Shapely (buffer/intersect in projected coordinates).
4) Display results in an ArcGIS MapView with toggleable layers (no publishing),
   specifically:
      - All erratics
      - Close to rivers
      - Close to coast
"""

import os
import csv

import pyproj
import shapely.ops
from shapely.geometry import Point

from arcgis.gis import GIS
from arcgis.features import FeatureLayer, Feature, FeatureSet
from arcgis.map.symbols import SimpleMarkerSymbolEsriSMS, SimpleLineSymbolEsriSLS, SimpleMarkerSymbolStyle
from arcgis.geometry import Geometry

###############################################################################
# 1. CREATE A DEMO CSV IF NOT EXISTS (3 EXAMPLE POINTS IN WA)
###############################################################################

CSV_PATH = "erratics_gis.csv"

###############################################################################
# 2. READ CSV OF ERRATICS
###############################################################################
def read_erratics_csv(csv_path):
    """
    Reads 'erratics_gis.csv' with these columns:
       row[1] = latitude,
       row[2] = longitude,
       row[6] = id,
       row[7] = name
    Returns a list of dicts: [{"id":"ERR001", "name":"...", "lat":47..., "lon":-122...}, ...]
    """
    data = []
    with open(csv_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)  # skip header
        for row in reader:
            lat = float(row[1])
            lon = float(row[2])
            eid = row[6]
            ename = row[7]
            data.append({
                "id": eid,
                "name": ename,
                "lat": lat,
                "lon": lon
            })
    return data

###############################################################################
# 3. ARCGIS FEATURE SERVICE URLS
###############################################################################
# Real data from ArcGIS Online
RIVERS_URL = "https://services1.arcgis.com/ZIL9uO234SBBPGL7/ArcGIS/rest/services/Rivers_World_Natural_Earth/FeatureServer/0"
COAST_URL =  "https://services7.arcgis.com/WSiUmUhlFx4CtMBB/ArcGIS/rest/services/GSHHS_GlobalCoastlines_HighResolution/FeatureServer/0"

###############################################################################
# 4. PROXIMITY UTILS
###############################################################################
def reproject_point(point_geometry, from_crs="EPSG:4326", to_crs="EPSG:3857"):
    """Reproject a Shapely Point using pyproj for distance-based calculations."""
    project_func = pyproj.Transformer.from_crs(
        from_crs, to_crs, always_xy=True
    ).transform
    return shapely.ops.transform(project_func, point_geometry)

def is_point_within_distance(point_lonlat, list_of_features, distance_meters):
    """
    Return True if 'point_lonlat' (Shapely, EPSG:4326) is within
    'distance_meters' of ANY geometry in 'list_of_features'.
    """
    point_3857 = reproject_point(point_lonlat, "EPSG:4326", "EPSG:3857")
    for feat_4326 in list_of_features:
        feat_3857 = reproject_point(feat_4326, "EPSG:4326", "EPSG:3857")
        if point_3857.distance(feat_3857) <= distance_meters:
            return True
    return False

###############################################################################
# 5. HELPER: CONVERT FeatureSet --> LIST OF SHAPELY GEOMETRIES
###############################################################################
def fs_to_shapely_list(fs):
    """
    Convert an ArcGIS FeatureSet to a list of Shapely geometries.
    Uses arcgis.geometry.Geometry(...) + .as_shapely for robust conversion.
    Skips null or empty geometry.
    """
    geoms = []
    null_count = 0
    fail_count = 0
    
    for f in fs.features:
        if f.geometry is None:
            null_count += 1
            continue
        
        try:
            arc_geom = Geometry(f.geometry)
            if arc_geom.is_empty:
                null_count += 1
                continue
            sgeom = arc_geom.as_shapely
            if sgeom and not sgeom.is_empty:
                geoms.append(sgeom)
            else:
                null_count += 1
        except Exception:
            fail_count += 1
    
    if null_count > 0:
        print(f"[WARN] Skipped {null_count} empty or null geoms.")
    if fail_count > 0:
        print(f"[WARN] Conversion failed for {fail_count} geoms.")
    return geoms

###############################################################################
# 6. MAIN
###############################################################################
def main():
    # A) Read local CSV
    erratics = read_erratics_csv(CSV_PATH)
    print(f"Loaded {len(erratics)} erratics from {CSV_PATH}.")

    # B) Connect to ArcGIS via API key
    API_KEY = "AAPTxy8BH1VEsoebNVZXo8HurNF06YWHEbns1XWgxHCpzlyDjxh3Rx8dbWwLv-YhpjbuKnTT5uOWTO7-WskSkafBC6jiu1QCJUkLpyb-6epQoRGSlLogeBqx_bwJSceJjPn7ooXJnbZwuuPl8jcPSv014Zrv8X5lK7aDfBFPPUlt8dfqMsy9ZZtrxkFKKrL9bRIhoJZTDuTzFRhIgV43IhOe3YtvXO7xAuynlg14irzQnV8.AT1_TRlM9H04"  # <-- replace with your real key
    gis = GIS(api_key=API_KEY)
    if gis.users.me is not None:
        print("[INFO] Named user or full developer account.")
    else:
        print("[INFO] Using anonymous-like user with API key.")

    # C) Bounding box for Washington to limit queries
    WA_BBOX = {
        "xmin": -122,
        "ymin": 46,
        "xmax": -118,
        "ymax": 47,
        "spatialReference": {"wkid": 4326}
    }

    # D) Query rivers and coast
    rivers_layer = FeatureLayer(RIVERS_URL, gis=gis)
    coast_layer  = FeatureLayer(COAST_URL,  gis=gis)

    print("[INFO] Querying rivers within bounding box...")
    rivers_fs = rivers_layer.query(
        geometry=WA_BBOX,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
        where="1=1",
        return_geometry=True
    )
    print(f" -> fetched {len(rivers_fs.features)} river features.")

    print("[INFO] Querying coast within bounding box...")
    coast_fs = coast_layer.query(
        geometry=WA_BBOX,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
        where="1=1",
        return_geometry=True
    )
    print(f" -> fetched {len(coast_fs.features)} coast features.")

    rivers_geomlist = fs_to_shapely_list(rivers_fs)
    coast_geomlist  = fs_to_shapely_list(coast_fs)

    print(f"[INFO] Rivers geometry count: {len(rivers_geomlist)}")
    print(f"[INFO] Coast geometry count:  {len(coast_geomlist)}")

    # E) Proximity checks
    RIVER_DISTANCE = 1000.0  # 1 km
    COAST_DISTANCE = 2000.0  # 2 km

    results = []
    for e in erratics:
        pt = Point(e["lon"], e["lat"])
        close_river = is_point_within_distance(pt, rivers_geomlist, RIVER_DISTANCE)
        close_coast = is_point_within_distance(pt, coast_geomlist,  COAST_DISTANCE)

        results.append({
            "id":   e["id"],
            "name": e["name"],
            "lon":  e["lon"],
            "lat":  e["lat"],
            "close_river":  close_river,
            "close_coast":  close_coast
        })

    print(f"[INFO] Completed proximity analysis for {len(results)} erratics.")

    # F) Create toggleable layers in ArcGIS MapView

    def make_featureset(records, layer_label):
        """
        Build a fully defined FeatureSet: 
         - geometry_type='esriGeometryPoint'
         - spatial_reference={"wkid":4326}
         - fields: an array describing each attribute
        """
        # 1) Build a list of arcgis.features.Feature
        feats = []
        for r in records:
            geom = {
                "x": r["lon"],
                "y": r["lat"],
                "spatialReference": {"wkid": 4326}
            }
            # We'll store booleans as strings to avoid field-type confusion
            attrs = {
                "id":   r["id"],
                "name": r["name"],
                "lon":  r["lon"],
                "lat":  r["lat"],
                "close_river":  str(r["close_river"]),
                "close_coast":  str(r["close_coast"])
            }
            feats.append(Feature(geometry=geom, attributes=attrs))
        
        # 2) Define the "fields" array for each attribute
        fields = [
            {
                "name": "id",
                "type": "esriFieldTypeString",
                "alias": "id"
            },
            {
                "name": "name",
                "type": "esriFieldTypeString",
                "alias": "name"
            },
            {
                "name": "lon",
                "type": "esriFieldTypeDouble",
                "alias": "lon"
            },
            {
                "name": "lat",
                "type": "esriFieldTypeDouble",
                "alias": "lat"
            },
            {
                "name": "close_river",
                "type": "esriFieldTypeString",
                "alias": "close_river"
            },
            {
                "name": "close_coast",
                "type": "esriFieldTypeString",
                "alias": "close_coast"
            }
        ]

        # 3) Create the FeatureSet with geometry type + fields
        fs = FeatureSet(
            features=feats,
            geometry_type="esriGeometryPoint",
            spatial_reference={"wkid": 4326},
            fields=fields
        )
        return fs

    # Create three layers: All, close_river, close_coast
    all_fs = make_featureset(results, "All Erratics")

    close_river_fs = make_featureset(
        [r for r in results if r["close_river"]], 
        "Close to Rivers"
    )
    close_coast_fs = make_featureset(
        [r for r in results if r["close_coast"]],
        "Close to Coast"
    )

    # Define some simple symbols
    sym_all = SimpleMarkerSymbolEsriSMS(
        style=SimpleMarkerSymbolStyle.esri_sms_circle,
        color=[0, 0, 255, 128],
        outline=SimpleLineSymbolEsriSLS(color=[255,255,255], width=1)
    )
    sym_river = SimpleMarkerSymbolEsriSMS(
        style=SimpleMarkerSymbolStyle.esri_sms_circle,
        color=[255, 0, 0, 128],
        outline=SimpleLineSymbolEsriSLS(color=[255,255,255], width=1)
    )
    sym_coast = SimpleMarkerSymbolEsriSMS(
        style=SimpleMarkerSymbolStyle.esri_sms_circle,
        color=[0, 255, 0, 128],
        outline=SimpleLineSymbolEsriSLS(color=[255,255,255], width=1)
    )

    # Create a map centered on Washington
    my_map = gis.map("Washington, USA")

    # Draw each set as a toggleable layer (label)
    # Potentially use `label=` to name them in the layer list
    my_map.content.draw(shape=all_fs, symbol=sym_all)
    my_map.content.draw(shape=close_river_fs, symbol=sym_river)
    my_map.content.draw(shape=close_coast_fs, symbol=sym_coast)

    print("\n[INFO] Done. Below is an interactive ArcGIS MapView (in Jupyter).")
    print("You can toggle the layers in the layer list.\n")
    print("----- RESULTS -----")
    for r in results:
        print(f"ID={r['id']} | Name={r['name']} | lat={r['lat']} lon={r['lon']} | "
              f"CloseToRiver={r['close_river']} | CloseToCoast={r['close_coast']}")

    # In Jupyter, just "return my_map" to display. 
    return my_map

###############################################################################
# 7. ENTRY POINT
###############################################################################
if __name__ == "__main__":
    m = main()
