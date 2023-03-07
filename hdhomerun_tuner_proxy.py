#!/usr/bin/env python3

import asyncio
import functools
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

# Proxy that acts like a tuner. Runs on the same network as the
# app and communicates with the app proxy running on the tuner's
# network.
class TunerProxy:
    tcp_transport : Optional[asyncio.Transport] = None
    udp_transport : Optional[asyncio.DatagramProtocol] = None
    codec = MessageCodec()

    class TCPClientProtocol(asyncio.Protocol):
        def __init__(self, on_con_lost):
            self.on_con_lost = on_con_lost

        def connection_made(self, transport: asyncio.Transport):
            TunerProxy.tcp_transport = transport
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
            if DEBUG:
                log(f'Received {len(data)} bytes from app proxy')
            TunerProxy.codec.decode(data, self._on_message_received_from_app_proxy)

        def connection_lost(self, exc):
            if DEBUG:
                log('The server closed the connection')
            self.on_con_lost.set_result(True)

    class UdpProtocol:
        def connection_made(self, transport: asyncio.DatagramTransport):
            TunerProxy.udp_transport = transport

        def datagram_received(self, data, addr):
            # Ignore datagrams until the tcp_transport is available.
            if TunerProxy.tcp_transport:
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

                encoded_message = TunerProxy.codec.encode(message)

                if DEBUG:
                    log(f'UDP broadcast received {len(data)} bytes from {ip}:{port}')
                    log(f'Sending {len(encoded_message)} bytes to app proxy')

                TunerProxy.tcp_transport.write(encoded_message)

        def connection_lost(self, exc):
            # This method needs to exist during shutdown.
            pass

    async def run_async(app_proxy_host):
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: TunerProxy.UdpProtocol(),
            local_addr=('255.255.255.255', HDHOMERUN_DISCOVER_UDP_PORT),
            reuse_port=True,
            allow_broadcast=True)

        while True:
            # Create a future to await so we know when the connection is lost.
            on_tcp_connection_lost = loop.create_future()

            log('Connecting to app proxy ...')
            try:
                await loop.create_connection(
                    lambda: TunerProxy.TCPClientProtocol(on_tcp_connection_lost),
                    app_proxy_host, TCP_PORT)
            except OSError as exc:
                if exc.errno == -2:
                    log(f'Unknown host: {app_proxy_host}')
                    sys.exit(-1)

                else:
                    # We'll get here if the server on the other end isn't responding.
                    log('Failed to connect. Sleeping ...')
                    # Wait a few seconds before attempting to reconnect.
                    await asyncio.sleep(3)
                    continue
            try:
                await on_tcp_connection_lost
            finally:
                TunerProxy.tcp_transport.close()
                TunerProxy.tcp_transport = None

            log('Connection lost')
            # Wait a few seconds before attempting to reconnect.
            await asyncio.sleep(3)
            log('Attempting reconnection ...')

if __name__ == '__main__':

    if len(sys.argv) < 2 or len(sys.argv) > 2:
        log(f'{sys.argv[0]} <app_proxy_host_address>')
        sys.exit(-1)
    
    asyncio.run(TunerProxy.run_async(sys.argv[1]))

