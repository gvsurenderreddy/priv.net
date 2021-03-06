"""Routes and wsgi app creation"""

import yaml
import os
import json
import requests
import socket
from netaddr import IPAddress, IPNetwork

from pyramid.config import Configurator
from pyramid.renderers import JSON

from mist.io.resources import Root
from mist.io import config

import logging

logging.basicConfig(level=config.PY_LOG_LEVEL,
                    format=config.PY_LOG_FORMAT,
                    datefmt=config.PY_LOG_FORMAT_DATE)
log = logging.getLogger(__name__)

# check whether host belongs to a private network
def check_private_host(dst):
   for cidr in config.NETWORK_CONNECT_PRIVATE:
       if IPAddress(str(dst)) in IPNetwork(str(cidr)):
           return True
       else:
           continue
   return False

# monkey patch socket to BINDTODEVICE
def bind_device(assocs):
    _socket = socket.socket

    class Socket(_socket):

        def connect(self, *args, **kwargs):
            addr, port = args[0]  # destination (IP, PORT)
            priv = check_private_host(socket.gethostbyname(addr))
            if not priv:
                pass
            else:
                iface = assocs[0]
                # define SO_BINDTODEVICE 25
                self.setsockopt(socket.SOL_SOCKET, 25, iface)

            super(Socket, self).connect(*args, **kwargs)

    return Socket


socket.socket = bind_device(config.VIRTUAL_INTERFACES)


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""
    if not settings.keys():
        settings = global_config

    settings = {}
    from mist.io.model import User

    # migrate settings.yaml to db.yaml
    try:
        with open('settings.yaml', 'r') as config_file:
            log.info("Found settings.yaml, migrating...")
            data = config_file.read()
            with open('db.yaml', 'w') as db_file:
                db_file.write(data)
        os.rename('settings.yaml', 'settings.yaml.backup')
        user = User()
        with user.lock_n_load():
            for key in ['core_uri', 'js_build', 'js_log_level']:
                if key in user._dict:
                    del user._dict[key]
            user.save()

        from mist.io.model import Machine
        with user.lock_n_load():
            for cloud in user.clouds.values():
                if 'list_of_machines' in cloud._dict:
                    list_of_machines = cloud._dict['list_of_machines']
                    for old_machine in list_of_machines:
                        machine_id = old_machine.get('id')
                        machine_hostname = old_machine.get('hostname')
                        print ("Migrating %s(%s) for user %s" %
                               (machine_id, machine_hostname, user.email))
                        if not machine_id or not machine_hostname:
                            print " *** ERROR MIGRATING, SKIPPING *** "
                            continue
                        if machine_id not in cloud.machines:
                            cloud.machines[machine_id] = Machine()
                        machine = cloud.machines[machine_id]
                        machine.dns_name = machine_hostname
                        machine.public_ips.append(machine_hostname)
                        machine.name = machine_hostname
                    del cloud._dict['list_of_machines']
            user.save()
    except IOError as exc:
        # settings.yaml doesn't exist, continue
        pass

    configurator = Configurator(root_factory=Root, settings=settings)

    # Add custom adapter to the JSON renderer to avoid serialization errors
    json_renderer = JSON()

    def string_adapter(obj, request):
        return str(obj)

    json_renderer.add_adapter(object, string_adapter)
    configurator.add_renderer('json', json_renderer)
    configurator.add_static_view('resources', 'mist.io:static')
    configurator.add_static_view('docs', path='../../../docs/build')
    configurator.include(add_routes)
    configurator.scan()
    app = configurator.make_wsgi_app()

    return app


