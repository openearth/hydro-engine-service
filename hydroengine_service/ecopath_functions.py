import ee

def submit_ecopath_job():
    # Variable declaration, can be coverted to function args
    scale = 10000
    crs = 'EPSG:3035'
    model = 'HYCOM'
    t_start = ee.Date('2020-07-01')
    t_stop = ee.Date('2021-07-01')
    bucket = 'slr'
    debug = False


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
    hycom_temperature = ee.ImageCollection("HYCOM/sea_temp_salinity")

    # Settings
    palette = ['9EB0FF','93AFFA','87ADF4','79ABED','6CA9E6','60A5DF','54A0D5','489ACA','3E90BC',
        '3787AF','327EA3','2D7597','296B8B','25607C','225771','1E4E65','1B465A','183D4F','153342',
        '122C38','11242E','101D25','11181C','121214','160E0D','1B0B07','210B03','270D01','2D0E00',
        '340F00','3B1100','421301','4B1602','541905','5D1E09','68240F','732B16','803620','8A3F2A',
        '944834','9E513F','A85A4A','B46658','BE6F63','C8796F','D2837A','DD8D86','EA9995','F4A3A1',
        'FFADAD']  # palettes.crameri.berlin[50]
    period = 'month'
    n_periods = 12

    # Determine all start of periods
    periods = ee.List.sequence(0, n_periods).map(lambda i: t_start.advance(i, period)) 

    # Determine all period ranges 
    def create_period_step(num_period):
        return ee.DateRange(
            t_start.advance(num_period, period),  # take i-th period
            t_start.advance(ee.Number(num_period).add(1), period)  # until i+1th period
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
            period_range.stop()
        )

        image_count = selected.size()
        selected = selected.mean()
        selected = selected.set('model', model)
        selected = selected.set('tStart', period_range.start())
        selected = selected.set('tStop', period_range.end())
        selected = selected.set('imageCount', image_count)
        selected = selected.set('units', 'm/s')
        return selected
    
    def export_map(image, model, export_path, geometry, scale, crs):
        ee.batch.Export.toCloudStorage(
            image=image,
            description=export_path.replace('/', '_').replace(":", '_'),  # Regex for /:/g == .replace(":")?
            bucket=bucket,
            fileNamePrefix=export_path,
            region=geometry,
            scale=scale,
            crs=crs 
        )
        return export_path

    # Now for some annoying stuff, we need to make a list of all properties
    # so that we can call export with local variables

    def prep_export(period_range):
        t_start = ee.DateRange(period_range).start()
        export_path = ee.String("ecopath/").cat(
            ee.String(model).cat(t_start.format())
        )
        im = get_map(model, period_range)
        im = im.set('path', export_path)
        im = im.set('tStart',  t_start)
        im = im.set('system:time_start', t_start.millis())
        im = im.set('period', period_range)
        return im

    images = period_ranges.map(prep_export)

    # filter out empty images
    images = ee.ImageCollection(images)
    images = images.filter(ee.Filter.gt('imageCount', 0))

    paths = images.aggregate_array('path')

    def export_to_all_paths(paths):
        def export_path(path):
            im = images.filter(ee.Filter.eq("path", path)).first()
            export_map(im, model, path, geometry, scale, crs)
        paths.map(export_path)
    
    paths.evaluate(export_to_all_paths)
