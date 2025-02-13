#!/usr/bin/env python3
"""
erratics_analysis_with_api_key.py

Demonstrates how to:
1) Read a CSV of glacial erratics (lat/lon).
2) Use ArcGIS Python API with an API key (anonymous-like user) to query real
   feature services for rivers, coastlines, forest polygons (in bounding box).
3) Perform all proximity analysis locally using Shapely (buffers, intersects).
4) Retrieve elevation for each erratic from ArcGIS Elevation REST API.
5) Display results in an ArcGIS MapView with toggleable layers (no publishing).
"""

import os
import csv
import requests

from arcgis.gis import GIS
from arcgis.features import FeatureLayer, Feature, FeatureSet
from arcgis.map.symbols import SimpleMarkerSymbolEsriSMS, SimpleLineSymbolEsriSLS, SimpleMarkerSymbolStyle, PictureMarkerSymbolEsriPMS
from arcgis.map.popups import PopupInfo
from arcgis.geometry import Geometry
from shapely.geometry import shape, Point
import shapely.ops

# Optional: for coordinate transformations (EPSG:4326 -> EPSG:3857)
# If your region is small and you want more accurate distance buffering,
# consider a local UTM or Albers projection. This example uses pyproj:
import pyproj
from shapely.ops import transform


###############################################################################
# 1. CREATE A DEMO CSV OF ERRATICS (3 REAL POINTS IN WASHINGTON, USA)
###############################################################################
# For demonstration, we create a small CSV "erratics_gis.csv" with columns that
# match your original indexing:
#   row[1] = lat
#   row[2] = lon
#   row[6] = id
#   row[7] = name
# We fill other columns with dummy data for completeness (no placeholders for lat/lon).
demo_csv = """col0,latitude,longitude,col3,col4,col5,id,name
xxx,46.8523,-121.7603,foo,foo,foo,ERR001,Mount Rainier Erratic
xxx,47.6062,-122.3321,foo,foo,foo,ERR002,Seattle Erratic
xxx,46.6021,-120.5059,foo,foo,foo,ERR003,Yakima Erratic
"""

CSV_PATH = "erratics_gis.csv"
if not os.path.isfile(CSV_PATH):
    with open(CSV_PATH, "w", encoding="utf-8") as f:
        f.write(demo_csv)


