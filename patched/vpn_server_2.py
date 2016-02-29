#!/usr/bin/env python

import socket
import requests
import urlparse
from netaddr import *
from contextlib import contextmanager
import config

destinations = {'PC 1': '10.0.1.6', 'Google': 'google.com', 'PC 1 again': '10.0.1.6', 'Google once more': 'google.com'}
# associating private nodes with the corresponding virtual interface
virt_devices = {}


# check whether host belongs to a private network
def check_private_host(addr):

	for cidr in config.NETWORK_CONNECT_PRIVATE:
		if IPAddress(str(addr)) in IPNetwork(str(cidr)):
			return True
		else:
			continue
	return False


@contextmanager
def reset(sock):
	try:
		yield sock
	finally:
		sock.unbind()


# monkey patch socket to BINDTODEVICE
def bind_device(ip='', iface=''):

	_socket = socket.socket

	class Socket(_socket):

		global url

		def __init__(self, *args, **kwargs):
			self.iface = iface
			self.ip = ip
			self.url = url
			super(Socket, self).__init__(*args, **kwargs)
			with reset(self):
				self.bind()

		def bind(self):
			if self.url.split(':')[0] not in ['http', 'https']:
				self.url = 'http://' + self.url
			parser = urlparse.urlparse(self.url)
			self.ip = parser.hostname
			if not check_private_host(socket.gethostbyname(self.ip)):
				pass
			else:
				print('NOTICE: Private host detected! Attempting connection ...')
				self.iface = raw_input('Provide outgoing interface: ')
				self.setsockopt(socket.SOL_SOCKET, 25, self.iface)  # define SO_BINDTODEVICE 25

		def unbind(self):
			pass
			# socket.socket = Socket
			# return socket.socket

	return Socket

socket.socket = bind_device()

for host, addr in destinations.iteritems():
	print('Poking ' + str(host) + ' ...')
	url = 'http://' + str(destinations[host])
	req = requests.get(url, timeout=2)
	if req and str(host)[:6] == 'Google':
		print('Google responded OK')
	else:
		print(req.text)

url = '10.0.1.6'
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.settimeout(2)
try:
	print('\tBinding locally ... ')
	s.connect((url, 5000))
	print('\tConnected to: ' + str(url))
	s.send('Made it to the NAT network!')
	data = s.recv(1024)
	s.close()
	print('=======>' + str(data))
except socket.timeout:
	print('\tCould not connect. Moving on ...')