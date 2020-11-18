import ee


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
