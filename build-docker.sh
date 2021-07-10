#!/bin/bash
# run to build local Docker image
# to publish to docker hub, try:
# PUBLISH=1 ./build.sh
# 
set -e

image="jamiedubs/validator-exporter" # must match hub.docker.com repo name
tag="latest"

docker build -t "$image" .

if [ -n "$PUBLISH" ]; then
  echo "Publishing to Docker Hub..."
  docker push $image:$tag
fi
