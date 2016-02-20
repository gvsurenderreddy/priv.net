#!/usr/bin/env python

import gobject
import dbus
from dbus.mainloop.glib import DBusGMainLoop

'''
def vpn_connection_handler(*args):
	for arg in args:
		print(str(arg))
'''


def vpn_connection_handler(*args, **kwargs):

	''' parameter: RESULT=ok ?
		more criteria ? robustness ?
		get network interface '''

	# mod = str(kwargs['dbus_interface'] + "." + kwargs['member'])
	if kwargs['member'] == 'EventEmitted':
		# print "Event Emitted ----->        " + str(args)
		if args[0] == dbus.String(u'started'):
			if args[1][0] == dbus.String(u'JOB=network-interface') and args[1][1] in [dbus.String(u'INSTANCE=ppp0'), dbus.String(u'INSTANCE=ppp1')]:
				print('***** VIRTUAL INTERFACE UP *****')
		if args[0] == dbus.String(u'stopped'):
			if args[1][0] == dbus.String(u'JOB=network-interface') and args[1][1] in [dbus.String(u'INSTANCE=ppp0'), dbus.String(u'INSTANCE=ppp1')]:
				print('***** VIRTUAL INTERFACE DOWN *****')


def signal_handler():
	dbus_loop = DBusGMainLoop(set_as_default=True)

	system_bus = dbus.SystemBus()

	# system_bus.add_signal_receiver(vpn_connection_handler, dbus_interface="org.freedesktop.NetworkManager.Device",
	#                               signal_name="StateChanged")
	# system_bus.add_signal_receiver(vpn_connection_handler, dbus_interface="com.ubuntu.Upstart0_6.Instance",
	#                                signal_name="StateChanged")
	system_bus.add_signal_receiver(vpn_connection_handler, interface_keyword='dbus_interface', member_keyword='member')

	loop = gobject.MainLoop()
	loop.run()

if __name__ == '__main__':
	signal_handler()