def add_routes(configurator):
    """This function defines pyramid routes.

    Takes a Configurator instance as argument and changes it's configuration.
    Any return value is ignored. This was put in a separate function so that it
    can easily be imported and extended upon.
    Just use: config.include(add_routes)

    """

    configurator.add_route('home', '/')
    configurator.add_route('api_v1_providers', '/api/v1/providers')
    configurator.add_route('providers', '/providers')
    configurator.add_route('api_v1_clouds', '/api/v1/clouds')
    configurator.add_route('clouds', '/clouds')
    configurator.add_route('api_v1_cloud_action', '/api/v1/clouds/{cloud}')
    configurator.add_route('cloud_action', '/clouds/{cloud}')

    configurator.add_route('api_v1_machines', '/api/v1/clouds/{cloud}/machines')
    configurator.add_route('machines', '/clouds/{cloud}/machines')
    configurator.add_route('api_v1_machine', '/api/v1/clouds/{cloud}/machines/{machine}')
    configurator.add_route('machine', '/clouds/{cloud}/machines/{machine}')
    configurator.add_route('api_v1_machine_rdp', '/api/v1/clouds/{cloud}/machines/{machine}/rdp')
    configurator.add_route('machine_rdp', '/clouds/{cloud}/machines/{machine}/rdp')
    configurator.add_route('api_v1_machine_tags', '/api/v1/clouds/{cloud}/machines/{machine}/tags')
    configurator.add_route('machine_tags', '/clouds/{cloud}/machines/{machine}/tags')
    configurator.add_route('api_v1_machine_tag', '/api/v1/clouds/{cloud}/machines/{machine}/tags/{tag}')
    configurator.add_route('machine_tag', '/clouds/{cloud}/machines/{machine}/tags/{tag}')
    configurator.add_route('api_v1_probe', '/api/v1/clouds/{cloud}/machines/{machine}/probe')
    configurator.add_route('probe', '/clouds/{cloud}/machines/{machine}/probe')

    configurator.add_route('api_v1_monitoring', '/api/v1/monitoring')
    configurator.add_route('monitoring', '/monitoring')
    configurator.add_route('api_v1_update_monitoring', '/api/v1/clouds/{cloud}/machines/{machine}/monitoring')
    configurator.add_route('update_monitoring', '/clouds/{cloud}/machines/{machine}/monitoring')
    configurator.add_route('api_v1_stats', '/api/v1/clouds/{cloud}/machines/{machine}/stats')
    configurator.add_route('stats', '/clouds/{cloud}/machines/{machine}/stats')
    configurator.add_route('api_v1_metrics', '/api/v1/clouds/{cloud}/machines/{machine}/metrics')
    configurator.add_route('metrics', '/clouds/{cloud}/machines/{machine}/metrics')
    configurator.add_route('api_v1_metric', '/api/v1/metrics/{metric}')
    configurator.add_route('metric', '/metrics/{metric}')
    configurator.add_route('api_v1_deploy_plugin', '/api/v1/clouds/{cloud}/machines/{machine}/plugins/{plugin}')
    configurator.add_route('deploy_plugin', '/clouds/{cloud}/machines/{machine}/plugins/{plugin}')

    configurator.add_route('api_v1_images', '/api/v1/clouds/{cloud}/images')
    configurator.add_route('images', '/clouds/{cloud}/images')
    configurator.add_route('api_v1_image', '/api/v1/clouds/{cloud}/images/{image:.*}')
    configurator.add_route('image', '/clouds/{cloud}/images/{image:.*}')
    configurator.add_route('api_v1_sizes', '/api/v1/clouds/{cloud}/sizes')
    configurator.add_route('sizes', '/clouds/{cloud}/sizes')
    configurator.add_route('api_v1_locations', '/api/v1/clouds/{cloud}/locations')
    configurator.add_route('locations', '/clouds/{cloud}/locations')
    configurator.add_route('api_v1_networks', '/api/v1/clouds/{cloud}/networks')
    configurator.add_route('networks', '/clouds/{cloud}/networks')
    configurator.add_route('api_v1_network', '/api/v1/clouds/{cloud}/networks/{network}')
    configurator.add_route('network', '/clouds/{cloud}/networks/{network}')

    configurator.add_route('api_v1_keys', '/api/v1/keys')
    configurator.add_route('keys', '/keys')
    configurator.add_route('api_v1_key_action', '/api/v1/keys/{key}')
    configurator.add_route('key_action', '/keys/{key}')
    configurator.add_route('api_v1_key_public', '/api/v1/keys/{key}/public')
    configurator.add_route('key_public', '/keys/{key}/public')
    configurator.add_route('api_v1_key_private', '/api/v1/keys/{key}/private')
    configurator.add_route('key_private', '/keys/{key}/private')
    configurator.add_route('api_v1_key_association', '/api/v1/clouds/{cloud}/machines/{machine}/keys/{key}')
    configurator.add_route('key_association', '/clouds/{cloud}/machines/{machine}/keys/{key}')

    configurator.add_route('api_v1_rules', '/api/v1/rules')
    configurator.add_route('rules', '/rules')
    configurator.add_route('api_v1_rule', '/api/v1/rules/{rule}')
    configurator.add_route('rule', '/rules/{rule}')
    configurator.add_route('api_v1_check_auth', '/api/v1/auth')
    configurator.add_route('check_auth', '/auth')
    configurator.add_route('account', '/account')
