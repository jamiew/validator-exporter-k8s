#!/bin/bash

image="jamiedubs/validator-exporter" # must match hub.docker.com repo name
tag="latest"

docker build -t "$image" .
# docker push $image:$tag
