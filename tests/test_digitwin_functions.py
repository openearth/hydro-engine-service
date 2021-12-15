import json
import logging
import os
from pathlib import Path
import unittest

import ee

from . import auth

from hydroengine_service import config
from hydroengine_service.digitwin_functions import submit_ecopath_jobs


logger = logging.getLogger(__name__)

config.EE_PRIVATE_KEY_FILE = os.environ.get('key_path') or str(Path(__file__).parent.parent / "privatekey.json")
EE_CREDENTIALS = ee.ServiceAccountCredentials(config.EE_ACCOUNT,
                                              config.EE_PRIVATE_KEY_FILE)

ee.Initialize(EE_CREDENTIALS, opt_url="https://earthengine-highvolume.googleapis.com")

class TestClient(unittest.TestCase):
    def test_ecopath_exports(self):
        tasks = submit_ecopath_jobs(30000, "EPSG:3035", "HYCOM", "2020-07-01", 2)
        assert type(tasks[0]) == ee.batch.Task
        assert tasks[0].id is not None  # make sure task is started