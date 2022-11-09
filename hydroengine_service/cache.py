"""This module provides a global available cache. It can be used for services. It should be initalized with the flask application"""
import ee

from flask_caching import Cache

cache = Cache()


def cache_image(image):
    """store the json version of the DAG in the cache"""
    mapid = image.getMapId()["mapid"]
    serialized = ee.data.serializer.toJSON(image)
    # store the dag in the cache
    cache.set(mapid, serialized)
    return mapid

def image_from_cache(mapid):
    """get an image based on the DAG stored in the cache"""
    serialized = cache.get(mapid)
    deserialized = ee.deserializer.fromJSON(serialized)
    return deserialized
