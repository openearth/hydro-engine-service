# coding: utf-8
import numpy as np
import pandas as pd
import scipy.interpolate

import ee

# Levelized Cost of Energy function for AC/DC
# https://northseawindpowerhub.eu/wp-content/uploads/2019/02/112522-19-001.830-rapd-report-Cost-Evaluation-of-North-Sea-Offshore-Wind....pdf
# distance to port (km), depth (m), LCoE EUR/MWh
LCOE_POINTS = np.array([
    (0, 5, 26.8),
    (0, 10, 26.9),
    (100, 7, 26.9),
    (125, 5, 26.9),
    (0, 17, 27),
    (150, 16, 27),
    (300, 14, 27),
    (0, 27, 27.5),
    (150, 26, 27.5),
    (300, 24, 27.5),
    (0, 40, 29),
    (150, 39, 29),
    (300, 38, 29),
    (0, 55, 30.7),
    (150, 55, 30.7),
    (300, 55, 30.7),
    (50, 25, 27.1)
])

LCOE_fit = scipy.interpolate.SmoothBivariateSpline(LCOE_POINTS[:, 0], LCOE_POINTS[:, 1], LCOE_POINTS[:, 2], kx=2, ky=2)

def compute_area(feature):
    """compute area of feature"""
    feature = feature.set('area', feature.geometry().area())
    return feature


def magnitude(image):
    # Take the magnitude and angle of the first 2 bands
    squared = image.pow(ee.Image(2))
    magnitude = (
        squared
        .select(0)
        .add(
            squared.select(1)
        )
        .pow(ee.Image(0.5))
    )
    magnitude = magnitude.rename('wind_magnitude_mean')

    angle = image.select(1).atan2(image.select(0))
    angle = angle.rename('wind_angle_mean')

    result = image.addBands(magnitude)
    result = result.addBands(angle)
    return result

def create_turbine_grid(feature):
    """create an equidistant spaced grid (unrotated)"""
    feature = ee.Feature(feature)

    turbine_spacing = ee.Algorithms.If(
        feature.getNumber('turbine_spacing'),
        feature.getNumber('turbine_spacing'),
        1000
    )


    bounds = (
        feature
        .geometry()
        .bounds()
        .transform('EPSG:3857', 1)
    )

    distortion = compute_distortion(bounds)

    outer = (
        bounds
        .coordinates()
        .get(0)
    )

    ll = ee.List(outer).get(0)
    ur = ee.List(outer).get(2)
    left = ee.List(ll).get(0)
    right = ee.List(ur).get(0)
    lower = ee.List(ll).get(1)
    upper = ee.List(ur).get(1)
    x_grid = ee.List.sequence(
        left,
        right,
        # compute undistorted spacing
        distortion.getNumber('scaleX').multiply(turbine_spacing)
    )
    y_grid = ee.List.sequence(
        lower,
        upper,
        # compute undistorted  spacing
        distortion.getNumber('scaleY').multiply(turbine_spacing)
    )

    def iter_x(x):
        def iter_y(y):
            return [x, y]
        coords = y_grid.map(iter_y)
        return coords
    coords = x_grid.map(iter_x)
    coords = coords.flatten()

    points = ee.Geometry.MultiPoint(coords, 'EPSG:3857')
    points = points.transform('EPSG:4326')
    points = (
        points
        .intersection(feature.geometry())
    )
    id = feature.id().cat('-turbines')
    n_turbines =  points.coordinates().size()
    props = ee.Dictionary()
    props = props.set('id', id)
    props = props.set('n_turbines', n_turbines)
    props = props.set('turbine_spacing', turbine_spacing)
    grid = ee.Feature(points, props)
    return feature.copyProperties(grid)

def lcoe(distance_to_port, depth):
    """compute the levelized cost of energy for a windfarm"""

    lcoe = LCOE_fit.ev(distance_to_port, depth)
    return float(lcoe)


