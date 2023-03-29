#!/usr/bin/env python3

import asyncio
import os
import socket
import struct
import sys
from typing import Optional
from message_codec import MessageCodec

# UDP port used to receive discovery requests on 255.255.255.255.
# Defined at: https://github.com/Silicondust/libhdhomerun/blob/master/hdhomerun_pkt.h
HDHOMERUN_DISCOVER_UDP_PORT=65001

# We arbitrarily use the same port for the app proxy's TCP server that
# is used to forward requests between the tuner proxy and the tuner proxy.
# It could be anything as long as the 2 proxies use the same port.
TCP_PORT = HDHOMERUN_DISCOVER_UDP_PORT

DEBUG = 'DEBUG' in os.environ

def log(str: str):
    print(str, file=sys.stderr)

# Encode/decode messages onto the TCP stream to the remote tuner.
codec = MessageCodec()

# TCP connection to the app proxy running on the network where
# the HDHomeRun tuner is.
tcp_transport : Optional[asyncio.Transport] = None

# Handles broadcast packets from HDHomeRun apps that are looking
# for tuners.
udp_transport : Optional[asyncio.DatagramProtocol] = None


class TCPClientProtocol(asyncio.Protocol):
    def __init__(self, on_con_lost):
        self.on_con_lost = on_con_lost

    def connection_made(self, transport: asyncio.Transport):
        peername = transport.get_extra_info("peername")
        log(f'Connected to app proxy: {peername[0]}:{peername[1]}')

    def _on_message_received_from_app_proxy(self, msg):
        # Unpack the message.
        addr, port, data = struct.unpack(f'!4sH{len(msg) - 6}s', msg)
        ip = socket.inet_ntoa(addr)

        # Send the reply back to the app.
        if DEBUG:
            log(f'Replying with {len(data)} bytes to {ip}:{port}')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (ip, port))

    def data_received(self, data):
        log(f'Reply received: {len(data)} bytes from app proxy')
        codec.decode(data, self._on_message_received_from_app_proxy)

    def connection_lost(self, exc):
        if DEBUG:
            log('The server closed the connection')
        self.on_con_lost.set_result(True)

class UdpProtocol:
    def connection_made(self, transport: asyncio.DatagramTransport):
        pass

    def datagram_received(self, data, addr):
        # Ignore datagrams until the tcp_transport is available.
        if tcp_transport:
            ip, port = addr
            # We received a broadcast from the HDHomeRun app. Package it up into
            # a message containing the source address, port, and payload and send
            # it to the app_proxy. When or if a response comes back, it will
            # contain the same source address and port so we can send it back to
            # the app.
            message = struct.pack(f'!4sH{len(data)}s',
                                    socket.inet_aton(ip),
                                    port,
                                    data)

            encoded_message = codec.encode(message)

            log(f'Request received: {len(data)} bytes from app at {ip}:{port}')
            
            if DEBUG:
                log(f'Sending {len(encoded_message)} bytes to app proxy')

            tcp_transport.write(encoded_message)

    def connection_lost(self, exc):
        # This method needs to exist during shutdown.
        pass

async def run_async(app_proxy_host):
    loop = asyncio.get_running_loop()

    while True:
        # Create a future to await so we know when the connection is lost.
        on_tcp_connection_lost = loop.create_future()

        log(f'Connecting to app proxy at {app_proxy_host}...')
        try:
            global tcp_transport
            tcp_transport, _tcp_protocol = await loop.create_connection(
                lambda: TCPClientProtocol(on_tcp_connection_lost),
                app_proxy_host, TCP_PORT)


            global udp_transport
            udp_transport, _udp_protocol = await loop.create_datagram_endpoint(
                lambda: UdpProtocol(),
                local_addr=('255.255.255.255', HDHOMERUN_DISCOVER_UDP_PORT),
                reuse_port=True,
                allow_broadcast=True)

            # We are running. Wait here until the connection is lost.
            await on_tcp_connection_lost

        except OSError as exc:
            if exc.errno == -2:
                log(f'Unknown host: {app_proxy_host}')
                sys.exit(-1)
            elif exc.errno == 98:
                log('Address is in use. Is the proxy already running?')
                sys.exit(-1)

        finally:
            if tcp_transport:
                tcp_transport.close()
                tcp_transport = None
            if udp_transport:
                udp_transport.close()
                udp_transport = None

        log('Disconnected')
        # Wait a few seconds before attempting to reconnect.
        await asyncio.sleep(3)
        log('Attempting reconnection ...')

if __name__ == '__main__':

    if len(sys.argv) < 2 or len(sys.argv) > 2:
        log(f'{sys.argv[0]} <app_proxy_host_address>')
        sys.exit(-1)
    
    asyncio.run(run_async(sys.argv[1]))