###############################################################################
# 2. FUNCTION TO READ THE CSV INTO A LIST
###############################################################################
def read_erratics_csv(csv_path):
    """
    Reads 'erratics_gis.csv' with the known column structure:
       row[1] = latitude,
       row[2] = longitude,
       row[6] = id,
       row[7] = name
    Returns a list of dictionaries:
      [{"id":..., "name":..., "lat":..., "lon":...}, ...]
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
# 3. ARCGIS REST ENDPOINTS FOR RIVERS, COAST, FOREST
###############################################################################
# We use publicly available "Natural Earth" feature services from Esri's Living Atlas:
#    - Rivers:   https://services1.arcgis.com/ZIL9uO234SBBPGL7/ArcGIS/rest/services/Rivers_World_Natural_Earth/FeatureServer/0
#    - Coast:    https://services7.arcgis.com/WSiUmUhlFx4CtMBB/ArcGIS/rest/services/GSHHS_GlobalCoastlines_HighResolution/FeatureServer/0
#    - Ecological Land Units (for forest polygons):
#      https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/Ecological_Land_Units_World/FeatureServer/0
# (These are real services as of 2025-02. They may change or require a specific subscription.)

RIVERS_URL = "https://services1.arcgis.com/ZIL9uO234SBBPGL7/ArcGIS/rest/services/Rivers_World_Natural_Earth/FeatureServer/0"
COAST_URL = "https://services7.arcgis.com/WSiUmUhlFx4CtMBB/ArcGIS/rest/services/GSHHS_GlobalCoastlines_HighResolution/FeatureServer/0"
FOREST_URL = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/Ecological_Land_Units_World/FeatureServer/0"

# For the forest dataset, we have polygons with attributes like "BIOME_NAME".
# We'll define "forest" as polygons where BIOME_NAME includes "Forest".
# Example forest BIOME_NAME values:
#   "Temperate Conifer Forests", "Temperate Broadleaf & Mixed Forests",
#   "Tropical & Subtropical Moist Broadleaf Forests", etc.


###############################################################################
# 4. ELEVATION ENDPOINT
###############################################################################
# ArcGIS Elevation Analysis can be accessed (if your API key has privileges) via:
#   https://elevation.arcgis.com/arcgis/rest/services/Tools/ElevationSync/GPServer/Profile/execute
# We'll do a simple function to get single-point elevations.


def get_elevation(lon, lat, api_key):
    """
    Queries ArcGIS Elevation REST API for the approximate elevation (in meters)
    at the given (lon, lat). 
    Returns a float or None if there's an error.

    WARNING: You must have an API key that permits the Elevation service.
    This may consume credits depending on your plan.
    """
    # This example uses a documented approach for the "Profile" GP service:
    # See: https://developers.arcgis.com/rest/elevation/api-reference/
    service_url = (
        "https://elevation.arcgis.com/arcgis/rest/services/Tools/ElevationSync/"
        "GPServer/Profile/execute"
    )

    # The service expects geometry in an "InputLineFeatures" parameter.
    # We can pass a short polyline with only two points or a single point if we treat it carefully.
    # A simpler approach is the "World Elevation" image service with an Identify request,
    # but let's do it the official "Profile" way.

    # We'll craft a minimal line from (lon, lat) to (lon, lat) so it has zero length:
    # Then the sample geometry in the result should yield a single Z value.

    line_features = {
        "geometryType": "esriGeometryPolyline",
        "features": [
            {
                "geometry": {
                    "paths": [
                        [
                            [lon, lat],
                            [lon, lat]
                        ]
                    ],
                    "spatialReference": {"wkid": 4326}
                },
                "attributes": {}
            }
        ]
    }

    params = {
        "InputLineFeatures": line_features,
        "ProfileIDField": "OBJECTID",
        "DEMResolution": "FINEST",
        "MaximumSampleDistanceUnits": "Meters",
        "env:outSR": 4326,
        "env:processSR": 4326,
        "returnM": "true",
        "returnZ": "true",
        "f": "json",
        "token": api_key
    }

    try:
        r = requests.post(service_url, json=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        # The output is in "OutputProfile". 
        # It has features with geometry(paths) that have (x, y, z, m).
        # We'll parse the single line.
        profile = j["results"][0]["value"]["features"][0]["geometry"]["paths"][0]
        # profile is a list of [x, y, z, m]
        # e.g.: [[lon, lat, elevZ, measureM], [lon, lat, elevZ, measureM], ...]
        # Since we used a zero-length line, we might have a single or two identical points.
        # We'll take the first point's z:
        elev_z = profile[0][2]
        return float(elev_z)
    except Exception as ex:
        print(f"[WARN] Elevation query failed for (lon={lon}, lat={lat}): {ex}")
        return None


###############################################################################
# 5. LOCAL PROXIMITY CHECKS (USING SHAPELY)
###############################################################################
def reproject_point(point_geometry, from_crs="EPSG:4326", to_crs="EPSG:3857"):
    """
    Reprojects a Shapely Point from one CRS to another using pyproj.
    Useful to do distance buffering in meters if `to_crs` has meter units.
    """
    project_func = pyproj.Transformer.from_crs(
        from_crs, to_crs, always_xy=True
    ).transform
    return transform(project_func, point_geometry)


def is_point_within_distance(point_lonlat, list_of_features, distance_meters):
    """
    Checks if the given Shapely point (in EPSG:4326) is within `distance_meters`
    of ANY geometry in list_of_features (each also in EPSG:4326).
    We'll:
      1) Reproject both point and each feature to EPSG:3857,
      2) Compare distances in projected space (meters).

    Returns True if within distance of at least one geometry, else False.

    For performance, you'd ideally union the features or use an R-tree,
    but this example is straightforward for small data.
    """
    # Reproject the point once:
    point_3857 = reproject_point(point_lonlat, "EPSG:4326", "EPSG:3857")

    # We'll do a simple loop:
    for feat_4326 in list_of_features:
        feat_3857 = reproject_point(feat_4326, "EPSG:4326", "EPSG:3857")
        dist = point_3857.distance(feat_3857)
        if dist <= distance_meters:
            return True
    return False


###############################################################################
# 6. MAIN SCRIPT
###############################################################################
def main():
    ###########################################################################
    # A) READ ERRATICS FROM CSV
    ###########################################################################
    erratics = read_erratics_csv(CSV_PATH)
    print(f"Loaded {len(erratics)} erratics from {CSV_PATH}.")

    ###########################################################################
    # B) CONNECT TO ARCGIS WITH API KEY (READ-ONLY)
    ###########################################################################
    API_KEY = "AAPTxy8BH1VEsoebNVZXo8HurNF06YWHEbns1XWgxHCpzlyDjxh3Rx8dbWwLv-YhpjbuKnTT5uOWTO7-WskSkafBC6jiu1QCJUkLpyb-6epQoRGSlLogeBqx_bwJSceJjPn7ooXJnbZwuuPl8jcPSv014Zrv8X5lK7aDfBFPPUlt8dfqMsy9ZZtrxkFKKrL9bRIhoJZTDuTzFRhIgV43IhOe3YtvXO7xAuynlg14irzQnV8.AT1_TRlM9H04"  # <-- Replace with your real key
    gis = GIS(api_key=API_KEY)
    if gis.users.me is not None:
        print("[INFO] You appear to be a named user, not just an API key. That's fine.")
    else:
        print("[INFO] Using API key-based anonymous user.")

    ###########################################################################
    # C) DEFINE A BOUNDING BOX FOR WASHINGTON STATE (rough bounding box)
    #    We'll only query features inside this box to avoid huge downloads.
    ###########################################################################
    WA_BBOX = {
        "xmin": -122,
        "ymin": 46,
        "xmax": -118,
        "ymax": 47,
        "spatialReference": {"wkid": 4326}
    }

    ###########################################################################
    # D) QUERY THE RIVERS, COAST, FOREST LAYERS (READ-ONLY)
    ###########################################################################
    rivers_layer = FeatureLayer(RIVERS_URL, gis=gis)
    coast_layer = FeatureLayer(COAST_URL, gis=gis)
    # forest_layer = FeatureLayer(FOREST_URL, gis=gis)

    print("[INFO] Querying rivers in WA bounding box...")
    rivers_fs = rivers_layer.query(
        geometry=WA_BBOX,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
        where="1=1",
        return_geometry=True
    )
    print(f"  -> fetched {len(rivers_fs.features)} river features.")

    print("[INFO] Querying coast in WA bounding box...")
    coast_fs = coast_layer.query(
        geometry=WA_BBOX,
        geometry_type="esriGeometryEnvelope",
        in_sr=4326,
        out_sr=4326,
        where="1=1",
        return_geometry=True
    )
    print(f"  -> fetched {len(coast_fs.features)} coast features.")

    # print("[INFO] Querying forest polygons in WA bounding box (only polygons with 'Forest' in BIOME_NAME)...")
    # Example: "BIOME_NAME LIKE '%Forest%'"
    # The actual attribute might differ. We'll do a broad approach to reduce data:
    # forest_fs = forest_layer.query(
    #     geometry=WA_BBOX,
    #     geometry_type="esriGeometryEnvelope",
    #     in_sr=4326,
    #     out_sr=4326,
    #     where="BIOME_NAME LIKE '%Forest%'",
    #     return_geometry=True
    # )
    # print(f"  -> fetched {len(forest_fs.features)} forest polygons.")

    # Convert each FeatureSet into a list of Shapely geometries in EPSG:4326
    def fs_to_shapely_list(fs):
        """
        Convert an ArcGIS FeatureSet to a list of Shapely geometries.
        Uses the built-in as_shapely method to handle Esri geometry formats.
        Skips features that have None or invalid geometry.
        """
        geoms = []
        null_count = 0
        conversion_fail_count = 0
        
        for f in fs.features:
            if f.geometry is None:
                # This feature has no geometry at all
                null_count += 1
                continue
            
            arcgeom = Geometry(f.geometry)  # Create an arcgis.geometry.Geometry object
            
            if arcgeom.is_empty:
                # It's an empty geometry
                null_count += 1
                continue
            
            try:
                # Convert to a Shapely geometry
                sgeom = arcgeom.as_shapely
                if sgeom is not None and not sgeom.is_empty:
                    geoms.append(sgeom)
                else:
                    null_count += 1
            except Exception as ex:
                # If for some reason conversion fails
                conversion_fail_count += 1
        
        if null_count > 0:
            print(f"[WARN] Skipped {null_count} features with null/empty geometry.")
        if conversion_fail_count > 0:
            print(f"[WARN] Failed to convert {conversion_fail_count} geometry features.")
        
        return geoms

    rivers_geomlist = fs_to_shapely_list(rivers_fs)
    coast_geomlist = fs_to_shapely_list(coast_fs)
    # forest_geomlist = fs_to_shapely_list(forest_fs)

    print(f"[INFO] Converted {len(rivers_geomlist)} river features to Shapely geometries.")
    print(f"[INFO] Converted {len(coast_geomlist)} coast features to Shapely geometries.")

    ###########################################################################
    # E) FOR EACH ERRATIC:
    #    1) Check if it's close to rivers, coast, forests
    #    2) Get elevation from ArcGIS Elevation
    ###########################################################################
    # Distances (in meters) for "close"
    RIVER_DISTANCE = 1000.0   # 1 km
    COAST_DISTANCE = 2000.0   # 2 km
    FOREST_DISTANCE = 500.0   # 0.5 km

    ELEVATION_THRESHOLD = 1000.0  # We'll say "above 1000m" is interesting

    results = []
    for err in erratics:
        # Shapely point in lat/lon
        pt_lonlat = Point(err["lon"], err["lat"])

        # A) Close to rivers?
        c_river = is_point_within_distance(pt_lonlat, rivers_geomlist, RIVER_DISTANCE)
        # B) Close to coast?
        c_coast = is_point_within_distance(pt_lonlat, coast_geomlist, COAST_DISTANCE)
        # C) Close to forest?
        # c_forest = is_point_within_distance(pt_lonlat, forest_geomlist, FOREST_DISTANCE)

        # D) Elevation
        # elev_m = get_elevation(err["lon"], err["lat"], API_KEY)  # may be None if it fails
        elev_m = None

        # E) Above threshold?
        if elev_m is not None:
            above_thresh = elev_m >= ELEVATION_THRESHOLD
        else:
            above_thresh = False

        results.append({
            "id": err["id"],
            "name": err["name"],
            "lon": err["lon"],
            "lat": err["lat"],
            "close_river": c_river,
            "close_coast": c_coast
            # "close_forest": c_forest,
            # "elevation_m": elev_m,
            # "above_threshold": above_thresh
        })

    print(f"[INFO] Completed analysis for {len(results)} erratics.")
        

    ###########################################################################
    # F) VISUALIZE IN AN ARCGIS MAPVIEW WITH TOGGLEABLE LAYERS
    #    We'll create ephemeral "FeatureSets" for:
    #       1) All erratics
    #       2) Subset close to rivers
    #       3) Subset close to coast
    #       4) Subset close to forest
    #       5) Subset above threshold
    ###########################################################################
    def make_featureset(records, label):
        """
        Create a FeatureSet from a list of dicts with keys:
         'lon','lat','id','name' plus any others for popup attributes.
        """
        feat_list = []
        for r in records:
            geom = {
                "x": r["lon"],
                "y": r["lat"],
                "spatialReference": {"wkid": 4326}
            }
            # put all fields in attributes
            attrs = dict(r)
            feat_list.append(Feature(geometry=geom, attributes=attrs))
        return FeatureSet(feat_list)

    # Convert entire set to a FeatureSet for "All Erratics"
    all_fs = make_featureset(results, "All Erratics")

    # Subsets
    close_rivers_fs = make_featureset(
        [r for r in results if r["close_river"]], 
        "Close to Rivers"
    )
    close_coast_fs = make_featureset(
        [r for r in results if r["close_coast"]],
        "Close to Coast"
    )
    # close_forest_fs = make_featureset(
    #     [r for r in results if r["close_forest"]],
    #     "Close to Forest"
    # )
    # above_thresh_fs = make_featureset(
    #     [r for r in results if r["above_threshold"]],
    #     "Above Elevation Threshold"
    # )

    # Prepare some symbologies
    sym_all = {
        "type": "esriSMS",
        "style": "esriSMSCircle",
        "color": [0, 0, 255, 128],
        "size": 8,
        "outline": {"color": [255, 255, 255, 255], "width": 1}
    }
    sym_riv = {
        "type": "esriSMS",
        "style": "esriSMSCircle",
        "color": [255, 0, 0, 128],
        "size": 8,
        "outline": {"color": [255, 255, 255, 255], "width": 1}
    }
    sym_coast = {
        "type": "esriSMS",
        "style": "esriSMSCircle",
        "color": [0, 255, 0, 128],
        "size": 8,
        "outline": {"color": [255, 255, 255, 255], "width": 1}
    }
    # sym_forest = {
    #     "type": "esriSMS",
    #     "style": "esriSMSCircle",
    #     "color": [0, 255, 255, 128],
    #     "size": 8,
    #     "outline": {"color": [255, 255, 255, 255], "width": 1}
    # }
    # sym_above = {
    #     "type": "esriSMS",
    #     "style": "esriSMSCircle",
    #     "color": [255, 255, 0, 128],
    #     "size": 8,
    #     "outline": {"color": [255, 255, 255, 255], "width": 1}
    # }
    
    sym_all =  SimpleMarkerSymbolEsriSMS(
    style = SimpleMarkerSymbolStyle.esri_sms_circle,
    color = [0, 0, 255, 128],
    outline = SimpleLineSymbolEsriSLS(color = [255, 255, 255], width = 1))

    sym_riv =  SimpleMarkerSymbolEsriSMS(
    style = SimpleMarkerSymbolStyle.esri_sms_circle,
    color = [255, 0, 0, 128],
    outline = SimpleLineSymbolEsriSLS(color = [255, 255, 255], width = 1))

    sym_coast =  SimpleMarkerSymbolEsriSMS(
    style = SimpleMarkerSymbolStyle.esri_sms_circle,
    color = [0, 255, 0, 128],
    outline = SimpleLineSymbolEsriSLS(color = [255, 255, 255], width = 1))

    print("\n[INFO] Preparing an interactive map view...")

    # Create a MapView centered roughly on Washington
    my_map = gis.map("Washington, USA")

    # Add layers with label => toggles in layer list
    my_map.content.draw(shape=all_fs, symbol=sym_all)
    my_map.content.draw(shape=close_rivers_fs, symbol=sym_riv)
    my_map.content.draw(shape=close_coast_fs, symbol=sym_coast)
    # my_map.content.draw(shape=close_forest_fs, symbol=sym_forest, label="Close to Forest")
    # my_map.content.draw(shape=above_thresh_fs, symbol=sym_above, label="Above 1000m")

    print("\n[INFO] Below is an interactive ArcGIS MapView (if in Jupyter).")
    print("      You can toggle the layers in the layer list.\n")
    print("------ RESULTS ------")
    # for r in results:
    #     print(f"ID={r['id']} | Name={r['name']} | Elevation={r['elevation_m']:.1f} | "
    #           f"CloseToRiver={r['close_river']} | CloseToCoast={r['close_coast']} | "
    #           f"CloseToForest={r['close_forest']} | Above1000m={r['above_threshold']}")
    for r in results:
        print(f"ID={r['id']} | Name={r['name']} | Elevation={r['elevation_m']:.1f} | "
              f"CloseToRiver={r['close_river']} | CloseToCoast={r['close_coast']}")

    return my_map


###############################################################################
# 7. RUN MAIN (if this file is executed directly)
###############################################################################
if __name__ == "__main__":
    # Make sure to replace "YOUR_API_KEY_HERE" above with a real API key
    # that has read-access to these services and the elevation endpoint.
    m = main()
    # In a notebook, just let `m` be the last line to display the map widget:
    # m