def windpower(V):
    # 1 / 2 * ρ * performance * A * V^3 * Ng
    # air density (ρ)= 0= 0kilogram/meter^3
    rho = 1.2
    # Betz law
    performance = 0.35
    # rotor swept area (A)= 0= 0meter^2
    rotor_radius = 110
    A = np.pi * rotor_radius * rotor_radius
    # coefficient of performance (Cp)= 0= 0
    # wind velocity (V)= 0= 0meter/second
    height = 260
    # generator efficiency (Ng)
    Ng = 0.8
    # gear box bearing efficiency (Nb)
    Nb = 0.95
    P = (V ** 3) * (1/2 * rho * performance * A *  Ng)
    return P

def compute_feature(feature):
    """compute relevant properties for windfarm"""

    print(feature)
    # roughness length at sea
    roughness = 0.0002 #  m
    # default height
    height = 130
    height_0 = 10
    feature['height'] = feature['properties'].get('height', 130)

    conversion = (
        np.log(height / roughness)
        /
        np.log(height_0 / roughness)
    )

    magnitude = feature['properties']['wind_magnitude_mean'] * conversion
    power = windpower(magnitude)
    area = feature['properties']['area']

    # assuming square  area
    n_turbines = feature['properties']['n_turbines']
    turbine_spacing = feature['properties']['turbine_spacing']
    area_per_turbine = turbine_spacing

    depth = feature['properties']['bathymetry'] * -1
    distance_to_port = feature['properties']['distance_to_port']

    feature['properties'].update({
        "wind_magnitude_mean_height": magnitude,
        "wind_power_mean": power,
        "levelized_cost_of_energy": lcoe(distance_to_port, depth), # convert to EUR/Wh
        "n_turbines": n_turbines,
        "area": area,
        "area_per_turbine": area_per_turbine,
        "turbine_spacing": turbine_spacing,
        # deprecated
        "spacing": turbine_spacing,
        "wind_power_total": power * n_turbines
    })
    return feature


def compute_distortion(geometry):
    """
    Compute the distortion  in ESPG:3857  in the center of the geometry
    returned  as {scaleX,  scaleY}
    """
    # create two versions  of  the geometry in  both  4326 and in 3857
    center4326 = geometry.centroid(1).transform('EPSG:4326')
    center3857 = geometry.centroid(1).transform('EPSG:3857')
    # lookup coordinates
    coords3857 = center3857.coordinates()
    # move 1 meter sideward
    coordsPlusOneX = [ee.Number(coords3857.get(0)).add(1), ee.Number(coords3857.get(1))]
    centerPlusOneX = ee.Geometry.Point(coordsPlusOneX, 'EPSG:3857')
    # and up
    coordsPlusOneY = [ee.Number(coords3857.get(0)), ee.Number(coords3857.get(1)).add(1)]
    centerPlusOneY = ee.Geometry.Point(coordsPlusOneY, 'EPSG:3857')
    #
    scaleX = ee.Number(1).divide(centerPlusOneX.distance(center3857))
    scaleY = ee.Number(1).divide(centerPlusOneY.distance(center3857))
    result = ee.Dictionary({"scaleX": scaleX, "scaleY": scaleY})
    return result

KNOWN_MODELS = ('HYCOM', 'GLOSSIS')

