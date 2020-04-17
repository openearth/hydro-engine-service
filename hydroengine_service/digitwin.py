# coding: utf-8
import numpy as np
import ee


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
    return grid

def lcoe(power):
    """compute the levelized cost of energy for a windfarm"""

    # TODO: follow this approach:
    # https://northseawindpowerhub.eu/wp-content/uploads/2019/02/112522-19-001.830-rapd-report-Cost-Evaluation-of-North-Sea-Offshore-Wind....pdf

    # formula is not in si units, explicitly mention  unit
    power_kW = power.multiply(1000)
    # Based on these numbers
    # https://www.pbl.nl/sites/default/files/downloads/pbl-2019-costs-of-offshore-wind-energy-2018_3623.pdf

    investment_cost = 1800 # per kW
    operation_cost = 50 # EUR/kW/year
    grid_connection_cost = 0.02 # EUR/kWh
    base_cost = 0.048 # EUR/kWh
    load_hours  = 4600 # hours/year
    lifetime = 25 # years
    hours = load_hours * lifetime
    base_cost_life = power_kW.multiply(base_cost * hours)
    grid_connection_cost_life  =  power_kW.multiply(grid_connection_cost  * hours)
    operation_cost_life = power_kW.multiply(operation_cost * lifetime)
    investment_cost_life  = power_kW.multiply(investment_cost)
    # TODO: this doesn't quite add up
    cost = base_cost_life.add(grid_connection_cost_life).add(operation_cost_life).add(investment_cost_life)
    lcoe = cost.divide(power_kW.multiply(hours))

    # For now return the  LCOE based on boven de Wadden [EUR/wH]
    lcoe = ee.Number( 0.071 / 1000)
    return lcoe


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
    P = (
        V
        .pow(3)
        .multiply(1/2 * rho * performance * A *  Ng)
    )
    return P

def compute_feature(feature):
    """compute relevant properties for windfarm"""

    # roughness length at sea
    roughness = 0.0002 #  m
    height = 260
    height_0 = 10
    feature = feature.set({"height": height})

    conversion = (
        np.log(height / roughness)
        /
        np.log(height_0 / roughness)
    )

    magnitude = feature.getNumber('wind_magnitude_mean').multiply(conversion)
    power = windpower(magnitude)
    area = feature.geometry().area()

    # assuming square  area
    turbine_grid = create_turbine_grid(feature)
    n_turbines = turbine_grid.get('n_turbines')
    area_per_turbine = turbine_grid.getNumber('turbine_spacing').pow(2)


    feature = feature.set({
        "wind_magnitude_mean_height": magnitude,
        "wind_power_mean": power,
        "levelized_cost_of_energy": lcoe(power).multiply(1000000), # convert to EUR/Wh
        "n_turbines": n_turbines,
        "area": area,
        "area_per_turbine": area_per_turbine,
        "turbine_spacing": turbine_grid.get('turbine_spacing'),
        # deprecated
        "spacing": turbine_grid.get('turbine_spacing'),
        "wind_power_total": power.multiply(n_turbines)
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
