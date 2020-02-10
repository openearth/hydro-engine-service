import ee
import json
import logging
import numpy as np
import os

from hydroengine_service import config
from hydroengine_service import error_handler
from hydroengine_service import dgds_functions

EE_CREDENTIALS = ee.ServiceAccountCredentials(config.EE_ACCOUNT,
                                              config.EE_PRIVATE_KEY_FILE)

ee.Initialize(EE_CREDENTIALS)

logger = logging.getLogger(__name__)

def get_liwo_styling(band):
    style = {
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
    assert band in style
    return style[band]

def band_names_v2_to_v1(band):
    band_names = {
        "waterdiepte": "waterdepth",
        "stroomsnelheid": "velocity",
        "stijgsnelheid": "riserate",
        "schade": "damage",
        "slachtoffers": "fatalities",
        "getroffenen": "",
        "aankomsttijd": ""
    }
    assert band in band_names
    return band_names[band]

def filter_liwo_collection_v1(collection_path, id_key, liwo_ids, band, reducer):
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


def filter_liwo_collection(collection_path, id_key, scenario_ids, band, reducer):
    # Filter based on breach location
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
        logging.info("imageName, {}, missing {} scenarios for band {}".format(dst, len(scenario_ids)-n_selected, band))

    # get reducer image
    reduce_func = getattr(ee.Reducer, reducer)()
    if reducer == 'max':
        image = ee.Image(scenarios.reduce(reduce_func))
        # clip image to region and show only values greater than 0 (no-data value given in images) .clip(region)
        image = image.mask(image.gt(0))
    if reducer == 'min':
        scenarios = scenarios.map(lambda i: i.mask(i.gt(0)))
        image = ee.Image(scenarios.reduce(reduce_func))
    else:
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
