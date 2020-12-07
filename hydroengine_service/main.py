#!/usr/bin/env python
# coding: utf-8

# TODO: move out all non-flask code to a separate file / library

import base64
import json
import logging
import os

import ee
import numpy as np
import geojson
import flask_cors
from flask import Flask
from flask import request, Response
from flask import Blueprint

from hydroengine_service import config
from hydroengine_service import error_handler

from hydroengine_service import liwo_blueprints
from hydroengine_service import dgds_blueprints

from hydroengine_service import river_functions
from hydroengine_service import dgds_functions

from hydroengine_service import liwo_functions
from hydroengine_service import digitwin_blueprints

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)

logFormatter = logging.Formatter(
    "%(asctime)s [%(threadName)-12.12s] [%(levelname)-7.7s]  %(message)s")

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)

logger.addHandler(consoleHandler)

app = Flask(__name__)

app.register_blueprint(error_handler.error_handler)

v1 = Blueprint("version1", "version1")
v2 = Blueprint('version2', "version2")



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
    'jarkus': ee.ImageCollection('projects/deltares-rws/eo-bathymetry/jarkus'),
    'ahn': ee.ImageCollection('users/rogersckw9/eo-bathymetry/ahn')
}

# graph index
index = ee.FeatureCollection('users/gena/HydroEngine/hybas_lev06_v1c_index')

monthly_water = ee.ImageCollection("JRC/GSW1_2/MonthlyHistory")


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


@v1.route('/get_image_urls', methods=['GET', 'POST'])
@flask_cors.cross_origin()
def api_get_image_urls():
    logger.warning(
        'get_image_urls is no longer supported, please update to get_bathymetry'
    )
    r = request.get_json()
    dataset = r['dataset']  # bathymetry_jetski | bathymetry_vaklodingen | dem_srtm | ...
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
        url = 'https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}' \
            .format(
            mapid=mapid
        )

        begin = image.get('begin').getInfo()

        end = image.get('end').getInfo()

        return {'mapid': mapid, 'url': url, 'begin': begin,
                'end': end}

    images = ee.List.sequence(0, t_count).map(generate_average_image)

    infos = [generate_image_info(images.get(i)) for i in
             range(images.size().getInfo())]

    resp = Response(json.dumps(infos), status=200, mimetype='application/json')

    return resp


@v1.route('/get_sea_surface_height_time_series', methods=['POST'])
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


@v1.route('/get_sea_surface_height_trend_image', methods=['GET', 'POST'])
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
    url = 'https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}' \
        .format(
        mapid=mapid
    )

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


@v1.route('/get_bathymetry', methods=['GET', 'POST'])
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
        url = 'https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}' \
            .format(
            mapid=mapid
        )

        result = {
            'mapid': mapid,
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


@v1.route('/get_raster_profile', methods=['GET', 'POST'])
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


@v1.route('/get_water_mask_raw', methods=['POST'])
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


@v1.route('/get_water_mask', methods=['POST', 'GET'])
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

    if crs is not None and crs != 'EPSG:4326':
        water_mask_vector = water_mask_vector.map(transform_feature(crs, scale))

    # create response
    if use_url:
        url = water_mask_vector.getDownloadURL('json')
        data = {'url': url}
    else:
        data = water_mask_vector.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@v1.route('/get_water_network', methods=['POST'])
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
    output = river_functions.generate_skeleton_from_voronoi(scale, water_vector)
    centerline = output["centerline"]

    centerline = centerline.map(
        lambda line: line.set('length', line.length(scale / 10)))

    if crs is not None and crs != 'EPSG:4326':
        centerline = centerline.map(transform_feature(crs, scale))

    # create response
    data = centerline.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@v1.route('/get_water_network_properties', methods=['POST'])
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
    output = river_functions.generate_skeleton_from_voronoi(scale, water_vector)
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

    if crs is not None and crs != 'EPSG:4326':
        points = points.map(transform_feature(crs, scale))

    # create response
    data = points.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@v1.route('/get_catchments', methods=['GET', 'POST'])
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


@v1.route('/get_rivers', methods=['GET', 'POST'])
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


@v1.route('/get_lakes', methods=['GET', 'POST'])
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

    #

    # create response
    data = selected_lakes.getInfo()

    return Response(json.dumps(data), status=200, mimetype='application/json')


@v1.route('/get_lake_by_id', methods=['GET', 'POST'])
def get_lake_by_id():
    lake_id = int(request.json['lake_id'])

    lake = ee.Feature(
        ee.FeatureCollection(
            lakes.filter(
                ee.Filter.eq('Hylak_id', lake_id)
            )
        ).first()
    )
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


@v1.route('/get_lake_time_series', methods=['GET', 'POST'])
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


@v1.route('/get_feature_collection', methods=['GET', 'POST'])
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


@v1.route('/get_raster', methods=['GET', 'POST'])
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
        'crs': crs,
        'scale': cell_size,
        'region': json.dumps(region.bounds(cell_size).getInfo())
    })

    data = {'url': url}
    return Response(json.dumps(data), status=200, mimetype='application/json')





