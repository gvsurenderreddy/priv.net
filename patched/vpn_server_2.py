#!/usr/bin/env python

import socket
import sys
from netaddr import *
import config


# check whether host belongs to a private network
def check_private_host(addr):

	for cidr in config.NETWORK_CONNECT_PRIVATE:
		if IPAddress(str(addr)) in IPNetwork(str(cidr)):
			return True
		else:
			continue
	return False


# monkey patch socket to BINDTODEVICE
def bind_device(ip, iface=''):

	_socket = socket.socket

	class Socket(_socket):

		def __init__(self, *args, **kwargs):
			super(Socket, self).__init__(*args, **kwargs)
			self.iface = iface
			if not check_private_host(ip):
				pass
			else:
				print('NOTICE: Private host detected! Attempting connection ...')
				if self.iface == '':
					self.iface = raw_input('Provide outgoing interface: ')
				self.setsockopt(socket.SOL_SOCKET, 25, self.iface)  # define SO_BINDTODEVICE 25

	return Socket

ipa = sys.argv[1]
dev = sys.argv[2] if len(sys.argv) > 2 else ''

socket.socket = bind_device(ipa, dev)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
print('\tBinding locally ... ')
s.connect((ipa, 5000))
print('\tConnected to: ' + str(ipa))
s.send('Made it to the NAT network!')
data = s.recv(1024)
s.close()
print('=======>' + str(data))

'''
req = requests.get('http://' + str(ipa))
print(req.text)
'''