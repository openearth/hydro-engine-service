import json
import unittest

from hydroengine_service import main


class TestClient(unittest.TestCase):
    # TODO: Mock EE client (this is now an integration test)
    # TODO: For integration test, only query tiny task
    def setUp(self):
        main.app.testing = True
        self.client = main.app.test_client()

    def test_submit_ecopath_job(self):
        with self.client as c:
            res = c.post("/start_water_velocity_jobs")
        
        assert res.status_code == 200

        result = json.loads(res.data.decode("UTF-8"))
        keys = list(result[0].keys())

        assert "task_id" in keys
        assert "description" in keys