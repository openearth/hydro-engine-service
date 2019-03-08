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

        r = self.client.get('/get_bathymetry', data=json.dumps(input),
                            content_type='application/json')

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

        assert result['palette'] == palette

    def test_get_bathymetry_kustlidar(self):
        input = {
            "dataset": "kustlidar",
            "end_date": "2018-01-01",
            "begin_date": "2001-01-01"
        }

        r = self.client.get('/get_bathymetry', data=json.dumps(input),
                            content_type='application/json')

        assert r.status_code == 200

        result = json.loads(r.data)

        assert 'mapid' in result

    def test_get_raster_profile(self):
        line = '''{
        "dataset": "bathymetry_jetski",
        "begin_date": "2011-08-02",
        "end_date": "2011-09-02",
        "polyline": {
              "geodesic": true,
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
        }'''

        r = self.client.post('/get_raster_profile', data=line,
                             content_type='application/json')
        assert r.status_code == 200

    def test_get_catchments(self):
        request = '''{
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "dissolve": true,
            "catchment_level": 6,
            "region_filter": ""
        }'''

        r = self.client.post('/get_catchments', data=request,
                             content_type='application/json')
        assert r.status_code == 200

    def test_get_rivers(self):
        request = '''{
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "filter_upstream_gt": 1000,
            "catchment_level": 6,
            "region_filter": ""
        }'''

        r = self.client.post('/get_rivers', data=request,
                             content_type='application/json')
        assert r.status_code == 200

    def test_get_lakes(self):
        request = '''{
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "id_only": false
        }'''

        r = self.client.post('/get_lakes', data=request,
                             content_type='application/json')

        print('LAKES: ')

        assert r.status_code == 200

    def test_get_water_mask(self):
        request = '''{
            "region": {
                "geodesic": false,
                "type": "Polygon",
                "coordinates": [[
                    [5.986862182617186, 52.517369933821186],
                    [6.030635833740234, 52.517369933821186],
                    [6.030635833740234, 52.535439735112924],
                    [5.986862182617186, 52.535439735112924],
                    [5.986862182617186, 52.517369933821186]
                ]]
            },
            "use_url": false,
            "start": "2013-01-01",
            "stop": "2015-01-01",
            "scale": 30,
            "crs": "EPSG:3857"
        }'''

        r = self.client.post('/get_water_mask', data=request,
                             content_type='application/json')

        assert r.status_code == 200

    def test_get_sea_surface_height_time_series(self):
        """test sea surface height timeseries"""
        request = '''{
        "region": {"type": "Point", "coordinates": [54.0, 0.0]}
        }
        '''

        r = self.client.post(
            '/get_sea_surface_height_time_series',
            data=request,
            content_type='application/json'
        )
        assert r.status_code == 200

    def test_get_liwo_scenarios_max(self):
        """test get liwo scenarios max"""
        request = '''{
            "variable": "liwo",
            "breach_name": "Afvoergolf",
            "band_filter": "waterdepth",
            "region":{
                "geodesic": false,
                "type": "Polygon",
                "coordinates": [[
                    [6.0161056877902865,51.41901371286102],
                    [6.2495651604465365,51.417729076754576],
                    [6.245101964645755,51.54985700463136],
                    [6.0174789788059115,51.54836255319905],
                    [6.0161056877902865,51.41901371286102]
                ]]
            },
            "scale": 30,
            "crs": "EPSG:28992"
        }'''
        resp = self.client.post(
            '/get_liwo_scenarios_max',
            data=request,
            content_type='application/json'
        )
        print('code:', resp.status_code)
        assert resp.status_code == 200

        result = json.loads(resp.data)

        assert 'mapid' in result

if __name__ == '__main__':
    unittest.main()
