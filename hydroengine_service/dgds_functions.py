import ee
import json
import logging
import numpy as np
import os
from copy import deepcopy

from hydroengine_service import config
from hydroengine_service import error_handler

EE_CREDENTIALS = ee.ServiceAccountCredentials(
    config.EE_ACCOUNT, config.EE_PRIVATE_KEY_FILE
)

ee.Initialize(EE_CREDENTIALS)

# visualization parameters for datasets
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATASET_DIR = os.path.join(APP_DIR, "datasets")
with open(DATASET_DIR + "/dataset_visualization_parameters.json") as json_file:
    DATASETS_VIS = json.load(json_file)

with open(DATASET_DIR + "/dataset_elevation_parameters.json") as json_file:
    ELEVATION_DATA = json.load(json_file)

logger = logging.getLogger(__name__)

LAND = ee.Image("users/gena/land_polygons_image")
LANDMASK = ee.Image(LAND.unmask(1, False).Not().resample("bicubic").focal_mode(2))


def validate_min_lt_max(min, max):
    try:
        min = float(min)
        max = float(max)
    except ValueError:
        raise error_handler.InvalidUsage("Specified min and max values must be numbers.")
    if not min < max:
        raise error_handler.InvalidUsage("Specified min must be less than max.")


def get_dgds_source_vis_params(source, image_id=None):
    """
    Check source and/or image_id has default visualization parameters defined
    :param source: String, source/location of Earth Engine Object
    :param image_id: String, Earth Engine Image id
    :return: Dictionary
    """
    data_params = DATASETS_VIS.get(source, None)
    if image_id and not data_params:
        data_params = DATASETS_VIS.get(image_id, None)
    assert data_params, f"{source} not in assets."
    return data_params


def get_dgds_data(
    source,
    dataset=None,
    image_id=None,
    band=None,
    function=None,
    start_date=None,
    end_date=None,
    image_num_limit=None,
    min=None,
    max=None,
):
    """

    :param source: String, source/location of Earth Engine Object
    :param dataset: String, name of Earth Engine Object dataset
    :param image_id: String, Earth Engine Image id
    :param band: String, band name to select from image
    :param function: String, function to apply to image
    :param start_date: String, start date to filter collection on
    :param end_date: String, end date to filter collection on
    :param image_num_limit: String, limit of objects to return
    :param min: Number, minimum value for image visualization
    :param max: Number, maximum value for image visualization
    :return: Dictionary
    """
    # Get list of objects with imageId and date for collection
    data_params = get_dgds_source_vis_params(source, image_id)
    info = {}
    if image_id:
        returned_url_id = image_id
    else:
        info = get_image_collection_info(source, start_date, end_date, image_num_limit)
        if not info:
            return
        # get most recent to return url
        returned_url_id = info[-1]["imageId"]

    if data_params.get("function", None) and not function:
        function = data_params["function"]
        if isinstance(function, list):
            function = function[0]
        else:
            function = function.get(band, None)

    image_info = _get_wms_url(
        image_id=returned_url_id,
        type=data_params["type"],
        band=band,
        function=function,
        min=min,
        max=max,
    )
    image_info["dataset"] = dataset
    image_info["band"] = band
    if info:
        image_info["imageTimeseries"] = info

    return image_info


def hillshade(
    image_rgb,
    image,
    azimuth=315,
    zenith=30,
    height_multiplier=30,
    weight=0.3,
    val_multiply=0.9,
    sat_multiply=0.8,
):
    """
    :param image_rgb: GEE image visualized in RGB to hillshade
    :param image: GEE image raw values, not visualized
    :param azimuth: Angle for hillshade.
    :param zenith: Zenith for hillshade. Lower is longer shadows
    :param height_multiplier:
    :param weight: Weight between image and  hillshade (1=equal)
    :param val_multiply: make darker (<1), lighter (>1)
    :param sat_multiply: make  desaturated (<1) or more saturated (>1)
    :return: Google Earth Engine ee.Image() object, hillshaded image
    """
    hsv = image_rgb.unitScale(0, 255).rgbToHsv()

    z = image.multiply(ee.Image.constant(height_multiplier))

    # Compute terrain properties
    terrain = ee.Algorithms.Terrain(z)
    slope = degree_to_radians_image(terrain.select(["slope"]))
    aspect = degree_to_radians_image(terrain.select(["aspect"])).resample("bicubic")
    azimuth = degree_to_radians_image(ee.Image.constant(azimuth))
    zenith = degree_to_radians_image(ee.Image.constant(zenith))
    # hillshade
    hs = (
        azimuth.subtract(aspect)
        .cos()
        .multiply(slope.sin())
        .multiply(zenith.sin())
        .add(zenith.cos().multiply(slope.cos()))
        .resample("bicubic")
    )

    # weighted average of hillshade and value
    intensity = hs.multiply(hsv.select("value"))

    hue = hsv.select("hue")

    # desaturate a bit
    sat = hsv.select("saturation").multiply(sat_multiply)
    # make a bit darker
    val = intensity.multiply(val_multiply)

    hillshaded = ee.Image.cat(hue, sat, val).hsvToRgb()
    return hillshaded


