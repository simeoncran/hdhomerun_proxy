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

# Proxy that acts like an app. Runs on the same network as the
# tuner and communicates with the tuner proxy running on the
# app's network.
class AppProxy:
    tcp_transport : Optional[asyncio.Transport] = None
    codec = MessageCodec()

    # A protocol object that manages a UDP socket for a single query that communicates
    # with the tuner. Each query may result is multiple reponses - each tuner can
    # reply with multiple replies, and there may be more than one tuner on the network. 
    class ClientDatagramProtocol:
        def __init__(self, reply_callback):
            self.reply_callback = reply_callback

        # Implementation of DatagramProtocol
        def connection_made(self, transport : asyncio.DatagramTransport):
            pass

        # Implementation of DatagramProtocol
        def connection_lost(self, exc):
            pass

        # Implementation of DatagramProtocol
        def datagram_received(self, data, addr):
            self.reply_callback(data)

        async def query_tuner_async(self, query_data):
            # Create an endpoint.
            loop = asyncio.get_running_loop()
            datagram_endpoint, protocol = await loop.create_datagram_endpoint(
                lambda: self,
                allow_broadcast=True,
                remote_addr=('255.255.255.255', HDHOMERUN_DISCOVER_UDP_PORT))

            datagram_endpoint.sendto(query_data)

            # Give the tuner some time to respond then clean up.
            # We don't know how many responses we will get, so we'll just hang around
            # for a while then clean up. 
            await asyncio.sleep(0.5)
            datagram_endpoint.close()

        def query_tuner(query_data, reply_callback):
            client = AppProxy.ClientDatagramProtocol(reply_callback)
            asyncio.create_task(client.query_tuner_async(query_data))
        
    # A protocol object that manages a TCP connection from a tuner proxy.
    class TcpServerProtocol(asyncio.Protocol):
        def connection_made(self, transport: asyncio.Transport):
                AppProxy.tcp_transport = transport
                peername = transport.get_extra_info('peername')
                log(f'Tuner proxy at {peername[0]}:{peername[1]} connected')
                self.transport = transport

        # Protocol implementation.
        def data_received(self, data):
            # Convert the stream data into a message.
            AppProxy.codec.decode(data, self.on_received_message)

        # Handle a message that has been received from the client.
        def on_received_message(self, msg):
            # The message is encoded to contain the original source address
            # and port of the app that made the request to the tuner_proxy.
            source_addr, source_port, query_data = struct.unpack(f'!4sH{len(msg) - 6}s', msg)

            # Perform the query.
            AppProxy.ClientDatagramProtocol.query_tuner(
                        query_data,
                        functools.partial(self.reply, source_addr, source_port))

        def reply(self, source_addr : bytes, source_port, reply_data):
            # Pack up the data.
            reply = struct.pack(f'!4sH{len(reply_data)}s', 
                                source_addr,
                                source_port,
                                reply_data)
            
            # Send back to the tuner proxy.
            self.transport.write(AppProxy.codec.encode(reply))
            
    async def run_async(app_proxy_host):
        loop = asyncio.get_running_loop()
        server = await loop.create_server(
            lambda: AppProxy.TcpServerProtocol(),
            app_proxy_host, HDHOMERUN_DISCOVER_UDP_PORT)

        async with server:
            await server.serve_forever()

if __name__ == '__main__':
    if len(sys.argv) < 1 or len(sys.argv) > 2:
        log(f'{sys.argv[0]} [bind_to_host_address]')
        sys.exit(-1)

    # Use the given address to bind to, otherwise pass None
    # to bind to all interfaces.
    asyncio.run(AppProxy.run_async(sys.argv[1] if len(sys.argv) > 1 else None))