def submit_ecopath_jobs(scale, crs, model, t_start, n_periods):
    """
    submit ecopath job to calculate a monthly image for northsea currents with the following
    args:
        scale: scale of the model pixels in m
        model: Either "HYCOM" or "GLOSSIS"
        t_start: string containing start-date
        crs: crs of images to be exported
        n_periods: number of months to export from t_start
    returns:
        list of tasks that were submitted to earthengine
    """

    assert model in KNOWN_MODELS, f"model not in {KNOWN_MODELS}"

    period = 'month'
    t_stop = pd.Timestamp(t_start) + pd.DateOffset(months=n_periods)
    bucket = 'hydro-engine-public'

    extent = [
        3463000.0001221001148224, # xmin
        3117163.4356725001707673, # ymin
        4313000.0001221001148224, # xmax
        4257163.4356725001707673  # ymax
    ]
    geometry =  ee.Geometry.Polygon(
        coords=[[
            [extent[0], extent[1]],
            [extent[0], extent[3]],
            [extent[2], extent[3]],
            [extent[2], extent[1]],
            [extent[0], extent[1]]
        ]], 
        proj=crs, 
        geodesic=False, 
        maxError=1
    )

    # Get ImageCollections
    hycom_currents = ee.ImageCollection("HYCOM/sea_water_velocity")
    glossis_currents = ee.ImageCollection("projects/dgds-gee/glossis/currents")
    
    # Determine all period ranges 
    def create_period_step(num_period):
        return ee.DateRange(
            ee.Date(t_start).advance(num_period, period),  # take i-th period
            ee.Date(t_start).advance(ee.Number(num_period).add(1), period)  # until i+1th period
        )

    period_ranges = ee.List.sequence(0, n_periods - 1).map(create_period_step)

    # Prepare the datasets
    # make datasets more consistent
    # Use top layer for velocities in hycom
    def get_top_layer(img):
        result = img \
            .select(['velocity_u_0', 'velocity_v_0']) \
            .rename(['velocity_u', 'velocity_v']) \
            .float() \
            .multiply(0.001)
        
        result = result.copyProperties(img)
        result = result.set('system:time_start', img.get('system:time_start'))
        return ee.Image(result)

    # Apply the get top layer function to all images
    hycom_currents = hycom_currents.filterDate(t_start, t_stop)
    hycom_currents = hycom_currents.map(get_top_layer)

    def get_compatible_glossis_currents(img):
        result = img.rename(['velocity_u', 'velocity_v'])
        result = result.resample('bicubic')
        return result.set('system:time_start', img.get('system:time_start'))

    glossis_currents = glossis_currents.map(get_compatible_glossis_currents)

    def get_map(model, period_range):
        models = {
            "HYCOM": hycom_currents,
            "glossis": glossis_currents
        }

        selected = models[model]
        period_range = ee.DateRange(period_range)

        selected = selected.filterDate(
            period_range.start(),
            period_range.end()
        )

        image_count = selected.size()
        selected = selected.mean()
        selected = selected.set('model', model)
        selected = selected.set('tStart', period_range.start())
        selected = selected.set('tStop', period_range.end())
        selected = selected.set('imageCount', image_count)
        selected = selected.set('units', 'm/s')
        return selected
    
    def export_map(image, export_path, geometry, scale, crs):
        task =  ee.batch.Export.image.toCloudStorage(
            image=image,
            description=export_path,
            bucket=bucket,
            fileNamePrefix=export_path,
            region=geometry,
            scale=scale,
            crs=crs 
        )
        task.start()
        return task

    # Now for some annoying stuff, we need to make a list of all properties
    # so that we can call export with local variables

    def prep_export(period_range):
        _t_start = ee.DateRange(period_range).start()
        export_path = ee.String("ecopath/").cat(
            ee.String(model).cat(_t_start.format())
        )
        im = get_map(model, period_range)
        im = im.set('path', export_path)
        im = im.set('tStart',  _t_start)
        im = im.set('system:time_start', _t_start.millis())
        im = im.set('period', period_range)
        return im

    images = period_ranges.map(prep_export)

    # filter out empty images
    images = ee.ImageCollection(images)
    images = images.filter(ee.Filter.gt('imageCount', 0))

    # sort images on path
    images = images.sort("path")
    # paths will shading images "path" property as a list
    date_range = pd.date_range(start=t_start, periods=n_periods, freq=pd.DateOffset(months=1))
    paths=[f"ecopath_{model}{dr.strftime('%Y-%m-%dT%X').replace(':', '_')}" for dr in date_range]

    def export_path(path):
        # find the image that corresponds to the path
        im = images.filter(ee.Filter.eq("path", path)).first()
        return export_map(im, path, geometry, scale, crs)

    task_list = [export_path(path) for path in paths]
        
    return task_list
