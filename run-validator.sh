#!/bin/bash

container_name="validator"
if [ ! -z $TESTNET ]; then
  echo "Running in testnet mode"
  image="quay.io/team-helium/validator:latest-val-amd64"
  data_dir="$HOME/validator_data_testnet"
else
  echo "Running in mainnet mode; use TESTNET=1 to run in testnet"
  image="quay.io/team-helium/validator:latest-validator-amd64"
  data_dir="$HOME/validator_data"
fi

if [ ! -d "$data_dir" ]; then
  echo "data_dir does not exist: $data_dir"
  exit 1
fi

# OK now do something
docker pull $image
docker rm -f $container_name

# --restart always \
docker run -d \
  --publish 2154:2154/tcp \
  --name "$container_name" \
  --mount type=bind,source=$data_dir,target=/var/data \
  $image
