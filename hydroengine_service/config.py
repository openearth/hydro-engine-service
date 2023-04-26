import pathlib
import json
from dotenv import load_dotenv, find_dotenv

def load_env():
    load_dotenv(find_dotenv(), verbose=True)

"""Required credentials configuration."""
EE_ACCOUNT = '578920177147-ul189ho0h6f559k074lrodsd7i7b84rc@developer.gserviceaccount.com'
EE_PRIVATE_KEY_FILE = 'privatekey.json'

APP_DIR = pathlib.Path(__file__).parent
DATASET_DIR = APP_DIR / 'datasets'
DATASET_PATH = DATASET_DIR / 'dataset_visualization_parameters.json'

# load visualization parameters
with DATASET_PATH.open() as json_file:
    DATASETS_VIS = json.load(json_file)
