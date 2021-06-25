#!/bin/bash

container_name="validator"
# image="quay.io/team-helium/validator:latest-validator-amd64"
image="quay.io/team-helium/validator:latest-val-amd64"
data_dir="$HOME/validator_data_testnet"

docker pull $image
docker rm -f $container_name

# --restart always \
docker run -d \
  --publish 2154:2154/tcp \
  --name "$container_name" \
  --mount type=bind,source=$data_dir,target=/var/data \
  $image
