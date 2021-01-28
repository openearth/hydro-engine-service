import json

import ee
import flask_cors
from flask import request, Response
from flask import Blueprint

from hydroengine_service import dgds_functions
from hydroengine_service import error_handler

v1 = Blueprint("dgds-v1", __name__)
v2 = Blueprint("dgds-v2", __name__)


@v1.route("/get_glossis_data", methods=["POST"])
@flask_cors.cross_origin()
def get_glossis_data():
    """
    Get GLOSSIS data. Either currents, wind, or waterlevel dataset must be provided.
    If waterlevel dataset is requested, must specify if band water_level_surge, water_level,
    or astronomical_tide is requested
    :return:
    """
    r = request.get_json()
    dataset = r.get("dataset", None)
    image_id = r.get("imageId", None)
    band = r.get("band", None)

    function = r.get("function", None)
    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    if not (dataset or image_id):
        msg = f"dataset or imageId required."
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)
    if dataset:
        source = "projects/dgds-gee/glossis/" + dataset
    if image_id:
        image_location_parameters = image_id.split("/")
        source = ("/").join(image_location_parameters[:-1])

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        function=function,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_gloffis_data", methods=["POST"])
@flask_cors.cross_origin()
def get_gloffis_data():
    """
    Get GLOFFIS data. dataset must be provided.
    :return:
    """
    r = request.get_json()
    dataset = r.get("dataset", None)
    band = r["band"]
    image_id = r.get("imageId", None)

    function = r.get("function", None)
    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    source = None
    if not (dataset or image_id):
        msg = f"dataset or imageId required."
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)
    if dataset:
        source = "projects/dgds-gee/gloffis/" + dataset
    if image_id:
        image_location_parameters = image_id.split("/")
        source = ("/").join(image_location_parameters[:-1])

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        function=function,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_metocean_data", methods=["POST"])
@flask_cors.cross_origin()
def get_metocean_data():
    """
    Get metocean data. dataset must be provided.
    :return:
    """
    r = request.get_json()
    dataset = r.get("dataset", None)
    band = r["band"]
    image_id = r.get("imageId", None)

    function = r.get("function", None)
    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    if not (dataset or image_id):
        msg = f"dataset or imageId required."
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)
    if dataset:
        source = "projects/dgds-gee/metocean/waves/" + dataset
    if image_id:
        source = image_id

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        function=function,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_gebco_data", methods=["GET", "POST"])
@flask_cors.cross_origin()
def get_gebco_data():
    r = request.get_json()
    dataset = r.get("dataset", "gebco")
    band = r.get("band", "elevation")
    image_id = r.get("imageId", None)

    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    if dataset:
        source = "projects/dgds-gee/bathymetry/" + dataset + "/2019"
    if image_id:
        source = image_id

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_gll_dtm_data", methods=["GET", "POST"])
@flask_cors.cross_origin()
def get_gll_dtm_data():
    r = request.get_json()
    dataset = r.get("dataset", "gll_dtm")
    band = r.get("band", "b1")

    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    source = "users/maartenpronk/gll_dtm/gll_dtm_v1"
    sld_style = """<RasterSymbolizer>
        <ColorMap type="intervals">
            <ColorMapEntry color="#ff0000" quantity="-1" label="-7 - -1 [m +MSL]"/>
            <ColorMapEntry color="#9900ff" quantity="0" label="-1 - 0 [m +MSL]"/>
            <ColorMapEntry color="#261cf0" quantity="1" label="0 - 1 [m +MSL]"/>
            <ColorMapEntry color="#00b0f0" quantity="2" label="1 - 2 [m +MSL]"/>
            <ColorMapEntry color="#d9d9d9" quantity="5" label="2 - 5 [m +MSL]"/>
            <ColorMapEntry color="#c2ffa5" quantity="10" label="5 - 10 [m +MSL]"/>
        </ColorMap>
        </RasterSymbolizer>"""

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=source,
        band=band,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
        sld_style=sld_style,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_elevation_data", methods=["GET", "POST"])
@flask_cors.cross_origin()
def get_elevation_data():
    r = request.get_json()
    datasets = r.get("datasets", None)
    image_id = r.get("imageId", None)
    source = None
    if datasets:
        source = datasets
    if image_id:
        source = image_id

    min = r.get("min", None)
    max = r.get("max", None)

    image_info = dgds_functions.generate_elevation_map(
        dataset_list=source, min=min, max=max
    )

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_chasm_data", methods=["POST"])
@flask_cors.cross_origin()
def get_chasm_data():
    """
    Get metocean data. dataset must be provided.
    :return:
    """
    r = request.get_json()
    dataset = r.get("dataset", None)
    band = r["band"]
    image_id = r.get("imageId", None)

    function = r.get("function", None)
    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    source = None
    # Can provide either dataset and/or image_id
    if not (dataset or image_id):
        msg = f"dataset or imageId required."
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)

    if dataset:
        source = "projects/dgds-gee/chasm/" + dataset
    elif image_id:
        image_location_parameters = image_id.split("/")
        source = ("/").join(image_location_parameters[:-1])

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        function=function,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")


@v1.route("/get_gtsm_data", methods=["POST"])
@flask_cors.cross_origin()
def get_gtsm_data():
    """
    Get GTSM data. Either waterlevel_return_period, or tidal_indicators dataset must be provided.
    See datasets_visualization_parameters.json for possible bands to request as band
    :return:
    """
    r = request.get_json()
    dataset = r.get("dataset", None)
    image_id = r.get("imageId", None)
    band = r.get("band", None)

    function = r.get("function", None)
    start_date = r.get("startDate", None)
    end_date = r.get("endDate", None)
    image_num_limit = r.get("limit", None)
    min = r.get("min", None)
    max = r.get("max", None)

    if not band:
        msg = f"band is a required parameter"
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)
    if dataset:
        source = "projects/dgds-gee/gtsm/" + dataset
    elif image_id:
        source = image_id
    else:
        msg = f"dataset or image_id is a required parameter"
        logger.error(msg)
        raise error_handler.InvalidUsage(msg)

    image_info = dgds_functions.get_dgds_data(
        source=source,
        dataset=dataset,
        image_id=image_id,
        band=band,
        function=function,
        start_date=start_date,
        end_date=end_date,
        image_num_limit=image_num_limit,
        min=min,
        max=max,
    )
    if not image_info:
        raise error_handler.InvalidUsage("No images returned.")

    return Response(json.dumps(image_info), status=200, mimetype="application/json")
