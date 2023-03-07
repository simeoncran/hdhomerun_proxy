#!/usr/bin/env python3

import asyncio
import functools
import os
import socket
import struct
import sys
from typing import Optional

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

# Encodes messages to and decodes messages from a byte stream.
class MessageCodec:
    def __init__(self):
        self._msg_buffer = bytes()
        self._length_bytes_remaining = 2
        self._msg_bytes_remaining = 0

    def encode(self, data: bytes):
        return struct.pack(f'>H{len(data)}s', len(data), data)

    def decode(self, data: bytes, message_callback):
        i = 0

        while True:

            while self._length_bytes_remaining:
                if i >= len(data):
                    # Not enough bytes received yet to know the length of the message.
                    return

                # The length is big-endian.
                self._length_bytes_remaining -= 1
                self._msg_bytes_remaining  |= (data[i] << (self._length_bytes_remaining * 8))
                i += 1

            if self._msg_bytes_remaining:
                # There are more bytes required. Read as much as we can.
                data_read = data[i: i + self._msg_bytes_remaining]
                data_read_len = len(data_read)
                # Append the data to the message.
                self._msg_buffer += data_read
                self._msg_bytes_remaining -= data_read_len
                i += data_read_len

            if self._msg_bytes_remaining:
                # There are more bytes required.
                return

            # We have a complete message.
            message = self._msg_buffer

            # Reset the state. Do that now to avoid reentrance issues.
            self._length_bytes_remaining = 2
            self._msg_bytes_remaining = 0
            self._msg_buffer = bytes()

            # Return the message via the callback.
            message_callback(message)

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
            try:
                self.on_con_lost.set_result(True)
            except asyncio.exceptions.InvalidStateError:
                # Ignore errors during KeyboardInterrupt shutdown.
                pass

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
        try:

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
                try:
                    await asyncio.sleep(3)
                except asyncio.exceptions.CancelledError:
                    pass
                log('Attempting reconnection ...')

        finally:
            try:
                if TunerProxy.tcp_transport:
                    TunerProxy.tcp_transport.close()
            except:
                pass
            try:
                if TunerProxy.udp_transport:
                    TunerProxy.udp_transport.close()
            except:
                pass

    def usage():
        return f'{sys.argv[0]} tunerproxy <app_proxy_host_address>'

    def run():
        if len(sys.argv) < 3 or len(sys.argv) > 3:
            log(TunerProxy.usage())
            sys.exit(-1)
        try:
            asyncio.run(TunerProxy.run_async(sys.argv[2]))
        except KeyboardInterrupt:
            log('Exiting ...')

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

    def usage():
        return f'{sys.argv[0]} appproxy [bind_to_host_address]'

    def run():
        try:
            # Use the given address to bind to, otherwise pass None
            # to bind to all interfaces.
            asyncio.run(AppProxy.run_async(sys.argv[2] if len(sys.argv) > 2 else None))
        except KeyboardInterrupt:
            log('Exiting ...')

if __name__ == '__main__':

    if len(sys.argv) > 1:
        if sys.argv[1] == 'tunerproxy':
            TunerProxy.run()
            sys.exit(0)
        elif sys.argv[1] == 'appproxy':
            AppProxy.run()
            sys.exit(0)


    log(f'Usage:')
    log(f'    {TunerProxy.usage()}')
    log('     OR')
    log(f'    {AppProxy.usage()}')
    sys.exit(-1)

