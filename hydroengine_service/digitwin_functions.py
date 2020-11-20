# coding: utf-8
import numpy as np
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
