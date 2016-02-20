#!/usr/bin/env python

import socket
import sys
import subprocess
import struct
import fcntl
from netaddr import *
from pyroute2 import iproute
from contextlib import contextmanager, closing

ipa = sys.argv[1]
dev = sys.argv[2]

private_networks = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']


# get local IP address of TUN
def get_ip_address(iface):

	from socket import socket, AF_INET, SOCK_STREAM, inet_ntoa

	""" 0x8915 --> SIOCGIFADDR
        Get or set the address of the device using ifr_addr. Setting the interface address is a privileged operation.
        For compatibility, only AF_INET addresses are accepted or returned. """

	sock = socket(AF_INET, SOCK_STREAM)
	return inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', iface[:15]))[20:24])


# check whether host belongs to a private network
def check_private_host(private_ip):

	''' * call routing_conf inside
		  check_private_host function instead ? '''

	for cidr in private_networks:
		if IPAddress(str(private_ip)) in IPNetwork(str(cidr)):
			return cidr
		else:
			continue
	pass


# configure separate ip rules/tables
def routing_conf():

	table_id = int(str(dev)[-1]) + 1  # table_id based on ppp interface int

	''' * more functionality
		* ensure table_id is unique for every virtual interface --> DONE
		* what about the netmask? Fixed? --> DONE
		* check for duplicates
		* add function to remove ip rules when virtual interfaces go down '''

	# virt_net = check_private_host(get_ip_address(dev))  # Virtual-NAT Network

	handler = iproute.IPRoute()
	index = handler.link_lookup(ifname=str(dev))[0]
	VpnClient = (handler.get_addr(match=lambda x: x['index'] == int(index)))[0]['attrs'][0][1]

	add_ip_rule = subprocess.Popen('ip rule add from ' + str(get_ip_address(dev)) + ' table ' + str(table_id),
	                               shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE).communicate()[0]
	add_ip_route = subprocess.Popen('ip route add default scope global via ' + str(VpnClient) + ' dev ' + str(dev) +
	                                ' table ' + str(table_id), shell=True, stdout=subprocess.PIPE,
	                                stdin=subprocess.PIPE).communicate()[0]
	return

routing_conf()


# monkey patch socket to BINDTODEVICE
@contextmanager
def bind_device(dev):

	import socket
	_socket = socket.socket

	class Socket(_socket):
		def __init__(self, *args, **kwargs):
			super(Socket, self).__init__()
			self.setsockopt(socket.SOL_SOCKET, 25, dev)  # define SO_BINDTODEVICE 25

		'''
		def __enter__(self):
			socket.socket = Socket
			return

		def __exit__(self, exc_type, exc_val, exc_tb):
			self.close()
		'''

		def unbind(self, *args, **kwargs):
			self.close()

	try:
		socket.socket = Socket
		# s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		yield socket.socket  # s
	finally:
		if not socket._closedsocket:
			Socket.unbind()
		# s.close()
		# e = socket.socket
		# e.unbind()

with bind_device(dev):  # as s:
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	print('Bind DONE: ' + str(dev))
	s.connect((ipa, 5000))
	print('Connected to: ' + str(ipa))
	s.send('Made it to the NAT network!')
	data = s.recv(1024)
	s.close()
	print(repr(data))