def visualize_elevation(
    image,
    land_mask=LANDMASK,
    data_params=None,
    bathy_only=False,
    hillshade_image=True,
    hillshade_args={},
):
    """
    :param image: Google Earth Engine image to visualize
    :param land_mask: Boolean Google Earth Engine image representing 1 for land mask
    :param bathy_only: Boolean for visualizing bathymetry only
    :param hillshade: Boolean for hillshading, default True
    :return: Google Earth Engine ee.Image() object, Hillshaded image
    """
    # validate min is less than max, otherwise raise error
    min = data_params["bathy_vis_params"]["min"]
    max = data_params["topo_vis_params"]["max"]
    if min and max is not None:
        validate_min_lt_max(min, max)

    topo_rgb = image.mask(land_mask).visualize(**data_params["topo_vis_params"])
    bathy_rgb = image.mask(land_mask.Not()).visualize(**data_params["bathy_vis_params"])
    image_rgb = topo_rgb.blend(bathy_rgb)

    if bathy_only:
        # overwrite with masked version
        image_rgb = bathy_rgb.mask(
            image.multiply(ee.Image(-1)).unitScale(-1, 10).clamp(0, 1)
        )

    if hillshade_image:
        # hillshade with default parameters
        hillshaded = hillshade(image_rgb, image, **hillshade_args)

    return hillshaded


def degree_to_radians_image(image):
    """
    Transform GEE image from degrees to radians
    :param image: GEE image object
    :return: Google Earth Engine ee.Image() object
    """
    return ee.Image(image).toFloat().multiply(3.1415927).divide(180)


def resample_landmask(image):
    """
    Bicubic resampling and apply mask of land to image, renaming band to elevation
    :param image: GEE image object
    :return: Google Earth Engine ee.Image() object
    """
    return (
        ee.Image(image)
        .float()
        .resample("bicubic")
        .updateMask(LANDMASK)
        .rename("elevation")
    )


def mosaic_elevation_datasets(dataset_list=None):
    """
    Create an image mosaic from multiple elevation data sources in GEE.
    :param dataset_list: List of dataset ids, as defined in dataset_elevation_parameters.json
    :return: Google Earth Engine ee.Image() object, elevation image
    """
    band_name = "elevation"
    images = []
    image_collections = []
    for dataset in dataset_list:
        params = ELEVATION_DATA.get(dataset, None)
        if not params:
            raise error_handler.handle_invalid_usage(
                f"No parameters defined for {dataset} in dataset_elevation_parameters.json"
            )
        type = params.get("type", None)
        source = params.get("source", None)
        band = params.get("band", None)
        bathymetry = params.get("bathymetry", None)
        topography = params.get("topography", None)

        if type == "Image":
            image = ee.Image(source)
            image = image.select(band).rename(band_name)
            if dataset == "ALOS":
                alos_mask = image.mask().eq(1)
                image = (
                    image.resample("bicubic")
                    .updateMask(alos_mask.And(LANDMASK))
                    .float()
                )
            elif topography and not bathymetry:
                image = resample_landmask(image)
            else:
                image = image.float().resample("bicubic")
            images.append(image)
        elif type == "ImageCollection":
            image_collection = ee.ImageCollection(source)
            image_collection = image_collection.map(resample_landmask)
            image_collections.append(image_collection)

    dems = ee.ImageCollection(images)
    for collection in image_collections:
        dems = dems.merge(collection)

    elevation_image = ee.ImageCollection(dems).mosaic()
    return ee.Image(elevation_image)


def generate_elevation_map(dataset_list=None, min=None, max=None):
    """
    Create a WMS tile url from GEE for an image mosaic from multiple elevation data sources in GEE.
    :param dataset_list: List of dataset ids, as defined in dataset_elevation_parameters.json
    :return: Dictionary, elevation image WMS tile info
    """
    if not dataset_list:
        dataset_list = ELEVATION_DATA.keys()

    mosaic_image = mosaic_elevation_datasets(dataset_list)
    data_params = deepcopy(
        DATASETS_VIS["projects/dgds-gee/bathymetry/gebco/2019"]
    )  # prevent mutation of global state

    if min is not None:
        data_params["bathy_vis_params"]["min"] = min
    if max is not None:
        data_params["topo_vis_params"]["max"] = max

    final_image = visualize_elevation(
        image=mosaic_image,
        data_params=data_params,
        bathy_only=False,
        hillshade_image=True,
    )
    url = _get_gee_url(final_image)
    # TODO: clean up, repeated content from gebco
    info = {}
    info["dataset"] = "elevation"
    info["band"] = "elevation"
    linear_gradient = []
    palette = (
        data_params["bathy_vis_params"]["palette"]
        + data_params["topo_vis_params"]["palette"]
    )
    n_colors = len(palette)
    offsets = np.linspace(0, 100, num=n_colors)
    for color, offset in zip(palette, offsets):
        linear_gradient.append(
            {"offset": "{:.3f}%".format(offset), "opacity": 100, "color": color}
        )
    info.update(
        {
            "url": url,
            "linearGradient": linear_gradient,
            "min": data_params["bathy_vis_params"]["min"],
            "max": data_params["topo_vis_params"]["max"],
            "imageId": None,
            "datasets": list(dataset_list),
            "function": "mosaic_elevation_datasets",
        }
    )
    return info


