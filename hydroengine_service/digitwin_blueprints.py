import json

import ee
import flask_cors
from flask import request, Response
from flask import Blueprint

from hydroengine_service import digitwin_functions

v1 = Blueprint("digitwin-v1", __name__)
v2 = Blueprint('digitwin-v2', __name__)


@v1.route('/get_windfarm_data', methods=['POST'])
@flask_cors.cross_origin()
def get_windfarm_data():
    r = request.get_json()

    features = r['features']
    collection = ee.FeatureCollection(features)


    ports = ee.FeatureCollection("projects/dgds-gee/worldlogistic/port")
    gebco = ee.Image("projects/dgds-gee/gebco/2019")
    coast = ee.Image("users/gena/land_polygons_image")
    wind = ee.Image("projects/dgds-gee/gwa/gwa3/10m").rename('wind_magnitude_mean')

    scale = 1000
    max_distance = 200000

    distanceToPort = (
        ports
        .distance(**{
            'searchRadius': max_distance,
            'maxError': 1000
        })
        .rename('distance_to_port')
    )

    distanceToCoast = (
        coast
        .mask()
        .resample('bicubic')
        .fastDistanceTransform()
        .sqrt()
        .reproject(ee.Projection('EPSG:3857').atScale(scale))
        .multiply(scale)
        .rename('distance_to_coast')
    )

    dataset = wind.addBands(gebco.rename('bathymetry'))
    dataset = dataset.addBands(distanceToPort)
    dataset = dataset.addBands(distanceToCoast)


    meanWindFarm = dataset.reduceRegions(**{
        "collection": collection,
        "reducer": ee.Reducer.mean(),
        "scale": 1000
    })
    # compute area
    meanWindFarm = meanWindFarm.map(digitwin.compute_area)
    print('area', meanWindFarm.getInfo())
    # compute grid parameters
    meanWindFarm = meanWindFarm.map(digitwin.create_turbine_grid)

    # do the rest local, we need scipy
    mean_wind_farm = meanWindFarm.getInfo()
    features = [
        digitwin.compute_feature(feature)
        for feature
        in mean_wind_farm['features']
    ]
    print(features)
    computed = geojson.FeatureCollection(features)
    response = Response(
        json.dumps(computed),
        status=200,
        mimetype='application/json'
    )
    return response
