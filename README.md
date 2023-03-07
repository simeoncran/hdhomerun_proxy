# HDHomeRun network proxy
This set of scripts allows you to run your HDHomeRun tuner
on a different network from the network where your HDHomeRun apps
are running.

I use these scripts to allow me to watch TV in one location that
has poor TV reception via a tuner in a different location that has
good TV reception.

## The 2 proxies
1. The **app proxy** runs on the network where the tuner is.
2. The **tuner proxy** runs on the network where the apps are.

The proxies communicate with each other via a TCP connection.

## How it works
When an HDHomeRun app starts up, it broadcasts a discovery request. Normally
the tuner would receive this request and reply with information about the
tuner, including its IP address.

The **tuner proxy** listens for these discovery request broadcasts on the app's
network and forwards them to the **app proxy** running on the tuner's network, and
relays the reply back.

Note that only the broadcast packets are relayed. The proxy does not do anything
with the video data. However as long as there is a route between the app's network
and the tuner's network, the apps will be able to connect to the tuner and the video
data will flow.

Setting up routing between 2 private networks is beyond the scope of these
directions, but as a hint, I use WireGuard and masquerading so that the
tuner's network is reachable from the app's network. This works for the TCP
connection between the proxies and for the video data. The WireGuard connection
has around 19 Mbps bandwidth and can easily handle multiple video streams.

## Running it
Shell scripts are provided to start the proxies in Docker.

On the network where the tuner is:

```
app_proxy_start.sh
```

On the network where the apps are:
```
tuner_proxy_start.sh
```

The scripts ensure that the docker containers will restart automatically, so you should only need to run these commands once.
