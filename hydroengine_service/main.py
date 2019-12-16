#!/usr/bin/env python

# TODO: move out all non-flask code to a separate file / library

import base64
import json
import logging
import os

import ee
import numpy as np
import flask_cors
from flask import Flask
from flask import Response
from flask import request

from hydroengine_service import config
from hydroengine_service import error_handler

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)

logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-7.7s]  %(message)s")

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)

logger.addHandler(consoleHandler)

# if __name__ == '__main__':
#    import config
# else:
#    from . import config

app = Flask(__name__)

app.register_blueprint(error_handler.error_handler)

# if 'privatekey.json' is defined in environmental variable - write it to file
if 'key' in os.environ:
    print('Writing privatekey.json from environmental variable ...')
    content = base64.b64decode(os.environ['key']).decode('ascii')

    with open(config.EE_PRIVATE_KEY_FILE, 'w') as f:
        f.write(content)

# used for testing
if 'key_path' in os.environ:
    config.EE_PRIVATE_KEY_FILE = os.environ['key_path']

# Initialize the EE API.
# Use our App Engine service account's credentials.
EE_CREDENTIALS = ee.ServiceAccountCredentials(config.EE_ACCOUNT,
                                              config.EE_PRIVATE_KEY_FILE)

ee.Initialize(EE_CREDENTIALS)

# visualization parameters for datasets
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATASET_DIR = os.path.join(APP_DIR, 'datasets')
with open(DATASET_DIR + '/dataset_visualization_parameters.json') as json_file:
    DATASETS_VIS = json.load(json_file)

# HydroBASINS level 5
basins = {
    5: ee.FeatureCollection('users/gena/HydroEngine/hybas_lev05_v1c'),
    6: ee.FeatureCollection('users/gena/HydroEngine/hybas_lev06_v1c'),
    7: ee.FeatureCollection('users/gena/HydroEngine/hybas_lev07_v1c'),
    8: ee.FeatureCollection('users/gena/HydroEngine/hybas_lev08_v1c'),
    9: ee.FeatureCollection('users/gena/HydroEngine/hybas_lev09_v1c'),
}

# HydroSHEDS rivers, 15s
rivers = ee.FeatureCollection('users/gena/HydroEngine/riv_15s_lev06')

# HydroLAKES
lakes = ee.FeatureCollection('users/gena/HydroLAKES_polys_v10')

# available datasets for bathymetry
bathymetry = {
    'jetski': ee.ImageCollection('users/gena/eo-bathymetry/sandengine_jetski'),
    'vaklodingen': ee.ImageCollection('users/gena/vaklodingen'),
    'kustlidar': ee.ImageCollection('users/gena/eo-bathymetry/rws_lidar'),
    'jarkus': ee.ImageCollection('users/rogersckw9/eo-bathymetry/jarkus'),
    'ahn': ee.ImageCollection('users/rogersckw9/eo-bathymetry/ahn')
}

# graph index
index = ee.FeatureCollection('users/gena/HydroEngine/hybas_lev06_v1c_index')

monthly_water = ee.ImageCollection('JRC/GSW1_0/MonthlyHistory')


def get_upstream_catchments(level):
    if level != 6:
        raise Exception(
            'Currently, only level 6 is supported for upstream catchments')

    def _get_upstream_catchments(basin_source) -> ee.FeatureCollection:
        hybas_id = ee.Number(basin_source.get('HYBAS_ID'))
        upstream_ids = index.filter(
            ee.Filter.eq('hybas_id', hybas_id)).aggregate_array('parent_from')
        upstream_basins = basins[level].filter(
            ee.Filter.inList('HYBAS_ID', upstream_ids)).merge(
            ee.FeatureCollection([basin_source]))

        return upstream_basins

    return _get_upstream_catchments


def number_to_string(i):
    return ee.Number(i).format('%d')


# TODO: merge all bathymetric data sets (GEBCO, EMODnet, Vaklodingen, JetSki, NOAA LiDAR, ...)
# TODO: regurn multiple profiles
# TODO: add an argument in get_raster_profile(): reducer (max, min, mean, ...)
def reduceImageProfile(image, line, reducer, scale):
    length = line.length()
    distances = ee.List.sequence(0, length, scale)
    lines = line.cutLines(distances).geometries()

    def generate_line_segment(l):
        l = ee.List(l)
        geom = ee.Geometry(l.get(0))
        distance = ee.Geometry(l.get(1))

        geom = ee.Algorithms.GeometryConstructors.LineString(
            geom.coordinates())

        return ee.Feature(geom, {'distance': distance})

    lines = lines.zip(distances).map(generate_line_segment)
    lines = ee.FeatureCollection(lines)

    # reduce image for every segment
    band_names = image.bandNames()

    return image.reduceRegions(lines, reducer.setOutputs(band_names), scale)


