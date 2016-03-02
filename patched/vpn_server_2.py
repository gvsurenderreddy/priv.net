#!/usr/bin/env python

import socket
import requests
from netaddr import *
import config

# destination testing
destinations = {'PC 1': '10.0.1.6', 'Google': 'google.com', 'PC 1 again': '10.0.1.6', 'Google once more': 'google.com'}
# associating private networks with the corresponding virtual interface
virt_devices = {'10.0.0.0/8': 'ppp0'}


# check whether host belongs to a private network
def check_private_host(dst):
	for cidr in config.NETWORK_CONNECT_PRIVATE:
		if IPAddress(str(dst)) in IPNetwork(str(cidr)):
			return cidr
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
				print('NOTICE: Private host detected. Attempting connection ...')
				for key, value in assocs.iteritems():
					if key == priv:
						iface = assocs[key]
						self.setsockopt(socket.SOL_SOCKET, 25, iface)  # define SO_BINDTODEVICE 25

			super(Socket, self).connect(*args, **kwargs)

	return Socket

socket.socket = bind_device(virt_devices)

for host, ip in destinations.iteritems():
	print('Poking ' + str(host) + ' ...')
	url = 'http://' + str(destinations[host])
	req = requests.get(url, timeout=2)
	if req and str(host)[:6] == 'Google':
		print('Google responded OK\n')
	else:
		print(req.text + '\n')