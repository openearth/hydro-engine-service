import ee
import json
import logging
import numpy as np
import os

from hydroengine_service import config
from hydroengine_service import error_handler

EE_CREDENTIALS = ee.ServiceAccountCredentials(config.EE_ACCOUNT,
                                              config.EE_PRIVATE_KEY_FILE)

ee.Initialize(EE_CREDENTIALS)

# visualization parameters for datasets
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATASET_DIR = os.path.join(APP_DIR, 'datasets')
with open(DATASET_DIR + '/dataset_visualization_parameters.json') as json_file:
    DATASETS_VIS = json.load(json_file)

logger = logging.getLogger(__name__)

def get_dgds_source_vis_params(source, image_id=None):
    """
    Check source and/or image_id has default visualization parameters defined
    :param source: String, source/location of Earth Engine Object
    :param image_id: String, Earth Engine Image id
    :return:
    """
    data_params = DATASETS_VIS.get(source, None)
    if image_id and not data_params:
        data_params = DATASETS_VIS.get(image_id, None)
    assert data_params, f'{source} not in assets.'
    return data_params


def get_dgds_data(source,
                  dataset=None,
                  image_id=None,
                  band=None,
                  function=None,
                  start_date=None,
                  end_date=None,
                  image_num_limit=None):
    """

    :param source: String, source/location of Earth Engine Object
    :param dataset: String, name of Earth Engine Object dataset
    :param image_id: String, Earth Engine Image id
    :param band: String, band name to select from image
    :param function: String, function to apply to image
    :param start_date: String, start date to filter collection on
    :param end_date: String, end date to filter collection on
    :param image_num_limit: String, limit of objects to return
    :return: Dictionary
    """
    # Get list of objects with imageId and date for collection
    data_params = get_dgds_source_vis_params(source, image_id)
    info = get_image_collection_info(source, start_date, end_date, image_num_limit)
    if not info:
        return

    # get most recent to return url
    returned_url_id = info[-1]["imageId"]
    if image_id:
        returned_url_id = image_id

    if data_params.get('function', None) and not function:
        function = data_params['function']
        if isinstance(function, list):
            function = function[0]
        else:
            function = function.get(band, None)

    image_info = _get_wms_url(returned_url_id, type=data_params['type'], band=band, function=function)
    image_info['dataset'] = dataset
    image_info['band'] = band
    image_info['imageTimeseries'] = info

    return image_info

def degree_to_radians_image(image):
    return ee.Image(image).toFloat().multiply(3.1415927).divide(180)


def visualize_gebco(source, band):
    """
    Specialized function to visualize GEBCO data
    :param source: String, Google Earth Engine image id
    :param band: String, band of image to visualize
    :return: Dictionary
    """
    data_params = DATASETS_VIS[source]
    image = ee.Image(source)

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

    # Compute terrain properties
    terrain = ee.Algorithms.Terrain(z)
    slope = degree_to_radians_image(terrain.select(['slope']))
    aspect = degree_to_radians_image(terrain.select(['aspect'])).resample('bicubic')
    azimuth = degree_to_radians_image(ee.Image.constant(azimuth))
    zenith = degree_to_radians_image(ee.Image.constant(zenith))
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
    linear_gradient = []
    palette = data_params['bathy_vis_params']['palette'] + data_params['topo_vis_params']['palette']

    # TODO: call to _generate_image_info

    m = hillshaded.getMapId()
    mapid = m.get('mapid')
    token = m.get('token')

    url = 'https://earthengine.googleapis.com/map/{mapid}/{{z}}/{{x}}/{{y}}?token={token}'.format(
        mapid=mapid,
        token=token
    )

    n_colors = len(palette)
    offsets = np.linspace(0, 100, num=n_colors)
    for color, offset in zip(palette, offsets):
        linear_gradient.append({
            'offset': '{:.3f}%'.format(offset),
            'opacity': 100,
            'color': color
        })

    info.update({
        'url': url,
        'linearGradient': linear_gradient,
        'min': data_params['bathy_vis_params']['min'],
        'max': data_params['topo_vis_params']['max'],
        'imageId': source
    })
    return info

def _generate_image_info(im, params):
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
        hillshade_args = params.get('hillshade_args', {})
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
        'url': url,
        'linearGradient': linear_gradient})
    return params

def apply_image_operation(image, operation, data_params=None, band=None):
    """
    Apply an operation to an image, based on specified operation and data parameters
    :param image: Google Earth Engine ee.Image() object
    :param operation: String, type of operation
    :param data_params: coming from data_visualization_parameters.json
    :return: Google Earth Engine ee.Image() object
    """
    if operation == "log":
        image = image.log10().rename('log')
    if operation == "magnitude":
        image = image.pow(2).reduce(ee.Reducer.sum()).sqrt().rename('magnitude')
    if operation == "flowmap":
        image.unitScale(data_params['min'][operation], data_params['max'][operation]).unmask(-9999)
        data_mask = image.eq(-9999).select(data_params['bandNames'][band])
        image = image.clamp(0, 1).addBands(data_mask)

    return image

