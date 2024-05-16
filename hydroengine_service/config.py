import pathlib
import json
import logging

APP_DIR = pathlib.Path(__file__).parent.resolve()

"""Required credentials configuration."""
EE_ACCOUNT = (
    "578920177147-ul189ho0h6f559k074lrodsd7i7b84rc@developer.gserviceaccount.com"
)
EE_PRIVATE_KEY_FILE = str(APP_DIR.parent / "privatekey.json")
if not pathlib.Path(EE_PRIVATE_KEY_FILE).exists():
    print(f"Can't find PK in {APP_DIR}")
else:
    print(f"Found PK at {EE_PRIVATE_KEY_FILE}")

DATASET_DIR = APP_DIR / "datasets"
DATASET_PATH = DATASET_DIR / "dataset_visualization_parameters.json"

# load visualization parameters
with DATASET_PATH.open() as json_file:
    DATASETS_VIS = json.load(json_file)
