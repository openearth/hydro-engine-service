import ee
import json
import logging
import numpy as np
import os

from hydroengine_service import config
from hydroengine_service import dgds_functions
from hydroengine_service import error_handler

EE_CREDENTIALS = ee.ServiceAccountCredentials(config.EE_ACCOUNT,
                                              config.EE_PRIVATE_KEY_FILE)

ee.Initialize(EE_CREDENTIALS)

# visualization files for datasets
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATASET_DIR = os.path.join(APP_DIR, 'datasets')

logger = logging.getLogger(__name__)


def get_liwo_styling(band):
    style = {
        'waterdepth': {
            'sld_style': 'waterdepth_sld_style.txt'
        },
        'velocity': {
            'sld_style': 'velocity_sld_style.txt'
        },
        'riserate': {
            'sld_style': 'riserate_sld_style.txt'
        },
        'damage': {
            'sld_style': 'damage_sld_style.txt'
        },
        'fatalities': {
            'sld_style': 'fatalities_sld_style.txt'
        },
        'affected': {
            'sld_style': 'affected_sld_style.txt'
        },
        'arrivaltime': {
            'sld_style': 'arrivaltime_sld_style.txt'
        }
    }
    assert band in style
    style_dict = {}
    with open(os.path.join(DATASET_DIR, style[band]['sld_style'])) as f:
        style_string = f.read().replace('\n', '')

    style_dict['sld_style'] = style_string
    return style_dict


def filter_liwo_collection_v1(collection_path, id_key, liwo_ids, band, reducer):
    """
    Create combined max image from collection. Version 1 based on unnamed single
    and multi band images.
    :param collection_path: Path to Earth Engine Image Collection
    :param id_key: Metadata key name for unique ids
    :param scenario_ids: List of scenario ids to combine
    :param band: band of image to select
    :param reducer: reducer operation by which to combine images
    :return: combined image
    """
    # Filter based on breach location
    collection = ee.ImageCollection(collection_path)

    # TODO: how to make this generic, consider GraphQL
    collection = collection.filter(
        ee.Filter.inList(id_key, liwo_ids)
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
    collection = collection.select(band)
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
    return image


def filter_liwo_collection_v2(collection_path, id_key, scenario_ids, band, reducer):
    """
    Create combined max image from collection. Version 2 based on named image bands
    :param collection_path: Path to Earth Engine Image Collection
    :param id_key: Metadata key name for unique ids
    :param scenario_ids: List of scenario ids to combine
    :param band: band of image to select
    :param reducer: reducer operation by which to combine images
    :return: combined image
    """
    # Filter based on scenario id, band
    scenarios = ee.ImageCollection(collection_path)
    scenarios = scenarios.filter(ee.Filter.inList(id_key, scenario_ids))
    scenarios = scenarios.filter(ee.Filter.listContains("system:band_names", band))
    scenarios = scenarios.select(band)
    n_selected = scenarios.size().getInfo()

    if n_selected == 0:
        msg = 'No images available for breach locations: %s' % (scenario_ids,)
        logger.debug(msg)
        raise error_handler.InvalidUsage(msg)
        # raise ValueError("No images with band {} in scenario_ids {}".format(band, scenario_ids))

    if len(scenario_ids) != n_selected:
        logging.info(
            "imageName, {}, missing {} scenarios for band {}".format(dst, len(scenario_ids) - n_selected, band))

    # get reducer image
    reduce_func = getattr(ee.Reducer, reducer)()
    scenarios = scenarios.map(lambda i: i.mask(i.gt(0)))
    image = ee.Image(scenarios.reduce(reduce_func))

    return image


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
