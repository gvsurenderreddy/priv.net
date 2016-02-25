#!/usr/bin/env python

import socket
import sys
from contextlib import contextmanager

ipa = sys.argv[1]
dev = sys.argv[2]


# monkey patch socket to BINDTODEVICE
@contextmanager
def bind_device(dev):

	_socket = socket.socket

	class Socket(_socket):
		def __init__(self, *args, **kwargs):
			super(Socket, self).__init__(*args, **kwargs)
			self.setsockopt(socket.SOL_SOCKET, 25, dev)  # define SO_BINDTODEVICE 25

		def unbind(self, *args, **kwargs):
			self.close()

	try:
		socket.socket = Socket
		yield socket.socket
	finally:
		if not socket._closedsocket:
			Socket.unbind()
		socket.socket = _socket

with bind_device(dev):
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	print('Bind DONE: ' + str(dev))
	s.connect((ipa, 5000))
	print('Connected to: ' + str(ipa))
	s.send('Made it to the NAT network!')
	data = s.recv(1024)
	s.close()
	print(repr(data))