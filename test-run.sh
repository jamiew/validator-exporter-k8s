#!/bin/sh

export STATS_DIR=./stats
export POD_NAME=validator-test-0
export NODE_NAME=imacomputer
export DEBUG=1

if [ ! -z $SAVE_STATS ]; then
  echo "Saving some fresh stats..."
  # find a suitable-ish running docker container
  # container="docker ps --format '{{ .Names }}' | grep validator-0 | grep -v exporter"
  # j/k let's just use kube pod names instead
  container="validator-0"
  ./save-stats.sh $container
fi

./validator-exporter.py &
exporter_pid=$!
echo "exporter_pid=$exporter_pid"
sleep 3
curl localhost:9825
kill $exporter_pid
wait
