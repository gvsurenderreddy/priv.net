""" Basic configuration and mappings

Here we define constants needed by mist.io

Also, the configuration from settings.py is exposed through this module.

"""

import logging

# Parse user defined settings from settings.py in the top level project dir
log = logging.getLogger(__name__)
settings = {}

try:
    execfile("settings.py", settings)
except IOError:
    log.warning("No settings.py file found.")
except Exception as exc:
    log.error("Error parsing settings py: %r", exc)

# accessible private networks by mist.io
NETWORK_CONNECT_PRIVATE = settings.get('NETWORK_CONNECT_PRIVATE', '')  # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16