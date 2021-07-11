#!/bin/sh

export STATS_DIR=./stats
export POD_NAME=validator-0
export NODE_NAME=node-pool-lolwut
export DEBUG=1

if [ ! -z $SAVE_STATS ]; then
  echo "Saving some fresh stats..."
  # find a suitable-ish running docker container
  # container="docker ps --format '{{ .Names }}' | grep validator-0 | grep -v exporter"
  # j/k let's just use kube pod names instead
  container="validator-0"
  ./save-stats.sh $container
fi

# run exporter in the background, but capture pid so we can cleanup
./validator-exporter.py &
exporter_pid=$!
echo "exporter_pid=$exporter_pid"

# fetch the prometheus client results and sanity-check some basics
sleep 3
output=$(curl -s localhost:9825)
# echo $output
(echo "$output" | grep "validator_api_balance") && (echo 'found field') || (echo 'error, missing field' && exit 1)

# cleanup our exporter process
kill $exporter_pid
wait
