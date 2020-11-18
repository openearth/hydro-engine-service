import json

import ee
import flask_cors
from flask import request, Response
from flask import Blueprint

from hydroengine_service import liwo_functions

v1 = Blueprint("liwo-v1", __name__)
v2 = Blueprint('liwo-v2', __name__)


@v2.route('/get_liwo_scenarios', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def get_liwo_scenarios():
    r = request.get_json()

    # name of breach location as string
    liwo_ids = r['liwo_ids']
    # band name as string
    band = r['band']

    collection = 'projects/deltares-rws/liwo/2020_0_2'
    id_key = 'Scenario_ID'
    bands = {
        'waterdepth': 'waterdiepte',
        'velocity': 'stroomsnelheid',
        'riserate': 'stijgsnelheid',
        'damage': 'schade',
        'fatalities': 'slachtoffers',
        'affected': 'getroffenen',
        'arrivaltime': 'aankomsttijd'
    }
    reducers = {
        "waterdepth": "max",
        "velocity": "max",
        "riserate": "max",
        "damage": "max",
        "fatalities": "max",
        "affected": "max",
        "arrivaltime": "min"
    }

    assert band in bands
    band_name = bands[band]
    reducer = reducers[band]

    image = liwo_functions.filter_liwo_collection_v2(collection, id_key, liwo_ids, band_name, reducer)
    params = liwo_functions.get_liwo_styling(band)
    info = liwo_functions.generate_image_info(image, params)
    info['liwo_ids'] = liwo_ids
    info['band'] = band

    # Following needed for export:
    # Specify region over which to compute
    # export  is True or None/False
    if r.get('export'):
        region = ee.Geometry(r['region'])
        # scale of pixels for export, in meters
        info['scale'] = float(r['scale'])
        # coordinate system for export projection
        info['crs'] = r['crs']
        extra_info = liwo_functions.export_image_response(image, region, info)
        info.update(extra_info)

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )

@v1.route('/get_liwo_scenarios', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def get_liwo_scenarios():
    r = request.get_json()
    # name of breach location as string
    liwo_ids = r['liwo_ids']
    # band name as string
    band = r['band']

    collection = 'users/rogersckw9/liwo/liwo-scenarios-03-2019'
    id_key = 'LIWO_ID'
    bands = {
        'waterdepth': 'b1',
        'velocity': 'b2',
        'riserate': 'b3',
        'damage': 'b4',
        'fatalities': 'b5'
    }

    reducers = {
        'waterdepth': 'max',
        'velocity': 'max',
        'riserate': 'max',
        'damage': 'max',
        'fatalities': 'max'
    }
    # for now use max as a reducer
    assert band in bands
    assert band in reducers
    band_name = bands[band]
    reducer = reducers[band]
    image = liwo_functions.filter_liwo_collection_v1(collection, id_key, liwo_ids, band_name, reducer)

    params = liwo_functions.get_liwo_styling(band)

    info = liwo_functions.generate_image_info(image, params)
    info['liwo_ids'] = liwo_ids
    info['band'] = band

    # Following needed for export:
    # Specify region over which to compute
    # export  is True or None/False
    if r.get('export'):
        region = ee.Geometry(r['region'])
        # scale of pixels for export, in meters
        info['scale'] = float(r['scale'])
        # coordinate system for export projection
        info['crs'] = r['crs']
        extra_info = liwo_functions.export_image_response(image, region, info)
        info.update(extra_info)

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )
