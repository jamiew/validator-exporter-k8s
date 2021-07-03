#!/bin/bash
# TODO how do we keep this in sync with `validator-setup.sh` from other repo?
# right now these are duplicating one another and falling out of sync

pod="$1"
if [ -z $pod ]; then
  echo "$0: specify pod name as first argument"
  exit 1
fi

dir=${STATS_DIR:="./stats"}
if [ ! -d "$dir" ]; then
  echo "$0: STATS_DIR '$stats_dir' is not a directory"
  exit 1
fi

container="validator"
namespace="helium"
v="time kubectl exec $pod -c $container -n $namespace -- miner"
echo "v=$v"

# paste from k8s/validator-setup.sh here
# forgive me for what i've done

echo "$(date): saving stats to $dir ..."
start_time="$(date -u +%s)"
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
end_time="$(date -u +%s)"
elapsed="$(($end_time-$start_time))"
echo "Took $elapsed seconds"
