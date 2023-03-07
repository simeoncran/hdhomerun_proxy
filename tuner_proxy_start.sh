#!/bin/bash

container_name=hdhomerun_tuner_proxy

# Set this to point to where the app proxy is running.
app_proxy_host=suzypi.susan.internal.simeoncran.net

script_path=$(realpath $(dirname "${BASH_SOURCE[0]}"))

docker run -d \
       --name $container_name \
       --network host \
       --restart unless-stopped \
       -v "$script_path":/usr/src/myapp \
       -w /usr/src/myapp python:3 python3 ./hdhomerun_tuner_proxy.py $app_proxy_host
