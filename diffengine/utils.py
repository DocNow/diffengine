import os
import yaml


def generate_config(home, content):
    config_file = os.path.join(home, "config.yaml")

    if not os.path.isdir(home):
        os.makedirs(home)

    yaml.dump(content, open(config_file, "w"), default_flow_style=False)