def visualize_gebco(source, band, min=None, max=None):
    """
    Specialized function to visualize GEBCO data
    :param source: String, Google Earth Engine image id
    :param band: String, band of image to visualize
    :return: Dictionary
    """
    data_params = deepcopy(DATASETS_VIS[source])  # prevent mutation of global state
    if min is not None:
        data_params["bathy_vis_params"]["min"] = min
    if max is not None:
        data_params["topo_vis_params"]["max"] = max

    image = ee.Image(source)

    gebco = image.select(data_params["bandNames"][band])
    land_mask = LANDMASK

    hillshaded = visualize_elevation(
        image=gebco,
        land_mask=land_mask,
        data_params=data_params,
        bathy_only=False,
        hillshade_image=True,
    )
    url = _get_gee_url(hillshaded)

    info = {}
    info["dataset"] = "gebco"
    info["band"] = band
    linear_gradient = []
    palette = (
        data_params["bathy_vis_params"]["palette"]
        + data_params["topo_vis_params"]["palette"]
    )
    n_colors = len(palette)
    offsets = np.linspace(0, 100, num=n_colors)
    for color, offset in zip(palette, offsets):
        linear_gradient.append(
            {"offset": "{:.3f}%".format(offset), "opacity": 100, "color": color}
        )

    info.update(
        {
            "url": url,
            "linearGradient": linear_gradient,
            "min": data_params["bathy_vis_params"]["min"],
            "max": data_params["topo_vis_params"]["max"],
            "imageId": source,
        }
    )
    return info


def _generate_image_info(im, params):
    """"generate url and tokens for image"""
    image = ee.Image(im)

    if "sld_style" in params:
        m = image.sldStyle(params.get("sld_style"))
        del params["sld_style"]
    elif "palette" in params:
        m = image.visualize(
            **{
                "min": params.get("min"),
                "max": params.get("max"),
                "palette": params.get("palette"),
            }
        )
    else:
        m = image

    if "hillshade" in params:
        # also pass along hillshade arguments
        hillshade_args = params.get("hillshade_args", {})
        m = hillshade(m, image, **hillshade_args)

    url = _get_gee_url(m)

    linear_gradient = []
    if "palette" in params:
        n_colors = len(params.get("palette"))
        palette = params.get("palette")
        offsets = np.linspace(0, 100, num=n_colors)
        if "function" in params:
            if params["function"] == "log":
                # if log scaling applied, apply log scale to linear gradient palette offsets
                offsets = np.logspace(0.0, 2.0, num=n_colors, base=10.0)
                offsets[0] = 0.0
        for color, offset in zip(palette, offsets):
            linear_gradient.append(
                {"offset": "{:.3f}%".format(offset), "opacity": 100, "color": color}
            )

    params.update({"url": url, "linearGradient": linear_gradient})
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
        image = image.log10().rename("log")
    if operation == "magnitude":
        image = image.pow(2).reduce(ee.Reducer.sum()).sqrt().rename("magnitude")
    if operation == "flowmap":
        image.unitScale(
            data_params["min"][operation], data_params["max"][operation]
        ).unmask(-9999)
        data_mask = image.eq(-9999).select(data_params["bandNames"][band])
        image = image.clamp(0, 1).addBands(data_mask)

    return image


