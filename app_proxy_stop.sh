#!/bin/bash

container_name=hdhomerun_app_proxy
docker stop $container_name
docker container rm $container_name