@app.route('/get_image_urls', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def api_get_image_urls():
    logger.warning(
        'get_image_urls is no longer supported, please update to get_bathymetry'
    )
    r = request.get_json()
    dataset = r[
        'dataset']  # bathymetry_jetski | bathymetry_vaklodingen | dem_srtm | ...
    t_begin = ee.Date(r['begin_date'])
    t_end = ee.Date(r['end_date'])
    t_step = r['step']
    t_interval = r['interval']

    t_step_units = 'day'
    t_interval_unit = 'day'

    # TODO: let t_count be dependent on begin_date - end_date
    # TODO: Make option for how the interval is chosen (now only forward)
    t_count = 10

    rasters = {
        'bathymetry_jetski': bathymetry['jetski'],
        'bathymetry_vaklodingen': bathymetry['vaklodingen'],
        'bathymetry_lidar': bathymetry['kustlidar']
    }

    colorbar_min = {
        'bathymetry_jetski': -12,
        'bathymetry_vaklodingen': -1200,
        'bathymetry_lidar': -1200
    }

    colorbar_max = {
        'bathymetry_jetski': 7,
        'bathymetry_vaklodingen': 700,
        'bathymetry_lidar': 700
    }

    sandengine_pallete = '''#000033,#000037,#00003a,#00003e,#000042,#000045,#000049,#00004d,#000050,#000054,#000057,#00005b,#00005f,#000062,#000066,#010268,#03036a,#04056c,#05076e,#070971,#080a73,#0a0c75,#0b0e77,#0c1079,#0e117b,#0f137d,#10157f,#121781,#131884,#141a86,#161c88,#171e8a,#191f8c,#1a218e,#1b2390,#1d2492,#1e2695,#1f2897,#212a99,#222b9b,#242d9d,#252f9f,#2a35a2,#2e3ca6,#3342a9,#3848ac,#3c4faf,#4155b3,#465cb6,#4a62b9,#4f68bc,#546fc0,#5875c3,#5d7bc6,#6282ca,#6688cd,#6b8fd0,#7095d3,#749bd7,#79a2da,#7ea8dd,#82aee0,#87b5e4,#8cbbe7,#90c2ea,#95c8ed,#9acef1,#9ed5f4,#a3dbf7,#a8e1fa,#9edef7,#94daf4,#8ad6f0,#80d2ed,#84cacb,#87c2a9,#8bba87,#8eb166,#92a944,#95a122,#999900,#a4a50b,#afb116,#babd21,#c5c92c,#d0d537,#dce142,#e7ec4d,#f2f857,#f3f658,#f3f359,#f4f15a,#f5ee5b,#f6eb5c,#f6e95d,#f7e65d,#f8e35e,#f9e15f,#fade60,#fadc61,#fbd962,#fcd663,#fdd463,#fdd164,#fecf65,#ffcc66,#fdc861,#fcc55d,#fbc158,#f9be53,#f7ba4f,#f6b64a,#f5b346,#f3af41,#f1ac3c,#f0a838,#efa433,#eda12e,#eb9d2a,#ea9a25,#e99620,#e7931c,#e58f17,#e48b13,#e3880e,#e18409,#df8105,#de7d00'''

    raster = rasters[dataset]

    def generate_average_image(i):
        b = t_begin.advance(ee.Number(t_step).multiply(i), t_step_units)
        e = b.advance(t_interval, t_interval_unit)

        images = raster.filterDate(b, e)

        reducer = ee.Reducer.mean()

        return images.reduce(reducer).set('begin', b).set('end', e)

    def generate_image_info(image):
        image = ee.Image(image)
        m = image.getMapId(
            {
                'min': colorbar_min[dataset],
                'max': colorbar_max[dataset],
                'palette': sandengine_pallete
            }
        )

        mapid = m.get('mapid')
        token = m.get('token')

        url = 'https://earthengine.googleapis.com/map/{0}/{{z}}/{{x}}/{{y}}?token={1}'.format(
            mapid, token)

        begin = image.get('begin').getInfo()

        end = image.get('end').getInfo()

        return {'mapid': mapid, 'token': token, 'url': url, 'begin': begin,
                'end': end}

    images = ee.List.sequence(0, t_count).map(generate_average_image)

    infos = [generate_image_info(images.get(i)) for i in
             range(images.size().getInfo())]

    resp = Response(json.dumps(infos), status=200, mimetype='application/json')

    return resp


@app.route('/get_sea_surface_height_time_series', methods=['POST'])
@flask_cors.cross_origin()
def get_sea_surface_height_time_series():
    """generate bathymetry image for a certain timespan (begin_date, end_date) and a dataset {jetski | vaklodingen | kustlidar}"""
    r = request.get_json()

    # get info from the request
    dataset = r['region']
    print(dataset)

    scale = 30

    if 'scale' in r:
        scale = float(r['scale'])

    region = ee.Geometry(dataset)
    images = ee.ImageCollection("users/fbaart/ssh_grids_v1609")

    ssh_list = images.getRegion(region, scale, 'EPSG:4326')

    ssh_rows = ssh_list.slice(1).map(
        lambda x: {'t': ee.List(x).get(3), 'v': ee.List(x).get(4)}
    )

    return Response(json.dumps(ssh_rows.getInfo()), status=200, mimetype='application/json')


@app.route('/get_sea_surface_height_trend_image', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def get_sea_surface_height_trend_image():
    """generate bathymetry image for a certain timespan (begin_date, end_date) and a dataset {jetski | vaklodingen | kustlidar}"""
    r = request.get_json()

    image = ee.Image('users/fbaart/ssh-trend-map')

    image = image.visualize(**{'bands': ['time'], 'min': -0.03, 'max': 0.03,
                               'palette': ["151d44", "156c72", "7eb390",
                                           "fdf5f4", "db8d77", "9c3060",
                                           "340d35"]})

    m = image.getMapId()

    mapid = m.get('mapid')
    token = m.get('token')

    url = 'https://earthengine.googleapis.com/map/{0}/{{z}}/{{x}}/{{y}}?token={1}'.format(
        mapid, token)

    response = Response(json.dumps({'url': url}), status=200,
                        mimetype='application/json')

    return response


def radians(image):
    """
    Converts image from degrees to radians
    """

    return ee.Image(image).toFloat().multiply(3.1415927).divide(180)


def hillshade(image_rgb, elevation, reproject, height_multiplier=500,  weight=1.2):
    """
    Styles RGB image using hillshading, mixes RGB and hillshade using HSV<->RGB transform
    """

    # height multiplier

    azimuth = 315
    zenith = 40

    hsv = image_rgb.unitScale(0, 255).rgbToHsv()

    if reproject:
        z = elevation.reproject(ee.Projection('EPSG:3857').atScale(30)).multiply(ee.Image.constant(height_multiplier))
    else:
        z = elevation.multiply(ee.Image.constant(height_multiplier))

    terrain = ee.Algorithms.Terrain(z)
    slope = radians(terrain.select(['slope']))
    aspect = radians(terrain.select(['aspect'])).resample('bicubic')
    azimuth = radians(ee.Image.constant(azimuth))
    zenith = radians(ee.Image.constant(zenith))

    hs = azimuth.subtract(aspect).cos().multiply(slope.sin()).multiply(zenith.sin()).add(
        zenith.cos().multiply(slope.cos())).resample('bicubic')
    intensity = hs.multiply(ee.Image.constant(weight)).multiply(hsv.select('value'))
    huesat = hsv.select('hue', 'saturation')

    return ee.Image.cat(huesat, intensity).hsvToRgb()


@app.route('/get_bathymetry', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def api_get_bathymetry():
    """generate bathymetry image for a certain timespan (begin_date, end_date) and a dataset {jetski | vaklodingen | kustlidar}"""
    r = request.get_json()

    # get info from the request
    dataset = r['dataset']
    begin_date = ee.Date(r['begin_date'])
    end_date = ee.Date(r['end_date'])

    colorbar_min = {
        'jetski': -12,
        'vaklodingen': -1200,
        # TODO: specify units in the dataset
        'kustlidar': -1200,
        'jarkus': -30,
        'ahn': -30
    }

    colorbar_max = {
        'jetski': 7,
        'vaklodingen': 700,
        'kustlidar': 700,
        'jarkus': 10,
        'ahn': 10
    }

    palettes = {
        'jetski': '''#000033,#000037,#00003a,#00003e,#000042,#000045,#000049,#00004d,#000050,#000054,#000057,#00005b,#00005f,#000062,#000066,#010268,#03036a,#04056c,#05076e,#070971,#080a73,#0a0c75,#0b0e77,#0c1079,#0e117b,#0f137d,#10157f,#121781,#131884,#141a86,#161c88,#171e8a,#191f8c,#1a218e,#1b2390,#1d2492,#1e2695,#1f2897,#212a99,#222b9b,#242d9d,#252f9f,#2a35a2,#2e3ca6,#3342a9,#3848ac,#3c4faf,#4155b3,#465cb6,#4a62b9,#4f68bc,#546fc0,#5875c3,#5d7bc6,#6282ca,#6688cd,#6b8fd0,#7095d3,#749bd7,#79a2da,#7ea8dd,#82aee0,#87b5e4,#8cbbe7,#90c2ea,#95c8ed,#9acef1,#9ed5f4,#a3dbf7,#a8e1fa,#9edef7,#94daf4,#8ad6f0,#80d2ed,#84cacb,#87c2a9,#8bba87,#8eb166,#92a944,#95a122,#999900,#a4a50b,#afb116,#babd21,#c5c92c,#d0d537,#dce142,#e7ec4d,#f2f857,#f3f658,#f3f359,#f4f15a,#f5ee5b,#f6eb5c,#f6e95d,#f7e65d,#f8e35e,#f9e15f,#fade60,#fadc61,#fbd962,#fcd663,#fdd463,#fdd164,#fecf65,#ffcc66,#fdc861,#fcc55d,#fbc158,#f9be53,#f7ba4f,#f6b64a,#f5b346,#f3af41,#f1ac3c,#f0a838,#efa433,#eda12e,#eb9d2a,#ea9a25,#e99620,#e7931c,#e58f17,#e48b13,#e3880e,#e18409,#df8105,#de7d00''',
        'vaklodingen': '''#9900FF,#9900FF,#8810FF,#7621FF,#6532FF,#4354FF,#3265FF,#2176FF,#0099FF,#1AA4FF,#35AFFF,#6BC5FF,#86D0FF,#A1DBFF,#D7F1FF,#D9E0A3,#F3CA89,#E2B247,#B89E21,#A49018''',
        'kustlidar': '''#000033,#000037,#00003a,#00003e,#000042,#000045,#000049,#00004d,#000050,#000054,#000057,#00005b,#00005f,#000062,#000066,#010268,#03036a,#04056c,#05076e,#070971,#080a73,#0a0c75,#0b0e77,#0c1079,#0e117b,#0f137d,#10157f,#121781,#131884,#141a86,#161c88,#171e8a,#191f8c,#1a218e,#1b2390,#1d2492,#1e2695,#1f2897,#212a99,#222b9b,#242d9d,#252f9f,#2a35a2,#2e3ca6,#3342a9,#3848ac,#3c4faf,#4155b3,#465cb6,#4a62b9,#4f68bc,#546fc0,#5875c3,#5d7bc6,#6282ca,#6688cd,#6b8fd0,#7095d3,#749bd7,#79a2da,#7ea8dd,#82aee0,#87b5e4,#8cbbe7,#90c2ea,#95c8ed,#9acef1,#9ed5f4,#a3dbf7,#a8e1fa,#9edef7,#94daf4,#8ad6f0,#80d2ed,#84cacb,#87c2a9,#8bba87,#8eb166,#92a944,#95a122,#999900,#a4a50b,#afb116,#babd21,#c5c92c,#d0d537,#dce142,#e7ec4d,#f2f857,#f3f658,#f3f359,#f4f15a,#f5ee5b,#f6eb5c,#f6e95d,#f7e65d,#f8e35e,#f9e15f,#fade60,#fadc61,#fbd962,#fcd663,#fdd463,#fdd164,#fecf65,#ffcc66,#fdc861,#fcc55d,#fbc158,#f9be53,#f7ba4f,#f6b64a,#f5b346,#f3af41,#f1ac3c,#f0a838,#efa433,#eda12e,#eb9d2a,#ea9a25,#e99620,#e7931c,#e58f17,#e48b13,#e3880e,#e18409,#df8105,#de7d00''',
        'jarkus': '''#9900FF,#9900FF,#8810FF,#7621FF,#6532FF,#4354FF,#3265FF,#2176FF,#0099FF,#1AA4FF,#35AFFF,#6BC5FF,#86D0FF,#A1DBFF,#D7F1FF,#D9E0A3,#F3CA89,#E2B247,#B89E21,#A49018''',
        'ahn': '''#9900FF,#9900FF,#8810FF,#7621FF,#6532FF,#4354FF,#3265FF,#2176FF,#0099FF,#1AA4FF,#35AFFF,#6BC5FF,#86D0FF,#A1DBFF,#D7F1FF,#D9E0A3,#F3CA89,#E2B247,#B89E21,#A49018'''
    }

    def sorted_composite(images):
        '''Create a sorted composite of the images between begin and end time, based on the system:time_start attribute'''
        # sort by system time
        sorted_images = images.sort('system:time_start', False)
        # take first non missing pixel
        sorted_composite = sorted_images.reduce(
            ee.Reducer.firstNonNull()
        )
        # store metadata
        return sorted_composite

    def generate_mean_image(images):
        reducer = ee.Reducer.mean()
        mean_composite = images.reduce(reducer)
        return mean_composite

    image_min = colorbar_min[dataset]
    image_max = colorbar_max[dataset]
    image_palette = palettes[dataset]

    if 'min' in r:
        image_min = r['min']

    if 'max' in r:
        image_max = r['max']

    if 'palette' in r:
        image_palette = r['palette']

    def generate_image_info(image):
        """generate url and tokens for image"""
        image = ee.Image(image)
        image_vis = image.visualize(**{
            'min': image_min,
            'max': image_max,
            'palette': image_palette
        })

        print(image_min, image_max)

        if 'hillshade' in r and r['hillshade']:
            image_vis = hillshade(image_vis,
                                  image.subtract(image_min).divide(ee.Image.constant(image_max).subtract(image_min)),
                                  True)

        m = image_vis.getMapId()

        mapid = m.get('mapid')
        token = m.get('token')

        url = 'https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}'.format(
            mapid=mapid,
            token=token
        )

        result = {
            'mapid': mapid,
            'token': token,
            'url': url
        }
        return result

    # filter by date
    images = bathymetry[dataset].filterDate(begin_date, end_date)

    # create composite
    image = sorted_composite(images)

    # add metadata
    info = generate_image_info(image)

    info['begin'] = r['begin_date']
    info['end'] = r['end_date']
    info['palette'] = image_palette

    if "hillshade" in r:
        info["hillshade"] = r["hillshade"]

    resp = Response(json.dumps(info), status=200, mimetype='application/json')
    return resp


@app.route('/get_raster_profile', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def api_get_raster_profile():
    r = request.get_json()

    polyline = ee.Geometry(r['polyline'])
    scale = float(r['scale'])
    dataset = r[
        'dataset']  # bathymetry_jetski | bathymetry_vaklodingen | dem_srtm | ...
    begin_date = r['begin_date']
    end_date = r['end_date']

    rasters = {
        'bathymetry_jetski': bathymetry['jetski'],
        'bathymetry_vaklodingen': bathymetry['vaklodingen'],
        'bathymetry_lidar': bathymetry['kustlidar']
    }

    raster = rasters[dataset]

    if begin_date:
        raster = raster.filterDate(begin_date, end_date)

    reducer = ee.Reducer.mean()

    raster = raster.reduce(reducer)

    data = reduceImageProfile(raster, polyline, reducer, scale).getInfo()

    # fill response
    resp = Response(json.dumps(data), status=200, mimetype='application/json')

    return resp


@app.route('/get_water_mask_raw', methods=['POST'])
def get_water_mask_raw():
    """
    Extracts water mask from raw satellite data.

    Code Editor URL:
    https://code.earthengine.google.com/4dd0b18aa43bfabf4845753dc7c6ba5c
    """

    j = request.json

    use_url = j['use_url']
    region = ee.Geometry(j['region'])
    bands = ['B3', 'B8']  # green, nir
    start = j['start']
    stop = j['stop']

    percentile = j['percentile'] if 'percentile' in j else 10
    ndwi_threshold = j['ndwi_threshold'] if 'ndwi_threshold' in j else 0
    scale = j['scale'] if 'scale' in j else 10

    # filter Sentinel-2 images
    images = ee.ImageCollection('COPERNICUS/S2') \
        .select(bands) \
        .filterBounds(region) \
        .filterDate(start, stop) \
        .map(lambda i: i.resample('bilinear'))

    # remove noise (clouds, shadows) using percentile composite
    image = images \
        .reduce(ee.Reducer.percentile([percentile])) \
 \
        # computer water mask using NDWI
    water_mask = image \
        .normalizedDifference() \
        .gt(ndwi_threshold)

    # vectorize
    water_mask_vector = water_mask \
        .mask(water_mask) \
        .reduceToVectors(**{
        "geometry": region,
        "scale": scale / 2
    })

    water_mask_vector = water_mask_vector.toList(10000) \
        .map(lambda o: ee.Feature(o).simplify(scale))

    water_mask_vector = ee.FeatureCollection(water_mask_vector)

    # create response
    if use_url:
        url = water_mask_vector.getDownloadURL('json')
        data = {'url': url}
    else:
        data = water_mask_vector.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


def get_water_mask_vector(region, scale, start, stop):
    #  water occurrence(monthly)
    water_occurrence = monthly_water \
        .filterDate(start, stop) \
        .map(lambda i: i.unmask(0).resample('bicubic')) \
        .map(lambda i: i.eq(2).updateMask(i.neq(0)))
    water_occurrence = water_occurrence.sum().divide(water_occurrence.count())

    # computer water mask
    water_mask = water_occurrence.gt(0.3)

    # clean-up
    water_mask = water_mask \
        .focal_mode(scale * 3, 'circle', 'meters')

    # vectorize
    water_mask_vector = water_mask.mask(water_mask) \
        .reduceToVectors(**{"geometry": region,
                            "scale": scale / 2,
                            "tileScale": 4})

    # take the largest
    water_mask_vector = water_mask_vector \
        .map(lambda o: o.set({"area": o.area(scale)}))

    water_mask_vector = ee.Feature(
        water_mask_vector.sort('area', False).first()
    )

    # simplify
    water_mask_vector = water_mask_vector.simplify(scale * 1.5)

    water_mask_vector = ee.FeatureCollection(water_mask_vector)

    return water_mask_vector


def transform_feature(crs, scale):
    return lambda f: f.transform(ee.Projection(crs).atScale(scale),
                                 ee.Number(scale).divide(100))


@app.route('/get_water_mask', methods=['POST', 'GET'])
def get_water_mask():
    """
    Code Editor URL: https://code.earthengine.google.com/81a463e6f4c9afc607086ece6de8d163
    """

    j = request.json

    use_url = j['use_url']
    region = ee.Geometry(j['region'])
    start = j['start']
    stop = j['stop']
    scale = j['scale']
    crs = j['crs']

    water_mask_vector = get_water_mask_vector(region, scale, start, stop)

    water_mask_vector = water_mask_vector.map(transform_feature(crs, scale))

    # create response
    if use_url:
        url = water_mask_vector.getDownloadURL('json')
        data = {'url': url}
    else:
        data = water_mask_vector.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


def generate_perimeter_points(geom, step):
    """
    Generates points along interiors and exteriors
    :param geom:
    :param step:
    :return:
    """
    error = ee.ErrorMargin(1, 'meters')

    p = geom.perimeter(error)

    n = p.divide(step).int()

    step = p.divide(n)

    # map over exterior and interiors
    def wrap_ring(coords):
        ring = ee.Geometry.LineString(coords)
        distances = ee.List.sequence(0, ring.length(error), step)

        return ee.Feature(ring) \
            .set({"distances": distances}) \
            .set({"distancesCount": distances.length()})

    rings = geom.coordinates().map(wrap_ring)

    rings = ee.FeatureCollection(rings)

    def generate_points(ring):
        distances = ring.get('distances')
        segments = ring.geometry().cutLines(distances).geometries()

        segment_points = \
            segments.map(lambda g: ee.Feature(ee.Geometry(g).centroid(1)))

        return ee.FeatureCollection(segment_points)

    points = rings \
        .filter(ee.Filter.gt('distancesCount', 2)) \
        .map(generate_points) \
        .flatten()

    return ee.FeatureCollection(points)


def generate_voronoi_polygons(points, scale, aoi):
    """
    Generates Voronoi polygons
    :param points:
    :param scale:
    :param aoi:
    :return:
    """

    error = ee.ErrorMargin(1, 'projected')
    # proj = ee.Projection('EPSG:3857').atScale(scale)
    proj = ee.Projection('EPSG:4326').atScale(scale)

    distance = ee.Image(0).float().paint(points, 1) \
        .fastDistanceTransform().sqrt().clip(aoi) \
        .reproject(proj)

    concavity = distance.convolve(ee.Kernel.laplacian8()) \
        .reproject(proj)

    concavity = concavity.multiply(distance)

    concavityTh = 0

    edges = concavity.lt(concavityTh)

    # label connected components
    connected = edges.Not() \
        .connectedComponents(ee.Kernel.circle(1), 256) \
        .clip(aoi) \
        .focal_max(scale * 3, 'circle', 'meters') \
        .focal_min(scale * 3, 'circle', 'meters') \
        .focal_mode(scale * 5, 'circle', 'meters') \
        .reproject(proj)

    # fixing reduceToVectors() bug, remap to smaller int
    def fixOverflowError(i):
        hist = i.reduceRegion(ee.Reducer.frequencyHistogram(), aoi, scale)
        uniqueLabels = ee.Dictionary(ee.Dictionary(hist).get('labels')).keys() \
            .map(lambda o: ee.Number.parse(o))

        labels = ee.List.sequence(0, uniqueLabels.size().subtract(1))

        return i.remap(uniqueLabels, labels).rename('labels').int()

    connected = fixOverflowError(connected).reproject(proj)

    polygons = connected.select('labels').reduceToVectors(**{
        "scale": scale,
        "crs": proj,
        "geometry": aoi,
        "eightConnected": True,
        "labelProperty": 'labels',
        "tileScale": 4
    })

    # polygons = polygons.map(lambda o: o.snap(error, proj))

    return {"polygons": polygons, "distance": distance}


def generate_skeleton_from_voronoi(scale, water_vector):
    # step between points along perimeter
    step = scale * 10
    simplify_centerline_factor = 15

    error = ee.ErrorMargin(1, 'meters')

    # proj = ee.Projection('EPSG:3857').atScale(scale)
    proj = ee.Projection('EPSG:4326').atScale(scale)

    # turn water mask into a skeleton
    def add_coords_count(o):
        return ee.Feature(None, {"count": ee.List(o).length(), "values": o})

    c = water_vector.geometry().coordinates()
    exterior = c.get(0)

    interior = c.slice(1).map(add_coords_count)
    interior = ee.FeatureCollection(interior)
    interior = interior.filter(ee.Filter.gt('count', 5))
    interior = interior.toList(10000).map(
        lambda o: ee.Feature(o).get('values'))

    water_vector = ee.Feature(
        ee.Geometry.Polygon(ee.List([exterior]).cat(interior)))

    geometry = water_vector.geometry()

    geometry_buffer = geometry.buffer(scale * 4, error)

    perimeter_geometry = geometry_buffer \
        .difference(geometry_buffer.buffer(-scale * 2, error), error)

    geometry = geometry_buffer

    points = generate_perimeter_points(geometry, step)

    output = generate_voronoi_polygons(points, scale, geometry)

    polygons = output["polygons"]
    distance = output["distance"]

    dist_filter = ee.Filter.And(
        ee.Filter.intersects(
            **{"leftField": ".geo", "rightField": ".geo", "maxError": error}),
        ee.Filter.equals(
            **{"leftField": "labels", "rightField": "labels"}).Not()
    )

    dist_save_all = ee.Join.saveAll(**{"matchesKey": 'matches'})

    features = dist_save_all.apply(polygons, polygons, dist_filter)

    # find intersection with neighbouring polygons
    def find_neighbours(ff1):
        matches = ee.FeatureCollection(ee.List(ff1.get('matches')))

        def find_neighbours2(ff2):
            i = ff2.intersection(ff1, error, proj)
            t = i.intersects(perimeter_geometry, error, proj)
            m = i.intersects(geometry, error, proj)

            return i.set({"touchesPerimeter": t}).set(
                {"intersectsWithMask": m})

        return matches.map(find_neighbours2)

    features = features.map(find_neighbours).flatten()

    # find a centerline
    f = ee.Filter.And(ee.Filter.eq('touchesPerimeter', False),
                      ee.Filter.eq('intersectsWithMask', True))
    centerline = features.filter(f)
    centerline = centerline.geometry().dissolve(scale, proj) \
        .simplify(scale * simplify_centerline_factor, proj)
    centerline = centerline.geometries().map(
        lambda g: ee.Feature(ee.Geometry(g)))
    centerline = ee.FeatureCollection(centerline)
    centerline = centerline \
        .map(lambda o: o.set({"type": o.geometry().type()})) \
        .filter(ee.Filter.eq('type', 'LineString')) \
        # .map(lambda o: o.transform(ee.Projection('EPSG:4326').atScale(scale)), error)

    return {"centerline": centerline, "distance": distance}


@app.route('/get_water_network', methods=['POST'])
def get_water_network():
    """
    Skeletonize water mask given boundary, converts it into a network
    (undirected graph) and generates a feature collection
    Script: https://code.earthengine.google.com/da4dd67e84910ca42c4f82c41e7f9bcb
    """

    j = request.json

    region = ee.Geometry(j['region'])
    start = j['start']
    stop = j['stop']
    scale = j['scale']
    crs = j['crs']

    # get water mask
    water_vector = get_water_mask_vector(region, scale, start, stop)

    # skeletonize
    output = generate_skeleton_from_voronoi(scale, water_vector)
    centerline = output["centerline"]

    centerline = centerline.map(
        lambda line: line.set('length', line.length(scale / 10)))

    centerline = centerline.map(transform_feature(crs, scale))

    # create response
    data = centerline.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@app.route('/get_water_network_properties', methods=['POST'])
def get_water_network_properties():
    """
    Generates variables along water skeleton network polylines.
    """

    j = request.json

    region = ee.Geometry(j['region'])
    start = j['start']
    stop = j['stop']
    scale = j['scale']

    step = j['step']

    crs = j['crs']

    error = ee.ErrorMargin(scale / 2, 'meters')

    if 'network' in j:
        raise Exception(
            'TODO: re-using existing networks is not supported yet')

    # get water mask
    water_vector = get_water_mask_vector(region, scale, start, stop)

    # skeletonize
    output = generate_skeleton_from_voronoi(scale, water_vector)
    centerline = ee.FeatureCollection(output["centerline"])
    distance = ee.Image(output["distance"])

    # generate width at every offset
    centerline = centerline.map(
        lambda line: line.set("length", line.length(error)))

    short_lines = centerline.filter(ee.Filter.lte('length', step))
    long_lines = centerline.filter(ee.Filter.gt('length', step))

    def process_long_line(line):
        line_length = line.length(error)
        distances = ee.List.sequence(0, line_length, step)
        segments = line.geometry().cutLines(distances, error)

        def generate_line_middle_point(pair):
            pair = ee.List(pair)

            s = ee.Geometry(pair.get(0))
            offset = ee.Number(pair.get(1))

            centroid = ee.Geometry.Point(s.coordinates().get(0))

            return ee.Feature(centroid) \
                .set("lineId", line.id()) \
                .set("offset", offset)

        segments = segments.geometries().zip(distances) \
            .map(generate_line_middle_point)

        return ee.FeatureCollection(segments)

    long_line_points = long_lines.map(process_long_line).flatten()

    def process_short_line(line):
        geom = line.geometry(error, 'EPSG:4326')

        geom = ee.Geometry.Point(geom.coordinates().get(0), 'EPSG:4326')

        return ee.Feature(geom) \
            .set("lineId", line.id()) \
            .set("offset", 0)

    short_line_points = short_lines.map(process_short_line)

    points = long_line_points.merge(short_line_points)

    fa = ee.Image('WWF/HydroSHEDS/15ACC')
    dem = ee.Image('JAXA/ALOS/AW3D30_V1_1').select('MED')

    def add_flow_accumulation(pt):
        flow_accumulation = fa.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=pt.geometry().buffer(scale * 10),
            scale=scale).values().get(0)

        return pt \
            .set("flow_accumulation", ee.Number(flow_accumulation))

    def add_width(pt):
        width = distance.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=pt.geometry(),
            scale=scale).values().get(0)

        return pt \
            .set("width", ee.Number(width).multiply(scale).multiply(2))

    def add_elevation(pt):
        elevation = dem.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=pt.geometry().buffer(scale * 10),
            scale=scale).values().get(0)

        return pt \
            .set("elevation", ee.Number(elevation))

    points = points.map(add_width)
    points = points.map(add_elevation)
    points = points.map(add_flow_accumulation)

    points = points.map(transform_feature(crs, scale))

    # create response
    data = points.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@app.route('/get_catchments', methods=['GET', 'POST'])
def api_get_catchments():
    region = ee.Geometry(request.json['region'])
    region_filter = request.json['region_filter']
    catchment_level = request.json['catchment_level']

    if region_filter == 'region':
        raise Exception(
            'Value is not supported, use either catchments-upstream '
            'or catchments-intersection')

    selection = basins[catchment_level].filterBounds(region)

    if region_filter == 'catchments-upstream':
        print('Getting upstream catchments ..')

        # for every selection, get and merge upstream
        upstream_catchments = ee.FeatureCollection(
            selection.map(get_upstream_catchments(catchment_level))) \
            .flatten().distinct('HYBAS_ID')
    else:
        print('Getting intersected catchments ..')

        upstream_catchments = selection

    # dissolve output
    # TODO: dissolve output

    # get GeoJSON
    # TODO: use ZIP to prevent 5000 feature limit
    data = upstream_catchments.getInfo()

    # fill response
    resp = Response(json.dumps(data), status=200, mimetype='application/json')

    return resp


@app.route('/get_rivers', methods=['GET', 'POST'])
def api_get_rivers():
    region = ee.Geometry(request.json['region'])
    region_filter = request.json['region_filter']
    catchment_level = request.json['catchment_level']

    # TODO: add support for region-only

    logger.debug("Region filter: %s" % region_filter)

    selected_catchments = basins[catchment_level].filterBounds(region)
    if region_filter == 'catchments-upstream':
        # for every selection, get and merge upstream catchments
        selected_catchments = ee.FeatureCollection(
            selected_catchments.map(get_upstream_catchments(catchment_level))) \
            .flatten().distinct('HYBAS_ID')

    # get ids
    upstream_catchment_ids = ee.List(
        selected_catchments.aggregate_array('HYBAS_ID'))

    logger.debug("Number of catchments: %s" %
                 repr(upstream_catchment_ids.size().getInfo()))

    # query rivers
    selected_rivers = rivers \
        .filter(ee.Filter.inList('HYBAS_ID', upstream_catchment_ids)) \
        .select(['ARCID', 'UP_CELLS', 'HYBAS_ID'])

    # filter upstream branches
    if 'filter_upstream_gt' in request.json:
        filter_upstream = int(request.json['filter_upstream_gt'])
        logger.debug(
            'Filtering upstream branches, limiting by {0} number of cells'.format(
                filter_upstream))
        selected_rivers = selected_rivers.filter(
            ee.Filter.gte('UP_CELLS', filter_upstream))

    logger.debug("Number of river branches: %s"
                 % selected_rivers.aggregate_count('ARCID').getInfo())

    # BUG in EE? getDownloadURL skips geometry
    # logger.debug('%s' % selected_rivers.limit(1).getInfo())
    # logger.debug('%s' % selected_rivers.limit(1).getDownloadURL('json'))

    # create response
    # url = selected_rivers.getDownloadURL('json')

    # data = {'url': url}

    data = selected_rivers.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')

    # data = selected_rivers.getInfo()  # TODO: use ZIP to prevent 5000 features limit
    # return Response(json.dumps(data), status=200, mimetype='application/octet-stream')

    # zip = zipfile.ZipFile(io.BytesIO(response.content))
    #
    # data = {
    #     'catchment_rivers': zip.namelist()
    # }
    #
    # resp = Response(json.dumps(data), status=200, mimetype='application/json')
    #
    # return resp


@app.route('/get_lakes', methods=['GET', 'POST'])
def api_get_lakes():
    region = ee.Geometry(request.json['region'])
    id_only = bool(request.json['id_only'])

    # query lakes
    selected_lakes = ee.FeatureCollection(lakes.filterBounds(region))

    if id_only:
        print('Getting lake ids only ... ')
        ids = selected_lakes.aggregate_array('Hylak_id')
        print(ids.getInfo())

        return Response(json.dumps(ids.getInfo()), status=200,
                        mimetype='application/json')

    # create response
    url = selected_lakes.getDownloadURL('json')

    data = {'url': url}

    return Response(json.dumps(data), status=200, mimetype='application/json')


@app.route('/get_lake_by_id', methods=['GET', 'POST'])
def get_lake_by_id():
    lake_id = int(request.json['lake_id'])

    lake = ee.Feature(ee.FeatureCollection(
        lakes.filter(ee.Filter.eq('Hylak_id', lake_id))).first())

    return Response(json.dumps(lake.getInfo()), status=200,
                    mimetype='application/json')


def get_lake_water_area(lake_id, scale):
    f = ee.Feature(lakes.filter(ee.Filter.eq('Hylak_id', lake_id)).first())

    def get_monthly_water_area(i):
        # get water mask
        water = i.clip(f).eq(2)

        s = scale
        if not scale:
            # estimate scale from reservoir surface area, currently
            coords = ee.List(f.geometry().bounds().transform('EPSG:3857',
                                                             30).coordinates().get(
                0))
            ll = ee.List(coords.get(0))
            ur = ee.List(coords.get(2))
            width = ee.Number(ll.get(0)).subtract(ur.get(0)).abs()
            height = ee.Number(ll.get(1)).subtract(ur.get(1)).abs()
            size = width.max(height)

            MAX_PIXEL_COUNT = 1000

            s = size.divide(MAX_PIXEL_COUNT).max(30)

            print('Automatically estimated scale is: ' + str(s.getInfo()))

        # compute water area
        water_area = water.multiply(ee.Image.pixelArea()).reduceRegion(
            ee.Reducer.sum(), f.geometry(), s).values().get(0)

        return ee.Feature(None, {'time': i.date().millis(),
                                 'water_area': water_area})

    area = monthly_water.map(get_monthly_water_area)

    area_values = area.aggregate_array('water_area')
    area_times = area.aggregate_array('time')

    return {'time': area_times.getInfo(), 'water_area': area_values.getInfo()}


@app.route('/get_lake_time_series', methods=['GET', 'POST'])
def api_get_lake_time_series():
    lake_id = int(request.json['lake_id'])
    variable = str(request.json['variable'])

    scale = None
    if 'scale' in request.json:
        scale = int(request.json['scale'])

    if variable == 'water_area':
        ts = get_lake_water_area(lake_id, scale)

        return Response(json.dumps(ts), status=200,
                        mimetype='application/json')

    return Response('Unknown variable', status=404,
                    mimetype='application/json')


@app.route('/get_feature_collection', methods=['GET', 'POST'])
def api_get_feature_collection():
    region = ee.Geometry(request.json['region'])

    asset = request.json['asset']

    features = ee.FeatureCollection(asset)

    region_feature = ee.Feature(region)

    # clip
    def clip_feature(feature):
        return feature.intersection(region_feature)

    features = features.filterBounds(region) \
        .map(clip_feature)

    data = features.getInfo()

    str = json.dumps(data)

    return Response(str, status=200, mimetype='application/json')


@app.route('/get_raster', methods=['GET', 'POST'])
def api_get_raster():
    variable = request.json['variable']
    region = ee.Geometry(request.json['region'])
    cell_size = float(request.json['cell_size'])
    crs = request.json['crs']
    region_filter = request.json['region_filter']
    catchment_level = request.json['catchment_level']

    if region_filter == 'catchments-upstream':
        selection_basins = basins[catchment_level].filterBounds(region)

        # for every selection, get and merge upstream
        region = ee.FeatureCollection(
            selection_basins.map(get_upstream_catchments(catchment_level))) \
            .flatten().distinct('HYBAS_ID').geometry()

        region = region.bounds()

    if region_filter == 'catchments-intersection':
        region = basins[catchment_level].filterBounds(region)

        region = region.geometry().bounds()

    raster_assets = {
        'dem': 'USGS/SRTMGL1_003',
        'hand': 'users/gena/global-hand/hand-100',
        'FirstZoneCapacity': 'users/gena/HydroEngine/static/FirstZoneCapacity',
        'FirstZoneKsatVer': 'users/gena/HydroEngine/static/FirstZoneKsatVer',
        'FirstZoneMinCapacity': 'users/gena/HydroEngine/static/FirstZoneMinCapacity',
        'InfiltCapSoil': 'users/gena/HydroEngine/static/InfiltCapSoil',
        'M': 'users/gena/HydroEngine/static/M',
        'PathFrac': 'users/gena/HydroEngine/static/PathFrac',
        'WaterFrac': 'users/gena/HydroEngine/static/WaterFrac',
        'thetaS': 'users/gena/HydroEngine/static/thetaS',
        'soil_type': 'users/gena/HydroEngine/static/wflow_soil',
        'landuse': 'users/gena/HydroEngine/static/wflow_landuse',
        'LAI01': 'users/gena/HydroEngine/static/LAI/LAI00000-001',
        'LAI02': 'users/gena/HydroEngine/static/LAI/LAI00000-002',
        'LAI03': 'users/gena/HydroEngine/static/LAI/LAI00000-003',
        'LAI04': 'users/gena/HydroEngine/static/LAI/LAI00000-004',
        'LAI05': 'users/gena/HydroEngine/static/LAI/LAI00000-005',
        'LAI06': 'users/gena/HydroEngine/static/LAI/LAI00000-006',
        'LAI07': 'users/gena/HydroEngine/static/LAI/LAI00000-007',
        'LAI08': 'users/gena/HydroEngine/static/LAI/LAI00000-008',
        'LAI09': 'users/gena/HydroEngine/static/LAI/LAI00000-009',
        'LAI10': 'users/gena/HydroEngine/static/LAI/LAI00000-010',
        'LAI11': 'users/gena/HydroEngine/static/LAI/LAI00000-011',
        'LAI12': 'users/gena/HydroEngine/static/LAI/LAI00000-012',
        'thickness-NASA': 'users/huite/GlobalThicknessNASA/average_soil_and_sedimentary-deposit_thickness',
        'thickness-SoilGrids': 'users/huite/SoilGrids/AbsoluteDepthToBedrock__cm',
    }

    if variable == 'hand':
        image = ee.ImageCollection(raster_assets[variable]).mosaic()
    else:
        image = ee.Image(raster_assets[variable])

    image = image.clip(region)

    # create response
    url = image.getDownloadURL({
        'name': 'variable',
        'format': 'tif',
        'crs': crs,
        'scale': cell_size,
        'region': json.dumps(region.bounds(cell_size).getInfo())
    })

    data = {'url': url}
    return Response(json.dumps(data), status=200, mimetype='application/json')


@app.route('/get_liwo_scenarios', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def get_liwo_scenarios():
    r = request.get_json()

    # Currently 'liwo' only option
    variable = 'liwo'
    # name of breach location as string
    liwo_ids = r['liwo_ids']
    # band name as string
    band = r['band']

    raster_assets = {
        'liwo': 'users/rogersckw9/liwo/liwo-scenarios-03-2019'
    }
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
    assert band in reducers
    assert band in bands
    reducer = reducers[band]

    styles = {
        'waterdepth': {
            'sld_style': '\
                <RasterSymbolizer>\
                    <ColorMap type="intervals">\
                        <ColorMapEntry color="#FFFFFF" opacity="0.01" quantity="0.01999"/>\
                        <ColorMapEntry color="#CEFEFE" opacity="1.0" quantity="0.5" label="&lt; 0.5"/>\
                        <ColorMapEntry color="#94bff7" opacity="1.0" quantity="1" label="0.5 - 1.0"/>\
                        <ColorMapEntry color="#278ef4" opacity="1.0" quantity="1.5" label="1.0 - 1.5"/>\
                        <ColorMapEntry color="#0000cc" opacity="1.0" quantity="2.0" label="1.5 - 2.0"/>\
                        <ColorMapEntry color="#4A0177" opacity="1.0" quantity="5" label="2.0 - 5.0"/>\
                        <ColorMapEntry color="#73004c" opacity="1.0" quantity="9999" label="&gt; 5.0"/>\
                    </ColorMap>\
                </RasterSymbolizer>'
        },
        'velocity': {
            'sld_style': '\
                <RasterSymbolizer>\
                    <ColorMap type="intervals">\
                        <ColorMapEntry color="#FFFFFF" opacity="0.01" quantity="0.01"/>\
                        <ColorMapEntry color="#FAD7FE" opacity="1.0" quantity="0.5" label="&lt; 0.5"/>\
                        <ColorMapEntry color="#E95CF5" opacity="1.0" quantity="1" label="0.5 - 1.0"/>\
                        <ColorMapEntry color="#CB00DB" opacity="1.0" quantity="2" label="1.0 - 2.0"/>\
                        <ColorMapEntry color="#8100B1" opacity="1.0" quantity="4" label="2.0 - 4.0"/>\
                        <ColorMapEntry color="#8100D2" opacity="1.0" quantity="1000" label="&gt; 4.0"/>\
                    </ColorMap>\
                </RasterSymbolizer>'
        },
        'riserate': {
            'sld_style': '\
                <RasterSymbolizer>\
                    <ColorMap type="intervals">\
                        <ColorMapEntry color="#FFFFFF" opacity="0.01" quantity="0.01"/>\
                        <ColorMapEntry color="#FFF5E6" opacity="1.0" quantity="0.25" label="&lt; 0.25"/>\
                        <ColorMapEntry color="#FFD2A8" opacity="1.0" quantity="0.5" label="0.25 - 0.5"/>\
                        <ColorMapEntry color="#FFAD66" opacity="1.0" quantity="1" label="0.5 - 1.0"/>\
                        <ColorMapEntry color="#EB7515" opacity="1.0" quantity="2" label="1.0 - 2.0"/>\
                        <ColorMapEntry color="#B05500" opacity="1.0" quantity="1000000" label="&gt; 2.0"/>\
                    </ColorMap>\
                </RasterSymbolizer>'
        },
        'damage': {
            'sld_style': '\
                <RasterSymbolizer>\
                    <ColorMap type="intervals">\
                        <ColorMapEntry color="#FFFFFF" opacity="0.01" quantity="0.01"/>\
                        <ColorMapEntry color="#499b1b" opacity="1.0" quantity="10000" label="&lt; 10.000"/>\
                        <ColorMapEntry color="#61f033" opacity="1.0" quantity="100000" label="10.000 - 100.000"/>\
                        <ColorMapEntry color="#ffbb33" opacity="1.0" quantity="1000000" label="100.000 - 1.000.000"/>\
                        <ColorMapEntry color="#ff3333" opacity="1.0" quantity="5000000" label="1.000.000 - 5.000.000"/>\
                        <ColorMapEntry color="#8f3333" opacity="1.0" quantity="1000000000000000" label="&gt; 5.000.000"/>\
                    </ColorMap>\
                </RasterSymbolizer>'
        },
        'fatalities': {
            'sld_style': '\
                <RasterSymbolizer>\
                    <ColorMap type="intervals">\
                        <ColorMapEntry color="#FFFFFF" opacity="0.01" quantity="0.0001"/>\
                        <ColorMapEntry color="#499b1b" opacity="1.0" quantity="0.1" label="&lt; 0.1"/>\
                        <ColorMapEntry color="#61f033" opacity="1.0" quantity="0.3" label="0.1 - 0.3"/>\
                        <ColorMapEntry color="#ffbb33" opacity="1.0" quantity="1" label="0.3 - 1"/>\
                        <ColorMapEntry color="#ff3333" opacity="1.0" quantity="3" label="1 - 3"/>\
                        <ColorMapEntry color="#8f3333" opacity="1.0" quantity="10000" label="&gt; 3"/>\
                    </ColorMap>\
                </RasterSymbolizer>'
        }
    }

    # Filter based on breach location
    collection = ee.ImageCollection(raster_assets[variable])

    # TODO: how to make this generic, consider GraphQL
    collection = collection.filter(
        ee.Filter.inList('LIWO_ID', liwo_ids)
    )

    collection = collection.map(
        lambda im: im.set('bandNames', im.bandNames())
    )

    n_selected = collection.size().getInfo()

    if band != 'waterdepth':
        collection = collection.filterMetadata('bandNames', 'equals', ['b1', 'b2', 'b3', 'b4', 'b5'])

    n_filtered = collection.size().getInfo()

    if n_selected != n_filtered:
        logging.warning('missing images, selected %s, filtered %s', n_selected, n_filtered)

    # Filter based on band name (characteristic to display)
    collection = collection.select(bands[band])
    n_images = collection.size().getInfo()
    msg = 'No images available for breach locations: %s' % (liwo_ids,)
    logger.debug(msg)

    if not n_images:
        raise error_handler.InvalidUsage(msg)

    # get max image
    reduce_func = getattr(ee.Reducer, reducer)()
    image = ee.Image(collection.reduce(reduce_func))
    # clip image to region and show only values greater than 0 (no-data value given in images) .clip(region)
    image = image.mask(image.gt(0))

    def generate_image_info(im, params):
        """generate url and tokens for image"""
        im = ee.Image(im)

        # some images are scaled to a factor of 10.
        if params.get('scale') == 'log':
            im = im.log10()

        im = im.sldStyle(params.get('sld_style'))

        m = im.getMapId()

        mapid = m.get('mapid')
        token = m.get('token')

        url = 'https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}'.format(
            mapid=mapid,
            token=token
        )

        result = {
            'mapid': mapid,
            'token': token,
            'url': url
        }
        return result

    def export_image_response(image, region, info):
        """create export response for image"""
        url = image.getDownloadURL({
            'name': 'export',
            'format': 'tif',
            'crs': info['crs'],
            'scale': info['scale'],
            'region': json.dumps(region.bounds(info['scale']).getInfo())
        })
        result = {'export_url': url}
        return result

    # TODO: generate visualization params for map ids
    params = styles[band]

    info = generate_image_info(image, params)
    info['variable'] = variable
    info['liwo_ids'] = liwo_ids
    info['band'] = band

    # # Following needed for export:
    # # Specify region over which to compute
    # export  is True or None/False
    if r.get('export'):
        region = ee.Geometry(r['region'])
        # scale of pixels for export, in meters
        info['scale'] = float(r['scale'])
        # coordinate system for export projection
        info['crs'] = r['crs']
        extra_info = export_image_response(image, region, info)
        info.update(extra_info)

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@app.route('/get_glossis_data', methods=['POST'])
@flask_cors.cross_origin()
def get_glossis_data():
    """
    Get GLOSSIS data. Either currents, wind, or waterlevel dataset must be provided.
    If waterlevel dataset is requested, must specify if band water_level_surge, water_level,
    or astronomical_tide is requested
    :return:
    """
    data_params = DATASETS_VIS['glossis']

    r = request.get_json()
    dataset = r['dataset']

    assert (dataset in data_params), '{} not in assets. '.format(dataset)
    data_params = data_params[dataset]
    # Get collection based on dataset requested
    collection = ee.ImageCollection(data_params['source'])

    if 'date' in r:
        start = ee.Date(r['date'])
        collection = collection.filterDate(start)
        # check that at least one image returned. If not, return error
        n_images = collection.size().getInfo()
        if not n_images:
            msg = 'No images available for time: %s' % (r['date'])
            logger.debug(msg)
            raise error_handler.InvalidUsage(msg)

    image = ee.Image(collection.sort('system:time_start', False).first())
    image_date = image.date().format().getInfo()
    image_id = image.id().getInfo()

    # Generate image on dataset requested (characteristic to display)
    band = r.get('band', list(data_params['bandNames'].keys())[0])
    assert band in data_params['bandNames']


    if dataset in ['wind', 'currents']:
        function = r.get('function', 'magnitude')
        assert function in data_params['function']

        image = apply_image_operation(image, function, data_params)

        vis_params = {
            'min': data_params['min'][function],
            'max': data_params['max'][function],
            'palette': data_params['palette'][function],
            'function': function
        }
    else:
        image = image.select(data_params['bandNames'][band])
        vis_params = {
            'min': data_params['min'][band],
            'max': data_params['max'][band],
            'palette': data_params['palette'][band]
        }

    if 'min' in r:
        vis_params['min'] = r['min']

    if 'max' in r:
        vis_params['max'] = r['max']

    if 'palette' in r:
        vis_params['palette'] = r['palette']

    info = generate_image_info(image, vis_params)
    info['dataset'] = dataset
    info['date'] = image_date
    info['imageId'] = data_params['source'] + '/' + image_id

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@app.route('/get_gloffis_data', methods=['POST'])
@flask_cors.cross_origin()
def get_gloffis_data():
    """
    Get GLOFFIS data. dataset must be provided.
    :return:
    """
    data_params = DATASETS_VIS['gloffis']

    r = request.get_json()

    dataset = r['dataset']
    assert (dataset in data_params), '{} not in assets. '.format(dataset)
    data_params = data_params[dataset]

    band = r['band']
    assert band in data_params['bandNames'].keys(), '{} not in bands. '.format(band)

    # Get collection based on dataset requested
    collection = ee.ImageCollection(data_params['source'])

    if 'date' in r:
        start = ee.Date(r['date'])
        collection = collection.filterDate(start)
        # check that at least one image returned. If not, return error
        n_images = collection.size().getInfo()
        if not n_images:
            msg = 'No images available for time: %s' % (r['date'])
            logger.debug(msg)
            raise error_handler.InvalidUsage(msg)

    image = ee.Image(collection.sort('system:time_start', False).first())
    image_date = collection.sort('system:time_start', False).first().date().format().getInfo()
    image_id = image.id().getInfo()
    image = image.select(band)

    vis_params = {
        'min': data_params['min'][band],
        'max': data_params['max'][band],
        'palette': data_params['palette'][band]
    }

    if dataset == 'hydro':
        image = image.mask(image.gte(0))

    if band == 'discharge_routed_simulated':
        image = apply_image_operation(image, "log")
        vis_params['function'] = data_params['function'][band]

    if 'min' in r:
        vis_params['min'] = r['min']

    if 'max' in r:
        vis_params['max'] = r['max']

    if 'palette' in r:
        vis_params['palette'] = r['palette']

    info = generate_image_info(image, vis_params)
    info['dataset'] = dataset
    info['band'] = band
    info['date'] = image_date
    info['imageId'] = data_params['source'] + '/' + image_id

    if band == 'discharge_routed_simulated':
        info['min'] = 10**vis_params['min']
        info['max'] = 10**vis_params['max']

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@app.route('/get_metocean_data', methods=['POST'])
@flask_cors.cross_origin()
def get_metocean_data():
    """
    Get metocean data. dataset must be provided.
    :return:
    """
    data_params = DATASETS_VIS['metocean']

    r = request.get_json()

    dataset = r['dataset']
    assert (dataset in data_params), '{} not in assets. '.format(dataset)
    data_params = data_params[dataset]

    band = list(data_params['bandNames'].keys())[0]
    if 'band' in r:
        band = r['band']
        assert band in data_params['bandNames'], '{} not in bands. '.format(band)

    # Get collection based on dataset requested
    image = ee.Image(data_params['source'])
    image = image.select(data_params['bandNames'][band])

    vis_params = {
        'min': data_params['min'][band],
        'max': data_params['max'][band],
        'palette': data_params['palette'][band]
    }

    if 'min' in r:
        vis_params['min'] = r['min']

    if 'max' in r:
        vis_params['max'] = r['max']

    if 'palette' in r:
        vis_params['palette'] = r['palette']

    info = generate_image_info(image, vis_params)
    info['dataset'] = dataset
    info['band'] = band
    info['imageId'] = data_params['source']

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@app.route('/get_gebco_data', methods=['POST'])
@flask_cors.cross_origin()
def get_gebco_data():
    r = request.get_json()

    data_params = DATASETS_VIS['bathymetry']['gebco']
    image = ee.Image(data_params['source'])
    band = 'elevation'

    gebco = image.select(data_params['bandNames'][band])

    # Angle for hillshade (keep at 315 for good perception)
    azimuth = 315
    # Lower is longer shadows
    zenith = 30

    bathy_only = data_params.get('bathy_only', False)

    height_multiplier = 30
    # Weight between image and  hillshade (1=equal)
    weight = 0.3
    # make darker (<1), lighter (>1)
    val_multiply = 0.9
    # make  desaturated (<1) or more saturated (>1)
    sat_multiply = 0.8

    # palettes
    # visualization params
    topo_rgb = gebco.mask(gebco.gt(0)).visualize(**data_params['topo_vis_params'])
    bathy_rgb = gebco.mask(gebco.lte(0)).visualize(**data_params['bathy_vis_params'])
    image_rgb = topo_rgb.blend(bathy_rgb)

    if (bathy_only):
        # overwrite with masked version
        image_rgb = bathy_rgb.mask(gebco.multiply(ee.Image(-1)).unitScale(-1, 10).clamp(0, 1))


    # TODO:  see how this still fits in the hillshade function
    hsv = image_rgb.unitScale(0, 255).rgbToHsv()

    z = gebco.multiply(ee.Image.constant(height_multiplier))

    def radians(image):
        return ee.Image(image).toFloat().multiply(3.1415927).divide(180)


    # Compute terrain properties
    terrain = ee.Algorithms.Terrain(z)
    slope = radians(terrain.select(['slope']))
    aspect = radians(terrain.select(['aspect'])).resample('bicubic')
    azimuth = radians(ee.Image.constant(azimuth))
    zenith = radians(ee.Image.constant(zenith))
    # hillshade
    hs = (
        azimuth
        .subtract(aspect)
        .cos()
        .multiply(slope.sin())
        .multiply(zenith.sin())
        .add(
            zenith
            .cos()
            .multiply(
                slope.cos()
            )
        )
        .resample('bicubic')
    )

    # weighted average of hillshade and value
    intensity = hs.multiply(hsv.select('value'))



    hue = hsv.select('hue')

    # desaturate a bit
    sat = hsv.select('saturation').multiply(sat_multiply)
    # make a bit darker
    val = intensity.multiply(val_multiply)

    hillshaded = ee.Image.cat(hue, sat, val).hsvToRgb()

    info = {}
    info['dataset'] = 'gebco'
    info['band'] = band

    m = hillshaded.getMapId()
    mapid = m.get('mapid')
    token = m.get('token')

    url = 'https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}'.format(
        mapid=mapid,
        token=token
    )

    linear_gradient = []
    palette = data_params['bathy_vis_params']['palette'] + data_params['topo_vis_params']['palette']
    n_colors = len(palette)
    offsets = np.linspace(0, 100, num=n_colors)
    for color, offset in zip(palette, offsets):
        linear_gradient.append({
            'offset': '{:.3f}%'.format(offset),
            'opacity': 100,
            'color': color
        })

    info.update({
        'mapid': mapid,
        'token': token,
        'url': url,
        'linearGradient': linear_gradient,
        'imageId': data_params['source']
    })


    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


def generate_image_info(im, params):
    """"generate url and tokens for image"""
    image = ee.Image(im)

    if 'sld_style' in params:
        m = image.sldStyle(params.get('sld_style'))
        del params['sld_style']
    elif 'palette' in params:
        m = image.visualize(**{
            'min': params.get('min'),
            'max': params.get('max'),
            'palette': params.get('palette')
        })
    else:
        m = image

    if 'hillshade' in params:
        # also pass along hillshade arguments
        hillshade_args = params.get('hillshade_args',  {})
        m = hillshade(m, image, False, **hillshade_args)

    m = m.getMapId()
    mapid = m.get('mapid')
    token = m.get('token')

    url = 'https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}'.format(
        mapid=mapid,
        token=token
    )

    linear_gradient = []
    if 'palette' in params:
        n_colors = len(params.get('palette'))
        palette = params.get('palette')
        offsets = np.linspace(0, 100, num=n_colors)
        if 'function' in params:
            if params['function'] == 'log':
                # if log scaling applied, apply log scale to linear gradient palette offsets
                offsets = np.logspace(0.0, 2.0, num=n_colors, base=10.0)
                offsets[0] = 0.0
        for color, offset in zip(palette, offsets):
            linear_gradient.append({
                'offset': '{:.3f}%'.format(offset),
                'opacity': 100,
                'color': color
            })

    params.update({
        'mapid': mapid,
        'token': token,
        'url': url,
        'linearGradient': linear_gradient})
    return params

def apply_image_operation(image, operation, data_params=None):
    """
    Apply an operation to an image, based on specified operation and data parameters
    :param image:
    :param operation: String, type of operation
    :param data_params: coming from data_visualization_parameters.json
    :return:
    """
    if operation == "log":
        image = image.log10().rename('log')
    if operation == "magnitude":
        image = image.pow(2).reduce(ee.Reducer.sum()).sqrt().rename('magnitude')
    if operation == "flowmap":
        image.unitScale(data_params['min'][operation], data_params['max'][operation]).unmask(-9999)
        data_mask = image.eq(-9999).select(data_params['bandNames'][band])
        image = image.clamp(0, 1).addBands(data_mask).rename('flowmap')

    return image

@app.route('/get_feature_info', methods=['POST'])
@flask_cors.cross_origin()
def get_feature_info():
    """
    Get image value at point
    :return:
    """
    r = request.get_json()
    image_id = r['imageId']
    bbox = r['bbox']
    band = r.get('band', None)
    function = r.get('function', None)
    info_format = r.get('info_format', 'JSON')

    image = ee.Image(image_id)
    if band:
        image_location_parameters = image_id.split('/')
        if len(image_location_parameters) == 5:
            _gee_folder_type, _project, data_collection, dataset, imageName = image_location_parameters
        # For metocean data, no image collections.
        if len(image_location_parameters) == 4:
            _gee_folder_type, _project, data_collection, dataset = image_location_parameters

        band_name = DATASETS_VIS[data_collection][dataset]['bandNames'][band]
        image = image.select(band_name)

    image = apply_image_operation(image, function)
    image = image.rename('value')

    value = (
        image.sample(**{
            'region': ee.Geometry(bbox),
            'geometries': True
        })
        .first()
        .getInfo()
    )

    # if no data at point, value will be None.
    if not value:
        # return Feature with value None (standard return format from GEE)
        value = {
          "geometry": bbox,
          "id": "0",
          "properties": {
            "value": None
          },
          "type": "Feature"
        }

    if info_format == 'JSON':
        value = value['properties']

    return Response(
        json.dumps(value),
        status=200,
        mimetype='application/json'
    )

@app.route('/')
def root():
    return 'Welcome to Hydro Earth Engine. Currently, only RESTful API is supported. Visit <a href="http://github.com/deltares/hydro-engine">http://github.com/deltares/hydro-engine</a> for more information ...'


@app.errorhandler(500)
def server_error(e):
    logger.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)
    # [END app]