def get_image_collection_info(
    source, start_date=None, end_date=None, image_num_limit=None
):
    """
    Return list of objects with imageId and time for all images in an ImageCollection, or Image, source
    :param source: String,
    :param start_date: String, start date to filter collection on
    :param end_date: String, end date to filter collection on
    :param image_num_limit: limit of objects to return
    :return: List of dictionaries
    """
    data_params = get_dgds_source_vis_params(source)
    type = data_params.get("type", "ImageCollection")

    # Get images based on source requested
    if type == "ImageCollection":
        collection = ee.ImageCollection(source)
    elif type == "Image":
        collection = ee.ImageCollection.fromImages([ee.Image(source)])
    else:
        msg = f"Object of type {type} not supported."
        logger.debug(msg)
        return

    if end_date and not start_date:
        msg = f"If endDate provided, must also include startDate"
        logger.debug(msg)
        return

    if start_date:
        start = ee.Date(start_date)
        end = start.advance(1, "day")
        if end_date:
            end = ee.Date(end_date)
        collection = collection.filterDate(start, end)

    n_images = collection.size().getInfo()
    if not n_images:
        msg = (
            f"No images available between startDate={start_date} and endDate={end_date}"
        )
        logger.debug(msg)
        return

    if image_num_limit:
        # get a limited number of latest images
        collection = collection.limit(image_num_limit, "system:time_start", False)

    # Sort ascending
    collection = collection.sort("system:time_start", True)

    # Map complete objects in GEE, as aggregation on individual properties
    # can run out of sync with each other in case a property is skipped (null)
    # Retrieving the objects locally will fail on collections over 5000 items.
    def map_id_time(item):
        iitem = ee.Image(item)
        date = iitem.get("system:time_start")
        sdate = ee.Algorithms.If(date, ee.Date(date).format(), None)
        d = ee.Dictionary({"imageId": iitem.get("system:id"), "date": sdate})
        return d

    response = collection.toList(collection.size()).map(map_id_time).getInfo()

    return response


def _get_wms_url(
    image_id,
    type="ImageCollection",
    band=None,
    datasets=None,
    function=None,
    min=None,
    max=None,
    palette=None,
):
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
    # GEBCO is styled differently, non-linear color palette
    if "gebco" in image_id:
        info = visualize_gebco(image_id, band, min, max)
        return info

    if function == "mosaic_elevation_datasets":
        info = generate_elevation_map(dataset_list=datasets, min=min, max=max)
        return info

    image = ee.Image(image_id)
    # Get image date
    try:
        image_date = image.date().format().getInfo()
    except Exception as e:
        msg = f"Image {image_id} does not have an assigned date."
        logger.debug(msg)
        image_date = None

    image_location_parameters = image_id.split("/")
    if type == "ImageCollection":
        source = ("/").join(image_location_parameters[:-1])
    elif type == "Image":
        source = image_id

    # Default visualization parameters
    vis_params = {
        "min": 0,
        "max": 1,
        "palette": ["#000000", "#FFFFFF"],
    }

    # see if we have default visualization parameters stored for this source
    source_params = DATASETS_VIS.get(source, None)
    if source_params:
        if band:
            band_name = source_params["bandNames"][band]
            vis_params["band"] = band
            image = image.select(band_name)
            vis_params["min"] = source_params["min"][band]
            vis_params["max"] = source_params["max"][band]
            vis_params["palette"] = source_params["palette"][band]
            style = source_params.get("sld_style", {}).get(band)
            if style:
                vis_params["sld_style"] = style
        if function:
            if isinstance(source_params["function"], list):
                assert function in source_params["function"]
                vis_params["function"] = function
                # band = function
                image = apply_image_operation(image, function)
                vis_params["min"] = source_params["min"][function]
                vis_params["max"] = source_params["max"][function]
                vis_params["palette"] = source_params["palette"][function]
            else:
                assert function == source_params["function"][band]
                function = source_params.get("function", None).get(band, None)
                vis_params["min"] = source_params["min"][band]
                vis_params["max"] = source_params["max"][band]
                vis_params["palette"] = source_params["palette"][band]
            vis_params["function"] = function
            image = apply_image_operation(
                image, function, data_params=vis_params, band=band
            )
    else:
        try:
            image = image.select(band)
        except Exception as e:
            msg = f"Error selecting band {band}, {e}"
            logger.debug(msg)
            return

    # Overwrite vis params if provided in request,
    # min/max values can be zero, should not be None
    if min is not None:
        vis_params["min"] = min
    if max is not None:
        vis_params["max"] = max
    if palette:
        vis_params["palette"] = palette

    if source == "projects/dgds-gee/gloffis/hydro":
        image = image.mask(image.gte(0))

    # validate min is less than max, otherwise raise error
    validate_min_lt_max(vis_params["min"], vis_params["max"])

    info = _generate_image_info(image, vis_params)
    info["source"] = source
    info["date"] = image_date
    info["imageId"] = image_id

    # Scale min and max if log function applied
    if function == "log":
        info["min"] = 10 ** vis_params["min"]
        info["max"] = 10 ** vis_params["max"]

    return info


def _get_gee_url(image):
    """
    Generate GEE url to access map from GEE image
    :param image: GEE image object
    :return: String, url
    """
    m = image.getMapId()
    mapid = m.get("mapid")
    url = "https://earthengine.googleapis.com/v1alpha/{mapid}/tiles/{{z}}/{{x}}/{{y}}".format(
        mapid=mapid
    )
    return url
