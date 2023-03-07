#!/bin/bash

container_name=hdhomerun_tuner_proxy
docker stop $container_name
docker container rm $container_name
