#!/usr/bin/env python3

# Dumps messages sent to 255.255.255.255:65001 by the HDHomeRun app.

import os
import socket
import struct
import sys
import select

__author__ = 'Simeon Cran'
__version__ = '0.1'

HDHOMERUN_DISCOVER_UDP_PORT=65001
BUFFERSIZE = 1024



HDHOMERUN_TYPE = {
    2: "HDHOMERUN_TYPE_DISCOVER_REQ",
    3: "HDHOMERUN_TYPE_DISCOVER_RPY",
    4: "HDHOMERUN_TYPE_GETSET_REQ",   
    5: "HDHOMERUN_TYPE_GETSET_RPY", 
    6: "HDHOMERUN_TYPE_UPGRADE_REQ",
    7: "HDHOMERUN_TYPE_UPGRADE_RPY"
}

HDHOMERUN_DEVICE_TYPE = {
    0xffffffff: "HDHOMERUN_DEVICE_TYPE_WILDCARD",
    1 : "HDHOMERUN_DEVICE_TYPE_TUNER",
    5 : "HDHOMERUN_DEVICE_TYPE_STORAGE"
}
HDHOMERUN_TAG= {
    1: "HDHOMERUN_TAG_DEVICE_TYPE",
    2: "HDHOMERUN_TAG_DEVICE_ID",
    3: "HDHOMERUN_TAG_GETSET_NAME",
    4: "HDHOMERUN_TAG_GETSET_VALUE",
    5: "HDHOMERUN_TAG_ERROR_MESSAGE",
    0x10: "HDHOMERUN_TAG_TUNER_COUNT",
    0x15: "HDHOMERUN_TAG_GETSET_LOCKKEY",  
    0x27: "HDHOMERUN_TAG_LINEUP_URL",      
    0x28: "HDHOMERUN_TAG_STORAGE_URL",
    0x29: "HDHOMERUN_TAG_DEVICE_AUTH_BIN_DEPRECATED",
    0x2A: "HDHOMERUN_TAG_BASE_URL",
    0x2B: "HDHOMERUN_TAG_DEVICE_AUTH_STR",
    0x2C: "HDHOMERUN_TAG_STORAGE_ID",
    0x2D: "HDHOMERUN_TAG_MULTI_TYPE"
}



def main():

    # Socket that communicates with the app.
    app_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    app_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    # SO_REUSEADDR allows multiple listeners to this port, as long as they all
    # use SO_REUSEADDR.
    app_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    app_socket.bind(('255.255.255.255', HDHOMERUN_DISCOVER_UDP_PORT))

    print('Listening ...')
    while True:
        data, addr = app_socket.recvfrom(BUFFERSIZE)
        print(f'Received {len(data)} bytes from {addr}')

        # NOTE: all values are big endian, except the CRC which is little endian.
        packet_type, value_length, value, crc_reversed = struct.unpack(f'>HH{len(data)-8}s4s', data)
        # A second unpack is needed for the CRC because it is little endian.
        crc, = struct.unpack('<L', crc_reversed)
        print(f'{HDHOMERUN_TYPE[packet_type]} len({value_length}) CRC:{hex(crc)}   Data: {value}')

        # A get, set, or discover packet is a sequence of tag-length-value data.
        # Firmware upgrade requests are chunks of data. The replies are not documented.
        # We only handle the get, set, and discover packets.
        if packet_type < 2 or packet_type > 7:
            print(f'Unsupported packet type: {packet_type}')
        else:
            print(value)
            value_working = value
            while len(value_working) > 2:

                # If the tag is MULTI_TYPE, the length is 4 types the number of 32 bit values following.
                # Each is 32 bits and appears to be HDHOMERUN_DEVICE_TYPE
                tag = value_working[0]
                val_length = value_working[1]
                val_start = 2
                if val_length & 0x80:
                    val_length = (val_length & 0x7f) | (value_working[2] << 7)
                    val_start = 3
                val_end = val_start + val_length
                val = value_working[val_start: val_end]
                value_working = value_working[val_end + 1:]

                print(f'TAG: {hex(tag)}  Length: {val_length}  Value: {val}')
                
        # if HDHOMERUN_TYPE[packet_type] == "HDHOMERUN_TYPE_DISCOVER_REQ":
        #     print(decode_DISCOVER_REQ(value))

if __name__ == '__main__':
    main()
