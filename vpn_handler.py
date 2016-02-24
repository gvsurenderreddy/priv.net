#!/usr/bin/env python

import socket
import subprocess
import struct
import fcntl
from pyroute2 import iproute
import gobject
import dbus
from dbus.mainloop.glib import DBusGMainLoop


def command(comm):

	cmd = subprocess.call(str(comm), shell=True)
	return cmd


# get local IP address of TUN
def get_ip_address(iface):

	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	return socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', iface[:15]))[20:24])


# configure separate ip rules/tables
def add_conf(dev):

	table_id = int(str(dev)[3:]) + 1  # table_id based on ppp interface int

	handler = iproute.IPRoute()
	index = handler.link_lookup(ifname=str(dev))[0]
	vpnclient = (handler.get_addr(match=lambda x: x['index'] == int(index)))[0]['attrs'][0][1]

	command('ip rule add from ' + str(get_ip_address(dev)) + ' table ' + str(table_id))
	command('ip route add default scope global via ' + str(vpnclient) + ' dev ' + str(dev) + ' table ' + str(table_id))
	return


def del_conf(dev):

	table_id = int(str(dev)[3:]) + 1  # table_id based on ppp interface int

	command('ip rule delete table ' + str(table_id))
	# command('ip route delete default scope global dev ' + str(dev) + ' table ' + str(table_id))
	return


def vpn_connection_handler(*args, **kwargs):

	# mod = str(kwargs['dbus_interface'] + "." + kwargs['member'])
	if kwargs['member'] == 'EventEmitted':
		# print "Event Emitted ----->        " + str(args)
		if args[1][0] == dbus.String(u'JOB=network-interface') and str(args[1][1])[:12] == 'INSTANCE=ppp':
			tun = str(args[1][1])[9:]
			if int(tun[3:]) in range(0, 90):
				if args[0] == dbus.String(u'starting'):
					print('====> VIRTUAL INTERFACE ' + str(tun) + ' STARTING ...')
				elif args[0] == dbus.String(u'started'):
					print('\t ... ' + str(tun) + ' ACTIVATED')
					add_conf(tun)
				elif args[0] == dbus.String(u'stopping'):
					print('====> VIRTUAL INTERFACE ' + str(tun) + ' STOPPING ...')
				elif args[0] == dbus.String(u'stopped'):
					print('\t ... ' + str(tun) + ' DEACTIVATED')
					del_conf(tun)
				else:
					print('***** WARNING: Something unexpected happened *****')
			else:
				print('***** ERROR: Exceeded maximum number (90) of potential virtual networks *****')
		else:
			pass


def signal_handler():

	dbus_loop = DBusGMainLoop(set_as_default=True)

	system_bus = dbus.SystemBus()
	# system_bus.add_signal_receiver(vpn_connection_handler, dbus_interface="org.freedesktop.NetworkManager.Device",
	#                                signal_name="StateChanged")
	# system_bus.add_signal_receiver(vpn_connection_handler, dbus_interface="com.ubuntu.Upstart0_6.Instance",
	#                                signal_name="StateChanged")
	system_bus.add_signal_receiver(vpn_connection_handler, interface_keyword='dbus_interface', member_keyword='member')

	loop = gobject.MainLoop()
	loop.run()

if __name__ == '__main__':
	signal_handler()