def get_image_collection_info(source, start_date=None, end_date=None, image_num_limit=None):
    """
    Return list of objects with imageId and time for all images in an ImageCollection, or Image, source
    :param source: String,
    :param start_date: String, start date to filter collection on
    :param end_date: String, end date to filter collection on
    :param image_num_limit: limit of objects to return
    :return: List of dictionaries
    """
    data_params = get_dgds_source_vis_params(source)
    type = data_params.get('type', 'ImageCollection')

    # Get images based on source requested
    if type == 'ImageCollection':
        collection = ee.ImageCollection(source)
    elif type == 'Image':
        collection = ee.ImageCollection.fromImages([ee.Image(source)])
    else:
        msg = f'Object of type {type} not supported.'
        logger.debug(msg)
        return

    if end_date and not start_date:
        msg = f'If endDate provided, must also include startDate'
        logger.debug(msg)
        return

    if start_date:
        start = ee.Date(start_date)
        end = start.advance(1, 'day')
        if end_date:
            end = ee.Date(end_date)
        collection = collection.filterDate(start, end)

    n_images = collection.size().getInfo()
    if not n_images:
        msg = f'No images available between startDate={start_date} and endDate={end_date}'
        logger.debug(msg)
        return

    if image_num_limit:
        # get a limited number of latest images
        collection = collection.limit(image_num_limit, 'system:time_start', False)

    # Sort ascending
    collection = collection.sort('system:time_start', True)

    ids = ee.List(collection.aggregate_array('system:id')).getInfo()

    dates = ee.List(collection.aggregate_array('system:time_start'))
    if dates.length().getInfo() == 0:
        date_list = [None] * len(ids)
    else:
        date_list = dates.map(lambda i: ee.Date(i).format()).getInfo()

    response = []
    for id, date in zip(ids, date_list):
        object = {
            'imageId': id,
            'date': date
        }
        response.append(object)

    return response

def _get_wms_url(image_id, type='ImageCollection', band=None, function=None, min=None, max=None, palette=None):
    """
    Get WMS url from image_id
    :param image_id: String, Google Earth Engine image id
    :param type: String, type of source, either Image or ImageCollection
    :param band: String, name of band in the image
    :param function: String, function applied to the image
    :param min: Float, minimum value of visualization
    :param max: Float, maximum value of visualization
    :param palette: List, palette applied to image visualization, given as list of hex codes.
    :return: Dictionary, json object with image and wms info
    """
    # TODO: improve generalizing specialized styling for GEBCO
    if 'gebco'in image_id:
        info = visualize_gebco(image_id, band)
        return info

    image = ee.Image(image_id)
    # Get image date
    try:
        image_date = image.date().format().getInfo()
    except Exception as e:
        msg = f'Image {image_id} does not have an assigned date.'
        logger.debug(msg)
        image_date = None

    image_location_parameters = image_id.split('/')
    if type == 'ImageCollection':
        source = ('/').join(image_location_parameters[:-1])
    elif type == 'Image':
        source = image_id

    # Default visualization parameters
    band_name = None
    vis_params = {
        'min': 0,
        'max': 1,
        'palette': ['#000000', '#FFFFFF']
    }

    # see if we have default visualization parameters stored for this source
    source_params = DATASETS_VIS.get(source, None)

    if source_params:
        if band:
            band_name = source_params['bandNames'][band]
            vis_params['band'] = band
            image = image.select(band_name)
            vis_params['min'] = source_params['min'][band]
            vis_params['max'] = source_params['max'][band]
            vis_params['palette'] = source_params['palette'][band]
        if function:
            if isinstance(source_params['function'], list):
                assert function in source_params['function']
                vis_params['function'] = function
                # band = function
                image = apply_image_operation(image, function)
                vis_params['min'] = source_params['min'][function]
                vis_params['max'] = source_params['max'][function]
                vis_params['palette'] = source_params['palette'][function]
            else:
                assert function == source_params['function'][band]
                # function = source_params.get('function', None).get(band, None)
            # if band_function and not function:
            #     function = source_params['function'][band]
                # vis_params['function'] = source_params['function'][band]
            vis_params['function'] = function
            image = apply_image_operation(image, function)
    else:
        try:
            image = image.select(band)
        except Exception as e:
            msg = f'Error selecting band {band}, {e}'
            logger.debug(msg)
            return

    # Overwrite vis params if provided in request
    if min:
        vis_params['min'] = min
    if max:
        vis_params['max'] = max
    if palette:
        vis_params['palette'] = palette

    if source == 'projects/dgds-gee/gloffis/hydro':
        image = image.mask(image.gte(0))

    info = _generate_image_info(image, vis_params)
    info['source'] = source
    info['date'] = image_date
    info['imageId'] = image_id

    # Scale min and max if log function applied
    if function == 'log':
        info['min'] = 10 ** vis_params['min']
        info['max'] = 10 ** vis_params['max']

    return info
