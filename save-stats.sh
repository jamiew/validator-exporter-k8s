#!/bin/bash

v="docker exec validator miner"
# dir=$STATS_DIR
dir="$HOME/dev/validator-exporter/stats"

echo "putting files into $dir ..."

date
$v info name > $dir/info_name;
$v info height > $dir/info_height;
$v info p2p_status > $dir/info_p2p_status;
$v info in_consensus > $dir/info_in_consensus;
$v info block_age > $dir/info_block_age;
$v hbbft perf --format csv > $dir/hbbft_perf.csv;
$v peer book -s --format csv > $dir/peer_book.csv;
$v ledger validators --format csv > $dir/ledger_validators.csv;
$v print_keys > $dir/print_keys;
$v versions > $dir/versions;
date
