#!/usr/bin/env python

import socket
import fcntl
import struct
import sys


s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


def get_ip_address(iface):
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	return socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', iface[:15]))[20:24])

"""
	0x8915 --> SIOCGIFADDR
    Get or set the address of the device using ifr_addr. Setting the interface address is a privileged operation.
    For compatibility, only AF_INET addresses are accepted or returned.
"""


try:
	s.bind((get_ip_address('eth0'), int(5000)))
	print('Bind DONE: ' + get_ip_address('eth0'))
except socket.error as err:
	print('Binding locally FAILED with Error Code ' + str(err[0]) + ' : ' + str(err[1]))
	sys.exit()

s.listen(10)
conn, addr = s.accept()
print('Received incoming connection from ' + str(addr))

while True:
	data = conn.recv(1024)
	if not data:
		break
	conn.send('This is PC 1! You penetrated the NAT network!')

conn.close()
s.close()