#!/bin/bash

export STATS_DIR=./stats
export POD_NAME=validator-0
export NODE_NAME=node-pool-lolwut
export DEBUG=1
export ALL_PENALTIES=1

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

# cleanup our exporter process
kill "$exporter_pid"
sleep 1

# then process the output and abort if things are awry
function check_output() {
  # local output="$1"
  local field_name="$2"
  echo -n "Checking $field_name: "
  match=$(echo "$output" | grep "$field_name")
  # last space-delimited field is our actual output value
  # value=$(echo "$match" | awk '{ print $NF }')
  # echo -n "$value "
  [ -n "$match" ] && (echo "✅") || (echo "❌"; exit 1)
}

echo
echo "Verifying output..."
check_output "$output", "validator_block_age"
check_output "$output", "validator_height"
check_output "$output", "validator_inconsensus"
check_output "$output", "validator_ledger"
check_output "$output", "validator_hbbft_perf"
check_output "$output", "validator_connections"
check_output "$output", "validator_sessions"
check_output "$output", "validator_api_balance"
check_output "$output", "validator_api_rewards"
echo "Everything looks good"