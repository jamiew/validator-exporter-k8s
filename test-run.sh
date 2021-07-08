#!/bin/sh

export STATS_DIR=./stats
export POD_NAME=validator-test-0
export NODE_NAME=imacomputer
export DEBUG=1

# find a suitable-ish running docker container
# j/k let's just use kube pod names instead
# container="docker ps --format '{{ .Names }}' | grep validator-0 | grep -v exporter"
container="validator-0"

./save-stats.sh $container
./validator-exporter.py
