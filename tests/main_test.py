import os
import json
import unittest
import logging

from . import auth

from hydroengine_service import main

# import palettes

logger = logging.getLogger(__name__)


class TestClient(unittest.TestCase):
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
        assert resp.status_code == 200

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
        assert resp.status_code == 200

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

        assert 'mapid' in result
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

        assert 'mapid' in result
        assert result['dataset'] == "currents"

    def test_get_glossis_data_with_date(self):
        """test get glossis current data"""

        request = {
            "dataset": "wind",
            "date": "2019-08-08T00:00:00"
        }
        resp = self.client.post(
            '/get_glossis_data',
            data=json.dumps(request),
            content_type='application/json'
        )
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'mapid' in result
        assert result['date'] == "2019-08-08T00:00:00"

    def test_get_glossis_data_with_wrong_date(self):
        """test get glossis current data"""

        request = {
            "dataset": "waterlevel",
            "date": "2018-06-18T22:00:00"
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

        assert 'mapid' in result

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

        assert 'mapid' in result

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

        assert 'mapid' in result

if __name__ == '__main__':
    unittest.main()
