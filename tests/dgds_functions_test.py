import logging
import pytest

from . import auth

from hydroengine_service import dgds_functions

# import palettes

logger = logging.getLogger(__name__)

class TestDGDSFunctions:

    @pytest.mark.parametrize('source, start_date, end_date, limit',
                             [
                                 ('projects/dgds-gee/bathymetry/gebco/2019', None, None, 10),
                                 ('projects/dgds-gee/glossis/currents', None, None, None),
                                 ('projects/dgds-gee/glossis/waterlevel', '2019-12-01', None, None),
                                 ('projects/dgds-gee/glossis/wind', '2019-08-01', '2019-09-01', 10),
                                 ('projects/dgds-gee/glossis/waveheight', None, None, None),
                                 ('projects/dgds-gee/gloffis/weather', None, None, 5),
                                 ('projects/dgds-gee/gloffis/hydro', None, None, 5),
                                 ('projects/dgds-gee/metocean/waves/percentiles', None, None, 5)])
    def test_get_image_collection_info(self, source, start_date, end_date, limit):
        image_date_list = dgds_functions.get_image_collection_info(source, start_date, end_date, limit)

        assert len(image_date_list) >= 1

        assert "imageId" in image_date_list[0]

        assert "date" in image_date_list[0]

    # @pytest.mark.parametrize('image_id, type, band, function, min, max, palette',
    #                          [])
    # def test_get_wms_url(self):
    #     dgds_functions.get_wms_url(image_id, type='ImageCollection', band=None, function=None, min=None, max=None, palette=None):
