mist.io
=======

The utilization of **Virtual Private Networks (VPNs)** now allows mist.io to
access private networks from the public Internet.

Installation
------------

First of all, make sure you switch to the proper libcloud commit (518e96a)
during the mist.io installation.

Post-installation steps:
------------------------

Make sure you grant the necessary **Linux capabilities** to the following
executables in the mist.io/bin/ directory: uwsgi, celery, cloudpy, python::

    sudo setcap cap_net_admin,cap_net_raw=eip <executable>

You may check that the Linux capabilities have been granted successfully
with the following command:

    sudo getcap <executable>

Substitute HAProxy with NGINX:
------------------------------

You may substitute the running HAProxy with **NGINX** in order to serve static
content, while passing the rest of the traffic to the backend server.

First, get NGINX::

    sudo apt-get install nginx

Get the NGINX configuration file from the GitHub repository and copy it
into /etc/nginx/sites-available. NGINX runs by default at port 80, so 
make sure there is no conflict with any other application. Aftewards, 
issue the command::

    ln -s /etc/nginx/sites-available/nginx.conf /etc/nginx/sites-enabled

In mist.io/ stop the HAProxy::

    ./bin/supervisorctl stop haproxy

Now, create an HTTP authentication for NGINX. You will need apache2-utils::

    sudo apt-get install apache2-utils
    sudo htpasswd -c /etc/nginx/.htpasswd <username>

The '-c' option is only required once in order to create the specified file.
You do not have to use the above option for additional users. Now, start
the NGINX service::

    sudo service nginx start

VPN service configuration:
--------------------------

It's time to setup the VPN end-points. Firstly, get **OpenVPN**::

    sudo apt-get install openvpn

At the OpenVPN server create an OpenVPN key to be used for authentication 
during session establishment::

    /usr/sbin/openvpn --genkey --secret /etc/openvpn/<key_file>

Create the server configuration file in /etc/openvpn/<conf_file>.conf. Make 
sure you pick proper IPs in order to avoid potential conflict with existing,
local private addresses. For example, you may pick 10.0.0.10 for the server
side and 10.0.0.5 for the client::

    dev tun0 
    dev-type tun
    port 1195
    ifconfig <server_IP> <client_IP>
    secret <key_file>
    proto tcp-server

Start the OpenVPN service::

    sudo service openvpn start

or::

    sudo service openvpn start tun0 

Now, configure a separate IP routing table for the newly created virtual
interface::

    sudo ip rule add from <server_IP> table 1
    sudo ip route add default via <client_IP> dev tun0 table 1 

The OpenVPN server side is all configured. Let's move to the client. The 
OpenVPN client can practically be any machine sitting in your private
network, even your own computer. After installing OpenVPN and transferring the 
server OpenVPN key to the client, create the client-side configuration file in 
/etc/openvpn/<conf_file>.conf. The <client_IP>-<server_IP> pair should be the 
reverse of the server-side configuration file::

    remote <server_public_IP>
    dev tun0 
    dev-type tun
    port 1195
    ifconfig <client_IP> <server_IP>
    secret <key_file>
    proto tcp-client

Afterwards, make sure IP forwarding is enabled::

    echo '1' | sudo tee -a /proc/sys/net/ipv4/ip_forward

Also, add the following IPtables NAT rule in order to allow proper routing of
public Internet traffic inside your private network::

    sudo iptables -t nat -A POSTROUTING -o <private_network_interface> -j MASQUERADE

Start the OpenVPN service and you are all set! Now you may manage and monitor 
through mist.io any machine sitting in your private network!
