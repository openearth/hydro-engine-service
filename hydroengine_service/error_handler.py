'''Application error handlers.'''
from flask import Blueprint, jsonify

import traceback

error_handler = Blueprint('errors', __name__)

class InvalidUsage(Exception):
    """raise this error invalid input is specified"""
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv

@error_handler.app_errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

@error_handler.app_errorhandler(Exception)
def handle_unexpected_error(error):
    stack = traceback.format_exc()

    status_code = 500
    success = False
    response = {
        'success': success,
        'error': {
            'type': 'UnexpectedException',
            'message': str(error),
            'stack': stack
        }
    }

    return jsonify(response), status_code
