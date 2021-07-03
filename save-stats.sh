#!/bin/bash

container="$1"

if [ -z $container ]; then
  echo "$0: specify container name as first argument"
  exit 1
fi

echo "container=$container"
v="docker exec $container miner"
echo "v=$v"
# dir=$STATS_DIR
dir="$HOME/dev/validator-exporter/stats"

echo "putting files into $dir ..."

date
time $v info name > $dir/info_name;
time $v info height > $dir/info_height;
time $v info p2p_status > $dir/info_p2p_status;
time $v info in_consensus > $dir/info_in_consensus;
time $v info block_age > $dir/info_block_age;
time $v hbbft perf --format csv > $dir/hbbft_perf.csv;
time $v peer book -s --format csv > $dir/peer_book.csv;
# time $v ledger validators --format csv > $dir/ledger_validators.csv;
time $v print_keys > $dir/print_keys;
time $v versions > $dir/versions;
date