@v1.route('/get_feature_info', methods=['POST'])
@flask_cors.cross_origin()
def get_feature_info():
    """
    Get image value at point
    :return:
    """
    r = request.get_json()
    image_id = r['imageId']
    bbox = r['bbox']
    datasets = r.get('datasets', None)
    band = r.get('band', None)
    function = r.get('function', None)
    info_format = r.get('info_format', 'JSON')
    if function == 'mosaic_elevation_datasets':
        if not datasets:
            msg = f'datsets list expected for function {function}'
            raise error_handler.InvalidUsage(msg)
        image = ee.Image(dgds_functions.mosaic_elevation_datasets(datasets).select('elevation'))
    else:
        image = ee.Image(image_id)
        image_location_parameters = image_id.split('/')
        source = ('/').join(image_location_parameters[:-1])

        data_params = dgds_functions.get_dgds_source_vis_params(source, image_id)

        if band:
            band_name = data_params['bandNames'][band]
            image = image.select(band_name)
        if function:
            assert (function in data_params.get('function', None)) or \
                   (function == data_params['function'].get(band, None)), \
                f'{function} not an option.'

        image = dgds_functions.apply_image_operation(image, function, data_params, band)

    image = image.rename('value')
    # TODO: get scale of image, or load default scale from parameters
    value = (
        image.sample(**{
            'region': ee.Geometry(bbox),
            'geometries': True,
            'scale': 10
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
    else:
        value['properties']['value'] = round(value['properties']['value'], 2)

    if info_format == 'JSON':
        value = value['properties']

    return Response(
        json.dumps(value),
        status=200,
        mimetype='application/json'
    )


@v1.route('/get_image_collection_info', methods=['POST'])
@flask_cors.cross_origin()
def get_image_collection_info():
    r = request.get_json()
    source = r['source']
    start_date = r.get('startDate', None)
    end_date = r.get('endDate', None)
    image_num_limit = r.get('limit', None)

    info = dgds_functions.get_image_collection_info(source, start_date, end_date, image_num_limit)
    if not info:
        raise error_handler.InvalidUsage('No images returned.')

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@v1.route('/get_wms_url', methods=['POST'])
@flask_cors.cross_origin()
def get_wms_url():
    # TODO: check how many bands, if band is not specified return warning.
    r = request.get_json()
    image_id = r['imageId']
    band = r.get('band', None)
    datasets = r.get('datasets', None)
    function = r.get('function', None)
    min = r.get('min', None)
    max = r.get('max', None)
    palette = r.get('palette', None)

    info = dgds_functions.get_wms_url(image_id, 'Image', band, datasets, function, min, max, palette)

    return Response(
        json.dumps(info),
        status=200,
        mimetype='application/json'
    )


@v1.route('/')
def root():
    return 'Welcome to Hydro Earth Engine. Currently, only RESTful API is supported. Visit <a href="http://github.com/deltares/hydro-engine">http://github.com/deltares/hydro-engine</a> for more information ...'


@app.errorhandler(500)
def server_error(e):
    logger.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500

# Note, this should be here. Don't move this above.
app.register_blueprint(v1, url_prefix="/v1")
app.register_blueprint(v2, url_prefix="/v2")

app.register_blueprint(liwo_blueprints.v1, url_prefix="/v1")
app.register_blueprint(liwo_blueprints.v2, url_prefix="/v2")

app.register_blueprint(dgds_blueprints.v1, url_prefix="/v1")
app.register_blueprint(dgds_blueprints.v2, url_prefix="/v2")

app.register_blueprint(digitwin_blueprints.v1, url_prefix="/v1")
app.register_blueprint(digitwin_blueprints.v2, url_prefix="/v2")

# use version 1
app.register_blueprint(v1, url_prefix="/")
app.register_blueprint(liwo_blueprints.v1, url_prefix="/")
app.register_blueprint(dgds_blueprints.v1, url_prefix="/")
app.register_blueprint(digitwin_blueprints.v1, url_prefix="/")


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)
    # [END app]
