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
        # if 'privatekey.json' is defined in environmental variable - write it to file
        if 'key' in os.environ:
            print('Writing privatekey.json from environmental variable ...')
            content = base64.b64decode(os.environ['key']).decode('ascii')

            with open('../privatekey.json', 'w') as f:
                f.write(content)

        main.app.testing = True
        self.client = main.app.test_client()

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
            "start": "2010-01-01",
            "stop": "2016-01-01",
            "scale": 10,
            "crs": "EPSG:3857"
        }'''

        r = self.client.post('/get_water_mask', data=request,
                             content_type='application/json')

        assert r.status_code == 200

        print(r.data)

    def test_get_water_network(self):
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
            "start": "2010-01-01",
            "stop": "2016-01-01",
            "scale": 8,
            "crs": "EPSG:3857"
        }'''

        r = self.client.post('/get_water_network', data=request,
                             content_type='application/json')

        assert r.status_code == 200

        print(r.data)

    def test_get_water_network_properties(self):
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
            "start": "2010-01-01",
            "stop": "2016-01-01",
            "scale": 8,
            "crs": "EPSG:3857",
            "step": 100
        }'''

        r = self.client.post('/get_water_network_properties',
                             data=request,
                             content_type='application/json')

        assert r.status_code == 200

        print(r.data)


if __name__ == '__main__':
    unittest.main()
