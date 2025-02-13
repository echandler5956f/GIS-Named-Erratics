import csv
import os

import pandas as pd

from arcgis.gis import GIS
from arcgis.features import Feature, FeatureSet
from arcgis.features.analysis import join_features

def read_csv_to_dict(file_path):
    """
    Reads a CSV file and returns a dictionary with the ID as the key and
    the name, latitude, and longitude as the value.
    """
    data_dict = {}
    with open(file_path, mode='r', encoding='utf-8-sig') as file:
        csv_reader = csv.reader(file)
        next(csv_reader)  # Skip header row if your CSV has one
        for row in csv_reader:
            erratic_id = row[6]
            name = row[7]
            latitude = float(row[1])
            longitude = float(row[2])
            data_dict[erratic_id] = {
                'name': name, 
                'latitude': latitude, 
                'longitude': longitude
            }
    return data_dict

def main():
    # 1. Load CSV
    file_path = 'erratics_gis.csv'
    erratics_data = read_csv_to_dict(file_path)
    print(f"Loaded {len(erratics_data)} erratics from CSV.")

    # 2. Connect to ArcGIS (Authenticated is typically required for publishing)
    portal = GIS(api_key="AAPTxy8BH1VEsoebNVZXo8HurNF06YWHEbns1XWgxHCpzlyDjxh3Rx8dbWwLv-YhpjbuKnTT5uOWTO7-WskSkafBC6jiu1QCJUkLpyb-6epQoRGSlLogeBqx_bwJSceJjPn7ooXJnbZwuuPl8jcPSv014Zrv8X5lK7aDfBFPPUlt8dfqMsy9ZZtrxkFKKrL9bRIhoJZTDuTzFRhIgV43IhOe3YtvXO7xAuynlg14irzQnV8.AT1_TRlM9H04")

    # 3. Convert your data into a FeatureSet
    feature_list = []
    for eid, info in erratics_data.items():
        point_geom = {
            "x": info['longitude'],
            "y": info['latitude'],
            "spatialReference": {"wkid": 4326}
        }
        attr = {
            "Erratic_ID": eid, 
            "Name": info['name']
        }
        feature_list.append(Feature(geometry=point_geom, attributes=attr))

    erratics_fs = FeatureSet(feature_list)
    
    # (Optional) Look at the FeatureSet
    print(f"FeatureSet has {len(erratics_fs.features)} features.")

    # 4. Convert FeatureSet --> Spatially Enabled DataFrame --> Publish
    #    (This is the correct way to create a hosted Feature Layer, 
    #     so that you can later do join_features, etc.)
    erratics_sdf = erratics_fs.sdf  # SEDF from the FeatureSet
    published_item = erratics_sdf.spatial.to_featurelayer(
        title="Temp_Erratics_Features",
        gis=portal,
        tags=["erratics", "temp"],
        description="Hosted layer of erratics for topographical analysis."
    )
    
    # The returned object is an Item in your portal
    print("Created hosted feature layer item:", published_item.title, published_item.id)
    
    # Get the first layer from the published item
    erratics_layer = published_item.layers[0]
    print("Erratics layer URL:", erratics_layer.url)

    # 5. Access real topographical layers for analysis
    # (Example item IDs; replace with valid ones for rivers/coastlines.)
    rivers_item = portal.content.get("ca7074fa1a2148c2927a9b7bcc0008c7")      # example only
    coastlines_item = portal.content.get("9dff06afeb4c4887a908e3f8857ec74d")  # example only
    forest_item = portal.content.get("2e4b3df6ba4b44969e3bc9827de746b3")      # example only

    rivers_layer = rivers_item.layers[0] if rivers_item else None
    coastlines_layer = coastlines_item.layers[0] if coastlines_item else None
    forest_layer = forest_item.layers[0] if forest_item else None

    # 6. For "close to rivers" => use join_features with a distance threshold
    close_to_rivers_result = join_features(
        target_layer=erratics_layer,
        join_layer=rivers_layer,
        spatial_relationship="intersects",
        distance=1000,  # e.g., 1 km
        distance_unit="Meters",
        join_type="keep_common",
        output_name="Erratics_Close_To_Rivers"  # publishes a new hosted layer
    )
    close_to_rivers_fl = close_to_rivers_result.output_layer
    print("Close to Rivers layer created:", close_to_rivers_fl.url)

    # 7. Close to Coast
    close_to_coast_result = join_features(
        target_layer=erratics_layer,
        join_layer=coastlines_layer,
        spatial_relationship="intersects",
        distance=2000,  # e.g., 2 km
        distance_unit="Meters",
        join_type="keep_common",
        output_name="Erratics_Close_To_Coast"
    )
    close_to_coast_fl = close_to_coast_result.output_layer
    print("Close to Coast layer created:", close_to_coast_fl.url)

    # 8. Close to Forest
    # (If the forest layer has an attribute you must filter, do so. For example:
    #    forest_query = "Value = 1"
    #    forest_only = forest_layer.filter(where=forest_query)
    #    ... pass forest_only to join_features
    # For brevity, we assume we can use forest_layer directly.)
    close_to_forests_result = join_features(
        target_layer=erratics_layer,
        join_layer=forest_layer,
        spatial_relationship="intersects",
        distance=500,  # e.g., 0.5 km
        distance_unit="Meters",
        join_type="keep_common",
        output_name="Erratics_Close_To_Forests"
    )
    close_to_forests_fl = close_to_forests_result.output_layer
    print("Close to Forests layer created:", close_to_forests_fl.url)

    # 9. Above Certain Elevation
    #    We can do a local approach: check each Feature's elevation,
    #    create a separate SEDF of those above threshold, and publish.
    elev_threshold = 1500.0
    above_feats = []
    # for feat in erratics_fs.features:
    #     # get_elevation => returns dict with 'z'
    #     elev_info = get_elevation(geometry=feat.geometry, return_geoid=False)
    #     if elev_info['z'] >= elev_threshold:
    #         above_feats.append(feat)

    if above_feats:
        above_fs = FeatureSet(above_feats)
        above_sdf = above_fs.sdf
        above_item = above_sdf.spatial.to_featurelayer(
            title="Erratics_Above_Threshold",
            gis=portal,
            tags=["erratics", "elevation"],
            description=f"Erratics above {elev_threshold} m."
        )
        above_layer = above_item.layers[0]
        print("Created layer for erratics above threshold:", above_layer.url)
    else:
        print(f"No erratics found above {elev_threshold} m.")

    # 10. Visualize on a Web Map
    my_map = portal.map("USA", zoomlevel=4)
    if close_to_rivers_fl:
        my_map.add_layer(close_to_rivers_fl)
    if close_to_coast_fl:
        my_map.add_layer(close_to_coast_fl)
    if close_to_forests_fl:
        my_map.add_layer(close_to_forests_fl)
    # If we created the above threshold layer
    if above_feats:
        my_map.add_layer(above_layer)

    # Show the map in an interactive environment
    # (In a script, you might just export to HTML)
    # my_map

    # Export to HTML
    export_dir = os.path.join(os.getcwd(), "exported_maps")
    if not os.path.exists(export_dir):
        os.mkdir(export_dir)
    html_path = os.path.join(export_dir, "filtered_erratics.html")
    my_map.export_to_html(html_path, title="Filtered Glacial Erratics")
    print(f"Map exported to {html_path}")

if __name__ == "__main__":
    main()
