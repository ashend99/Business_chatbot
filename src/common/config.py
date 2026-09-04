import os

from utils.config import get_config

def get_project_config():
    project_home = os.getenv("PROJECT_HOME", "")
    project_config_file = os.path.join(project_home, "project_config.yaml")
    return get_config(project_config_file)

PROJECT_CONFIG = get_project_config()