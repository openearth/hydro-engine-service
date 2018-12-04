import os
import json
import unittest
import logging

os.environ['key_path'] = '../privatekey.json'

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

    def test_get_raster(self):
        r = self.client.get('/')
        assert r.status_code == 200

        # r = client.get('/get_catchments')
        # assert r.status_code == 200
        # assert 'Welcome' in r.data.decode('utf-8')

    def test_get_feature_collection(self):
        request = '''{
            "region":
                {"type": "Polygon", "coordinates":
                    [[[5.995833, 4.387513999999975], [7.704733999999998, 4.387513999999975],
                      [7.704733999999998, 7.925567000000025], [5.995833, 7.925567000000025],
                      [5.995833, 4.387513999999975]]]},
            "asset": "users/gena/HydroEngine/riv_15s_lev06"
        }'''

        r = self.client.get('/get_feature_collection', data=request,
                            content_type='application/json')

        assert r.status_code == 200


# class TestPalettes(unittest.TestCase):
#    def test_cpt(self):
#        palette = palettes.pycpt2gee()
#        assert palette.endswith('faffff')


if __name__ == '__main__':
    unittest.main()
