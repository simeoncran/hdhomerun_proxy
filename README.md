# HDHomeRun network proxy
These Python 3.x scripts allow you to run your HDHomeRun tuner
on a different network from the network where your HDHomeRun apps
are running.

I use these scripts to allow me to watch TV in one location that
has poor TV reception via a tuner in a different location that has
good TV reception.

## The 2 proxies
Each Python script implements a ***proxy***.
1. The **app proxy** runs on the network where the HDHomeRun tuner is and acts as if it is the HDHomeRun app running on that network.
2. The **tuner proxy** runs on the network where the HDHomeRun apps are and acts as if it is the HDHomeRun tuner running on that network.

The proxies communicate with each other via a TCP connection.

## How it works
When an HDHomeRun app starts up, it **broadcasts** a discovery request. Normally the tuner would receive this request and reply with information that tells the tuner how to connect to it. However **broadcasts cannot be received outside of the network that they originate on**, so when the tuner and the apps are on different networks the tuner will never receive the discovery request broadcast. 

The **tuner proxy** script listens for these discovery request broadcasts on the app's network and forwards them to the **app proxy** running on the tuner's network, and relays the reply back. This allows the apps to find the tuners so they can communicate.

Note that only the broadcast packets are relayed. The proxy does not do
anything (and does not need to do anything) with the video data. If you can connect to your tuner's status page from your remote network, the video data should be able to flow, once the HDHomeRun app discovers your tuner (with the help of these scripts).

Setting up routing between 2 private networks is beyond the scope of these
directions, but as a hint, I use WireGuard as the VPN so that the
tuner's network is reachable from the app's network. This works for the TCP
connection between the proxies and for the video data. My WireGuard connection
has around 19 Mbps bandwidth and can easily handle multiple video streams.

## Running it
The scripts depend on Python 3.x. Any version should work.

Copy the contents of this repo onto a machine on the same network as your HDHomeRun tuner, and onto a machine on the same network as your HDHomeRun app.

On a machine on the same network as your HDHomeRun tuner run:
```
python3 hdhomerun_app_proxy.py
```

On a machine on the same network as your HDHomeRun app run:
```
python3 hdhomerun_tuner_proxy.py my_app_proxy.network.address
```
... where ``my_app_proxy.network.address`` is the address of the machine where you started the app proxy.

## Testing it
You should immediately see from the output of the scripts that the tuner proxy has made a connection to the app proxy.

Now run an HDHomeRun app. You should see that the tuner proxy receives tuner discovery packets from the app, and that the app proxy is forwarding them to the tuner.

## Running it with Docker

***This is a more advanced way to set up the proxies. You don't need to do this, it's just very convenient if you know what you're doing.***

The advantage of Docker is that the scripts will be restarted on failure or reboot and you don't even need to have Python installed. I run these on Raspberry Pi 4's on each end.

### On the tuner side
On a Linux machine running on the same network as the HDHomeRun tuner, run this script:
```
#!/bin/bash

# Set this to point to where the app proxy is running.
app_proxy_host=suzypi.susan.internal.simeoncran.net

container_name=hdhomerun_app_proxy

script_path=$(realpath $(dirname "${BASH_SOURCE[0]}"))

docker run -d \
       --name $container_name \
       --network host \
       --restart unless-stopped \
       -v "$script_path":/usr/src/myapp \
       -w /usr/src/myapp python:3 python3 ./hdhomerun_app_proxy.py $app_proxy_host
```

To view the logs:
```
docker logs hdhomerun_app_proxy
```

To stop the container:
```
docker stop hdhomerun_app_proxy
```
### On the app side
On a Linux machine running on the same network as the HDHomeRun tuner, run this script:
```
#!/bin/bash

# Set this to point to where the app proxy is running.
app_proxy_host=suzypi.internal.susan.simeoncran.net

container_name=hdhomerun_tuner_proxy

script_path=$(realpath $(dirname "${BASH_SOURCE[0]}"))

docker run -d \
       --name $container_name \
       --network host \
       --restart unless-stopped \
       -v "$script_path":/usr/src/myapp \
       -w /usr/src/myapp python:3 python3 ./hdhomerun_tuner_proxy.py $app_proxy_host

```

To view the logs:
```
docker logs hdhomerun_tuner_proxy
```

To stop the container:
```
docker stop hdhomerun_tuner_proxy
```

