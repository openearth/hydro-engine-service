import json
import logging
import pytest
import time

from . import auth
import ee

from hydroengine_service import main

# import palettes

logger = logging.getLogger(__name__)


TEST_BUCKET = "hydro-engine-public"
TEST_SUBFODLER = "test"
TEST_REGION = ee.Geometry.Polygon([  # Deltares Delft
  [4.373489981809318,51.97731280009385],
  [4.398423796811759,51.97731280009385],
  [4.398423796811759,51.99036964506517],
  [4.373489981809318,51.99036964506517],
  [4.373489981809318,51.97731280009385]
])


class TestClient:
    @pytest.fixture(autouse=True)
    def setUp(self):
        main.app.testing = True
        self.client = main.app.test_client()

    def test_root(self):
        r = self.client.get('/')
        assert r.status_code == 200
        assert 'Welcome' in r.data.decode('utf-8')

    def test_get_bathymetry_vaklodingen(self):
        input = {
            "dataset": "vaklodingen",
            "begin_date": "2010-01-01",
            "end_date": "2015-01-01"
        }

        r = self.client.get('/get_bathymetry', data=json.dumps(input),
                            content_type='application/json')

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

    def test_get_bathymetry_vaklodingen_custom_palette(self):
        palette = "#064273,#76b6c4"

        input = {
            "dataset": "vaklodingen",
            "begin_date": "2010-01-01",
            "end_date": "2015-01-01",
            "palette": palette
        }

        r = self.client.get(
            '/get_bathymetry',
            data=json.dumps(input),
            content_type='application/json'
        )

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

        assert result['palette'] == palette

    def test_get_bathymetry_vaklodingen_hillshade(self):
        input = {
            "dataset": "vaklodingen",
            "begin_date": "2010-01-01",
            "end_date": "2015-01-01",
            "hillshade": True,
            "min": -2000,
            "max": 500
        }

        r = self.client.get(
            '/get_bathymetry',
            data=json.dumps(input),
            content_type='application/json'
        )

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

        assert result['hillshade'] == True

        print(json.dumps(result))

    def test_get_bathymetry_kustlidar(self):
        input = {
            "dataset": "kustlidar",
            "end_date": "2018-01-01",
            "begin_date": "2001-01-01"
        }

        r = self.client.get(
            '/get_bathymetry',
            data=json.dumps(input),
            content_type='application/json'
        )

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

    def test_get_raster_profile(self):
        line = {
            "dataset": "bathymetry_jetski",
            "begin_date": "2011-08-02",
            "end_date": "2011-09-02",
            "polyline": {
                "geodesic": True,
                "type": "LineString",
                "coordinates": [
                    [
                        5.03448486328125,
                        53.53541058046374
                    ],
                    [
                        5.58380126953125,
                        53.13029407190636
                    ]
                ]
            },
            "scale": 100
        }

        r = self.client.post(
            '/get_raster_profile',
            data=json.dumps(line),
            content_type='application/json'
        )
        assert r.status_code == 200

    def test_get_catchments(self):
        request = {
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [
                          5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "dissolve": True,
            "catchment_level": 6,
            "region_filter": ""
        }

        r = self.client.post(
            '/get_catchments',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert r.status_code == 200

    def test_get_rivers(self):
        request = {
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [
                          5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "filter_upstream_gt": 1000,
            "catchment_level": 6,
            "region_filter": ""
        }

        r = self.client.post(
            '/get_rivers',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert r.status_code == 200

    def test_get_lakes(self):
        request = {
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [
                          5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "id_only": False
        }

        r = self.client.post(
            '/get_lakes',
            data=json.dumps(request),
            content_type='application/json'
        )

        assert r.status_code == 200

    def test_get_water_mask(self):
        request = {
            "region": {
                "geodesic": False,
                "type": "Polygon",
                "coordinates": [[
                    [5.986862182617186, 52.517369933821186],
                    [6.030635833740234, 52.517369933821186],
                    [6.030635833740234, 52.535439735112924],
                    [5.986862182617186, 52.535439735112924],
                    [5.986862182617186, 52.517369933821186]
                ]]
            },
            "use_url": False,
            "start": "2013-01-01",
            "stop": "2015-01-01",
            "scale": 30,
            "crs": "EPSG:3857"
        }

        r = self.client.post(
            '/get_water_mask',
            data=json.dumps(request),
            content_type='application/json')

        assert r.status_code == 200

    def test_get_sea_surface_height_time_series(self):
        """test sea surface height timeseries"""
        request = {
            "region": {"type": "Point", "coordinates": [54.0, 0.0]}
        }

        r = self.client.post(
            '/get_sea_surface_height_time_series',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert r.status_code == 200

    def test_get_liwo_scenarios_max_no_region(self):
        """test get liwo scenarios max"""
        request = {
            "liwo_ids": [635, 1903, 1948],
            "band": "waterdepth",
            "reducer": "max"
        }
        resp = self.client.post(
            '/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'mapid' in result

    def test_get_liwo_scenarios_max_export(self):
        """test get liwo scenarios max"""

        # some of these variables are only used for export
        request = {
            "liwo_ids": [635, 1948],
            "band": "waterdepth",
            "reducer": "max",
            "region": {
                "geodesic": False,
                "type": "Polygon",
                "coordinates": [[
                    [6.0161056877902865, 51.41901371286102],
                    [6.2495651604465365, 51.417729076754576],
                    [6.245101964645755, 51.54985700463136],
                    [6.0174789788059115, 51.54836255319905],
                    [6.0161056877902865, 51.41901371286102]
                ]]
            },
            "scale": 30,
            "export": True,
            "crs": "EPSG:28992"
        }
        resp = self.client.post(
            '/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200, resp.data

        result = json.loads(resp.data)

        assert 'mapid' in result

    def test_get_liwo_scenarios_max_regional_and_primary(self):
        """test get liwo scenarios max"""
        request = {
            "liwo_ids": [209, 10634],
            "band": "waterdepth",
            "reducer": "max"
        }
        resp = self.client.post(
            '/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200, resp.data

        result = json.loads(resp.data)
        with open('test-data.txt', 'w') as outfile:
            json.dump(result, outfile)

        assert 'mapid' in result

    def test_v2_get_liwo_scenarios_max_no_region(self):
        """test get liwo scenarios max"""
        request = {
            "liwo_ids": [18037, 18038, 18039],
            "band": "waterdepth"
        }
        resp = self.client.post(
            '/v2/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200, resp.data

        result = json.loads(resp.data)

        assert 'mapid' in result

    def test_v2_get_liwo_scenarios_max_export(self):
        """test get liwo scenarios max"""

        # some of these variables are only used for export
        # this only works for 50m scale
        request = {
            "liwo_ids": [18037, 18038, 18039],
            "band": "waterdepth",
            "scale": 50,
            "export": True
        }
        resp = self.client.post(
            '/v2/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200, resp.data

        result = json.loads(resp.data)

        assert 'export_url' in result

    def test_v2_get_liwo_scenarios_max_regional_and_primary(self):
        """test get liwo scenarios max"""
        request = {
            "liwo_ids": [18037, 621],
            "band": "waterdepth"
        }
        resp = self.client.post(
            '/v2/get_liwo_scenarios',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200, resp.data

        result = json.loads(resp.data)
        with open('test-data.txt', 'w') as outfile:
            json.dump(result, outfile)

        assert 'mapid' in result

    def test_get_glossis_data_with_waterlevel(self):
        """test get glossis waterlevel data, latest with no time stamp"""

        request = {
            "dataset": "waterlevel",
            "band": "water_level"
        }
        resp = self.client.post(
            '/get_glossis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'band' in result
        assert result['dataset'] == "waterlevel"

    def test_get_glossis_data_with_current(self):
        """test get glossis current data"""

        request = {
            "dataset": "currents"
        }
        resp = self.client.post(
            '/get_glossis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result['function'] == 'magnitude'
        assert result['band'] == None
        assert result['dataset'] == "currents"

    def test_get_glossis_data_by_id(self):
        """test get glossis current data"""

        image_id = "projects/dgds-gee/glossis/wind/glossis_wind_20200301000000"
        request = {
            "imageId": image_id
        }
        resp = self.client.post(
            '/get_glossis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'function' in result
        assert result['band'] == None
        assert result['imageId'] == image_id

    def test_get_glossis_data_with_wrong_date(self):
        """test get glossis current data"""

        request = {
            "dataset": "waterlevel",
            "band": "water_level",
            "startDate": "2018-06-18T22:00:00"
        }
        resp = self.client.post(
            '/get_glossis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 400

    def test_get_gloffis_data(self):
        """test get gloffis weather data"""

        request = {
            "dataset": "weather",
            "band": "mean_temperature"
        }
        resp = self.client.post(
            '/get_gloffis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'url' in result
        assert 'band' in result
        assert 'imageId' in result
        assert result['min'] == -50
        assert result['max'] == 50

    def test_get_gloffis_data_log(self):
        """test get gloffis hydro data"""

        request = {
            "dataset": "hydro",
            "band": "discharge_routed_simulated"
        }
        resp = self.client.post(
            '/get_gloffis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'url' in result
        assert 'band' in result
        assert 'function' in result
        assert 'imageId' in result
        assert result['min'] == 1.0
        assert result['max'] == 1000000.0

    def test_get_crucial_data(self):
        """test get crucial data"""

        request = {
            "dataset": "groundwater_declining_trend",
            "band": "b1"
        }
        resp = self.client.post(
            '/get_crucial_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

    def test_get_msfd_data(self):
        """test get msfd data"""

        request = {
            "dataset": "chlorophyll",
            "band": "b1"
        }
        resp = self.client.post(
            '/get_msfd_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)


    def test_get_metocean_data(self):
        """test get metocean percentile data"""

        request = {
            "dataset": "percentiles",
            "band": "50th"
        }
        resp = self.client.post(
            '/get_metocean_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'url' in result
        assert result['imageId'] == 'projects/dgds-gee/metocean/waves/percentiles'
        assert 'function' not in result

    def test_get_gebco_data(self):
        """test get gebco data"""

        request = {
            "dataset": "gebco"
        }
        resp = self.client.post(
            '/get_gebco_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result['band'] == 'elevation'
        assert 'function' not in result


    def test_get_gll_dtm_data(self):
        """test get gll_dtm data"""

        request = {"dataset": "gll_dtm"}
        resp = self.client.post(
            "/get_gll_dtm_data",
            data=json.dumps(request),
            content_type="application/json",
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result["band"] == "elevation"
        assert "function" not in result

    def test_get_feature_info_null(self):
        request = {
            "imageId": "projects/dgds-gee/gloffis/hydro/gloffis_hydro_20200120000000",
            "band": "discharge_routed_simulated",
            "function": "log",
            "bbox": {
                "type": "Point",
                "coordinates": [
                    -28.23,
                    49.05
                ]
            }
        }
        resp = self.client.post(
            '/get_feature_info',
            data=json.dumps(request),
            content_type='application/json'
        )
        print(resp)
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result['value'] is None

    def test_get_feature_info(self):
        request = {
            "imageId": "projects/dgds-gee/metocean/waves/percentiles",
            "band": "50th",
            "bbox": {
                "type": "Point",
                "coordinates": [
                    -28.23,
                    49.05
                ]
            }
        }
        resp = self.client.post(
            '/get_feature_info',
            data=json.dumps(request),
            content_type='application/json'
        )
        print(resp)
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result['value'] == 3.02

    def test_get_feature_info_elevation(self):
        request = {
            "imageId": None,
            "datasets": [
                "GEBCO",
                "ALOS",
                "USGSNED",
                "GLDEM",
                "CADEM",
                "AHN2",
                "AUDEM",
                "REMA",
                "EMODnet"
            ],
            "function": "mosaic_elevation_datasets",
            "bbox": {
                "type": "Point",
                "coordinates": [
                    -28.23,
                    49.05
                ]
            }
        }
        resp = self.client.post(
            '/get_feature_info',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert result['value'] == -3712.95
    
    def test_get_task_status_task_id_na(self):
        task_id = 'some_id'

        with self.client as c:
            res = c.get(
                '/get_task_status',
                query_string={'task_id': task_id}
            )
        assert res.status_code == 200
        result = res.data.decode("UTF-8")

        assert result == 'UNKNOWN'

    def test_get_task_status_task_id_exists(self):
        simpleImage = ee.Image(1)
        task: ee.batch.Task = ee.batch.Export.image.toCloudStorage(
            simpleImage,
            description="testExportImageGCS",
            bucket=TEST_BUCKET,
            fileNamePrefix=f"{TEST_SUBFODLER}/test",
            region=TEST_REGION,
            scale=30,
            crs="EPSG:4326"
        )
        task.start()

        with self.client as c:
            res = c.get(
                '/get_task_status',
                query_string={'task_id': task.id}
            )
            
        assert res.status_code == 200
        result = res.data.decode("UTF-8")

        assert result != 'UNKNOWN'

    def test_get_task_status_operation_name_na(self):
        operation_name = 'projects/myproject/operations/myoperation'

        with self.client as c:
            res = c.get(
                '/get_task_status',
                query_string={'operation_name': operation_name}
            )
        assert res.status_code == 400
        result = res.data.decode("UTF-8")
        assert result == 'Resource projects/myproject could not be found.'
    
    def test_get_task_output(self):
        simpleImage = ee.Image(1)
        task: ee.batch.Task = ee.batch.Export.image.toCloudStorage(
            simpleImage,
            description="testExportImageGCS",
            bucket=TEST_BUCKET,
            fileNamePrefix=f"{TEST_SUBFODLER}/test",
            region=TEST_REGION,
            scale=30,
            crs="EPSG:4326"
        )
        task.start()
        
        max_wait_time = 180
        start = time.time()
        t = 0
        while t < max_wait_time:
            with self.client as c:
                res = c.get(
                    '/get_task_status',
                    query_string={'task_id': task.id}
                )
            result = res.data.decode("UTF8")
            if result == "COMPLETED":
                break
            time.sleep(10)
            t = time.time() - start
        
        with self.client as c:
            res = c.get(
                '/get_task_output',
                query_string={'task_id': task.id}
            )
            
        assert res.status_code == 200
        result = res.data.decode("UTF-8")
        assert json.loads(result)["uris"][0] == "https://console.developers.google.com/storage/browser/hydro-engine-public/test/"
