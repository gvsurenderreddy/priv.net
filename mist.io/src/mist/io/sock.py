"""mist.io.socket

Here we define the socketio Connection and handlers.

When a user loads mist.io or comes back online, their browser will request a
new socket and the initialize function will be triggered on the server within a
greenlet.

"""

import uuid
import json
import socket
import random
import traceback
import datetime
from time import time

from sockjs.tornado import SockJSConnection, SockJSRouter
from mist.io.sockjs_mux import MultiplexConnection
import tornado.iostream

import requests

try:
    from mist.core.auth.methods import user_from_session_id
    from mist.core import config
    from mist.core.methods import get_stats
    multi_user = True
except ImportError:
    from mist.io.helpers import user_from_session_id
    from mist.io import config
    from mist.io.methods import get_stats
    multi_user = False

from mist.io.helpers import amqp_subscribe_user
from mist.io.methods import notify_user
from mist.io.exceptions import MachineUnauthorizedError
from mist.io.exceptions import BadRequestError
from mist.io.amqp_tornado import Consumer

from mist.io import methods
from mist.io import tasks
from mist.io.shell import Shell
from mist.io.hub.tornado_shell_client import ShellHubClient

import logging
logging.basicConfig(level=config.PY_LOG_LEVEL,
                    format=config.PY_LOG_FORMAT,
                    datefmt=config.PY_LOG_FORMAT_DATE)
log = logging.getLogger(__name__)


# hold all open connections to properly clean them up in case of SIGTERM
CONNECTIONS = set()


def get_conn_info(conn_info):
    real_ip = forwarded_for = user_agent = ''
    for header in conn_info.headers:
        if header.lower() == 'x-real-ip':
            real_ip = conn_info.headers[header]
        elif header.lower() == 'x-forwarded-for':
            forwarded_for = conn_info.headers[header]
        elif header.lower() == 'user-agent':
            user_agent = conn_info.headers[header]
    ip = real_ip or forwarded_for or conn_info.ip
    session_id = ''
    if 'session.id' in conn_info.cookies.keys():
        session_id = conn_info.cookies['session.id'].value
    return ip, user_agent, session_id


def mist_conn_str(conn_dict):
    parts = []
    dt_last_rcv = datetime.datetime.fromtimestamp(conn_dict['last_rcv'])
    conn_dict['last_rcv'] = dt_last_rcv
    for key in ('name', 'last_rcv', 'user', 'ip', 'user_agent', 'closed',
                'session_id'):
        if key in conn_dict:
            parts.append(conn_dict.pop(key))
    parts.extend(conn_dict.values())
    return ' - '.join(map(str, parts))


class MistConnection(SockJSConnection):
    closed = False

    def on_open(self, conn_info):
        log.info("%s: Initializing", self.__class__.__name__)
        self.ip, self.user_agent, session_id = get_conn_info(conn_info)
        self.user = user_from_session_id(session_id)
        self.session_id = uuid.uuid4().hex
        CONNECTIONS.add(self)

    def send(self, msg, data=None):
        super(MistConnection, self).send(json.dumps({msg: data}))

    def on_close(self, stale=False):
        if not self.closed:
            log.info("%s: on_close event handler", self.__class__.__name__)
            if stale:
                log.warning("stale conn removed")
            CONNECTIONS.remove(self)
            self.closed = True
        else:
            log.warning("%s: called on_close AGAIN!", self.__class__.__name__)
            traceback.print_stack()

    def get_dict(self):
        return {
            'name': self.session.name,
            'last_rcv': self.session.base.last_rcv,
            'user': self.user.email,
            'ip': self.ip,
            'user_agent': self.user_agent,
            'closed': self.is_closed,
            'session_id': self.session_id,
        }

    def __repr__(self):
        return mist_conn_str(self.get_dict())


class ShellConnection(MistConnection):
    def on_open(self, conn_info):
        super(ShellConnection, self).on_open(conn_info)
        self.hub_client = None
        self.ssh_info = {}

    def on_shell_open(self, data):
        if self.ssh_info:
            self.close()
        self.ssh_info = {
            'cloud_id': data['cloud_id'],
            'machine_id': data['machine_id'],
            'host': data['host'],
            'columns': data['cols'],
            'rows': data['rows'],
            'ip': self.ip,
            'user_agent': self.user_agent,
            'email': self.user.email,
            'provider': data.get('provider', '')
        }
        self.hub_client = ShellHubClient(worker_kwargs=self.ssh_info)
        self.hub_client.on_data = self.emit_shell_data
        self.hub_client.start()
        log.info('on_shell_open finished')

    def on_shell_data(self, data):
        self.hub_client.send_data(data)

    def on_shell_resize(self, columns, rows):
        self.hub_client.resize(columns, rows)

    def emit_shell_data(self, data):
        self.send('shell_data', data)

    def on_close(self, stale=False):
        if self.hub_client:
            self.hub_client.stop()
        super(ShellConnection, self).on_close(stale=stale)


class UserUpdatesConsumer(Consumer):
    def __init__(self, main_sockjs_conn,
                 amqp_url=config.BROKER_URL):
        self.sockjs_conn = main_sockjs_conn
        email = self.sockjs_conn.user.email or 'noone'
        super(UserUpdatesConsumer, self).__init__(
            amqp_url=amqp_url,
            exchange='mist-user_%s' % email.replace('@', ':'),
            queue='mist-socket-%d' % random.randrange(2 ** 20),
            exchange_type='fanout',
            exchange_kwargs={'auto_delete': True},
            queue_kwargs={'auto_delete': True, 'exclusive': True},
        )

    def on_message(self, unused_channel, basic_deliver, properties, body):
        super(UserUpdatesConsumer, self).on_message(
            unused_channel, basic_deliver, properties, body
        )
        self.sockjs_conn.process_update(
            unused_channel, basic_deliver, properties, body
        )

    def start_consuming(self):
        super(UserUpdatesConsumer, self).start_consuming()
        self.sockjs_conn.start()


