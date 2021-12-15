from typing import List

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import ee

from hydroengine_service.ecopath_functions import submit_ecopath_jobs

v1 = Blueprint("ecopath-v1", __name__)

@v1.route("/data", methods=["POST"])
@cross_origin()
def submit_ecopath_job():
    tasks: List[ee.batch.Task] = submit_ecopath_jobs()
    # Give back the task name plus id
    return jsonify([{
        "task_id": task.id,
        "description": task.config["description"]
    } for task in tasks])