class MainConnection(MistConnection):
    def on_open(self, conn_info):
        super(MainConnection, self).on_open(conn_info)
        self.running_machines = set()
        self.consumer = None

    def on_ready(self):
        log.info("Ready to go!")
        if self.consumer is None:
            self.consumer = UserUpdatesConsumer(self)
            self.consumer.run()
        else:
            log.error("It seems we have received 'on_ready' more than once.")

    def start(self):
        self.list_keys()
        self.list_clouds()
        self.check_monitoring()

    def list_keys(self):
        self.send('list_keys', methods.list_keys(self.user))

    def list_clouds(self):
        clouds = methods.list_clouds(self.user)
        self.send('list_clouds', clouds)
        for key, task in (('list_machines', tasks.ListMachines()),
                          ('list_images', tasks.ListImages()),
                          ('list_sizes', tasks.ListSizes()),
                          ('list_networks', tasks.ListNetworks()),
                          ('list_locations', tasks.ListLocations()), ('list_projects', tasks.ListProjects()),):
            for cloud_id in self.user.clouds:
                if self.user.clouds[cloud_id].enabled:
                    cached = task.smart_delay(self.user.email, cloud_id)
                    if cached is not None:
                        log.info("Emitting %s from cache", key)
                        self.send(key, cached)

    def check_monitoring(self):
        try:
            from mist.core import methods as core_methods
            func = core_methods.check_monitoring
        except ImportError:
            func = methods.check_monitoring
        try:
            self.send('monitoring', func(self.user))
        except Exception as exc:
            log.warning("Check monitoring failed with: %r", exc)

    def on_stats(self, cloud_id, machine_id, start, stop, step, request_id,
                 metrics):
        error = False
        try:
            data = get_stats(self.user, cloud_id, machine_id,
                             start, stop, step)
        except BadRequestError as exc:
            error = str(exc)
            data = []
        except Exception as exc:
            log.error("Exception in get_stats: %r", exc)
            return

        ret = {
            'cloud_id': cloud_id,
            'machine_id': machine_id,
            'start': start,
            'stop': stop,
            'request_id': request_id,
            'metrics': data,
        }
        if error:
            ret['error'] = error
        self.send('stats', ret)

    def process_update(self, ch, method, properties, body):
        routing_key = method.routing_key
        try:
            result = json.loads(body)
        except:
            result = body
        log.info("Got %s", routing_key)
        if routing_key in set(['notify', 'probe', 'list_sizes', 'list_images',
                               'list_networks', 'list_machines',
                               'list_locations', 'list_projects', 'ping']):
            self.send(routing_key, result)
            if routing_key == 'probe':
                log.warn('send probe')

            if routing_key == 'list_networks':
                cloud_id = result['cloud_id']
                log.warn('Got networks from %s',
                         self.user.clouds[cloud_id].title)
            if routing_key == 'list_machines':
                # probe newly discovered running machines
                machines = result['machines']
                cloud_id = result['cloud_id']
                # update cloud machine count in multi-user setups
                try:
                    mcount = self.user.clouds[cloud_id].machine_count
                    if multi_user and len(machines) != mcount:
                        tasks.update_machine_count.delay(self.user.email,
                                                         cloud_id,
                                                         len(machines))
                except Exception as exc:
                    log.warning("Error while update_machine_count.delay: %r",
                                exc)
                for machine in machines:
                    bmid = (cloud_id, machine['id'])
                    if bmid in self.running_machines:
                        # machine was running
                        if machine['state'] != 'running':
                            # machine no longer running
                            self.running_machines.remove(bmid)
                        continue
                    if machine['state'] != 'running':
                        # machine not running
                        continue
                    # machine just started running
                    self.running_machines.add(bmid)
                    ips = filter(lambda ip: ':' not in ip,
                                 machine.get('public_ips', []))
                    if not ips:
                        continue

                    has_key = False
                    for k in self.user.keypairs.values():
                        for m in k.machines:
                            if m[:2] == [cloud_id, machine['id']]:
                                has_key = True
                                break
                        if has_key:
                            break

                    if has_key:
                        cached = tasks.ProbeSSH().smart_delay(
                            self.user.email, cloud_id, machine['id'], ips[0]
                        )
                        if cached is not None:
                            self.send('probe', cached)

                    cached = tasks.Ping().smart_delay(
                        self.user.email, cloud_id, machine['id'], ips[0]
                    )
                    if cached is not None:
                        self.send('ping', cached)

        elif routing_key == 'update':
            self.user.refresh()
            sections = result
            if 'clouds' in sections:
                self.list_clouds()
            if 'keys' in sections:
                self.list_keys()
            if 'monitoring' in sections:
                self.check_monitoring()

    def on_close(self, stale=False):
        if self.consumer is not None:
            try:
                self.consumer.stop()
            except Exception as exc:
                log.error("Error closing pika consumer: %r", exc)
        super(MainConnection, self).on_close(stale=stale)


def make_router():
    return SockJSRouter(
        MultiplexConnection.get(
            main=MainConnection,
            shell=ShellConnection,
        ),
        '/socket'
    )
