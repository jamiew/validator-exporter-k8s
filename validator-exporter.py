#!/usr/bin/env python3

# external packages
import prometheus_client
import requests

# internal packages
import time
import os
import re
import logging
from collections import namedtuple

# remember, levels: debug, info, warning, error, critical. there is no trace.
logging.basicConfig(format="%(filename)s:%(funcName)s:%(lineno)d:%(levelname)s\t%(message)s", level=logging.WARNING)
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG if os.environ.get('DEBUG') else logging.INFO)
log.info("validator-exporter starting up...!")

# where the validator container stashes its stats files
STATS_DIR = os.environ.get('STATS_DIR', '/var/data/stats')
if not os.path.isdir(STATS_DIR):
  log.error(f"STATS_DIR is not a real directory: {STATS_DIR}")
  exit(1)

# exposed by Kubernetes environment variables
POD_NAME = os.environ.get('POD_NAME')
NODE_NAME = os.environ.get('NODE_NAME')
if not POD_NAME or not NODE_NAME:
  log.error('NODE_NAME and/or POD_NAME env variables are missing')
  exit(1)

# time to sleep between scrapes
UPDATE_PERIOD = int(os.environ.get('UPDATE_PERIOD', 30))

# for testnet, https://testnet-api.helium.wtf/v1
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://api.helium.io/v1')

# prometheus exporter types Gauge,Counter,Summary,Histogram,Info and Enum
SCRAPE_TIME = prometheus_client.Summary('validator_scrape_time',
                              'Time spent collecting miner data')
CHAIN_STATS = prometheus_client.Gauge('chain_stats',
                              'Stats about the global chain',
                              ['resource_type'])
VAL = prometheus_client.Gauge('validator_height',
                              "Height of the validator's blockchain",
                              ['resource_type', 'validator_name', 'pod', 'node'])
INCON = prometheus_client.Gauge('validator_inconsensus',
                              'Is validator currently in consensus group',
                              ['validator_name', 'pod', 'node'])
BLOCKAGE = prometheus_client.Gauge('validator_block_age',
                              'Age of the current block',
                             ['resource_type', 'validator_name', 'pod', 'node'])
HBBFT_PERF = prometheus_client.Gauge('validator_hbbft_perf',
                              'HBBFT performance metrics from perf, only applies when in CG',
                             ['resource_type', 'subtype', 'validator_name', 'pod', 'node'])
CONNECTIONS = prometheus_client.Gauge('validator_connections',
                              'Number of libp2p connections ',
                             ['resource_type', 'validator_name', 'pod', 'node'])
SESSIONS = prometheus_client.Gauge('validator_sessions',
                              'Number of libp2p sessions',
                             ['resource_type', 'validator_name', 'pod', 'node'])
LEDGER_PENALTY = prometheus_client.Gauge('validator_ledger',
                              'Validator performance metrics ',
                             ['resource_type', 'subtype', 'validator_name', 'pod', 'node'])
VALIDATOR_VERSION = prometheus_client.Info('validator_version',
                              'Version number of the miner container',
                              ['validator_name', 'pod', 'node'])
BALANCE = prometheus_client.Gauge('validator_api_balance',
                              'Balance of the validator owner account (from Helium API)',
                              ['validator_addr', 'validator_name', 'owner_address', 'pod', 'node'])
REWARDS = prometheus_client.Gauge('validator_api_rewards',
                              'Rewards for the validator (from Helium API)',
                              ['validator_addr', 'validator_name', 'pod', 'node'])
UPTIME = prometheus_client.Gauge('validator_container_uptime',
                              'Time container has been at a given state',
                              ['state_type', 'validator_name', 'pod', 'node'])
miner_facts = {}

def try_int(v):
  if re.match(r"^\-?\d+$", v):
    return int(v)
  return v

def try_float(v):
  if re.match(r"^\-?[\d\.]+$", v):
    return float(v)
  return v

def read_file(command):
  # log.debug(f"read_file dir={STATS_DIR} command={command}")
  filename = STATS_DIR + "/" + command
  text = ""
  try:
    with open(filename, 'r') as f:
      text = f.read()
  except FileNotFoundError as ex:
    log.error(f"could not find file {filename}", exc_info=ex)
  finally:
    # FIXME kind of faking an object like what's returned by old shell cmd
    dict = {"output": str.encode(text)}
    obj = namedtuple("ObjectName", dict.keys())(*dict.values())
    return obj


def get_facts():
  if miner_facts:
    return miner_facts

  # example output:
  # {pubkey,"1YBkf..."}.
  # {onboarding_key,"1YBkf..."}.
  # {animal_name,"one-two-three"}.
  out = read_file('print_keys')

  if out == "" or type(out) == str:
    log.warning(f"get_facts: no data for print_keys, aborting")
    return

  printkeys = {}
  for line in out.output.split(b"\n"):
    strline = line.decode('utf-8')

    # := requires py3.8
    if m := re.match(r'{([^,]+),"([^"]+)"}.', strline):
      k = m.group(1)
      v = m.group(2)
      log.debug(f"get_facts: {k}={v}")
      printkeys[k] = v

  if v := printkeys.get('pubkey'):
    miner_facts['address'] = v
  if printkeys.get('animal_name'):
    miner_facts['name'] = v
  #$ docker exec validator miner print_keys
  return miner_facts


# Decorate function with metric.
@SCRAPE_TIME.time()
def stats():
  miner_facts = get_facts()
  hotspot_name_str = get_miner_name()
  if not hotspot_name_str:
    log.error("Hotspot name is missing; aborting")
    return
  collect_miner_version(hotspot_name_str)
  collect_block_age(hotspot_name_str)
  collect_miner_height(hotspot_name_str)
  # collect_chain_stats()
  collect_in_consensus(hotspot_name_str)
  collect_ledger_validators(hotspot_name_str)
  collect_peer_book(hotspot_name_str)
  collect_hbbft_performance(hotspot_name_str)
  collect_balance(miner_facts['address'], hotspot_name_str)
  collect_rewards(miner_facts['address'], hotspot_name_str)

def safe_get_json(url):
  # TODO always debug this request - how long it took, response status code, response bytes
  try:
    ret = requests.get(url)
    if not ret.status_code == requests.codes.ok:
      log.error(f"bad status code ({ret.status_code}) from url: {url}")
      return
    retj = ret.json()
    return retj
  except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ex:
    log.error(f"error fetching {url}: {ex}")
    return

def collect_chain_stats():
  api = safe_get_json(f'{API_BASE_URL}/blocks/height')
  if not api:
    log.error("chain height fetch returned empty JSON")
    return
  height_val = api['data']['height']
  CHAIN_STATS.labels('height').set(height_val)

  api = None
  api = safe_get_json(f'{API_BASE_URL}/validators/stats')
  if not api:
    log.error("val stats stats fetch returned empty JSON")
    return
  count_val = api['data']['staked']['count']
  CHAIN_STATS.labels('staked_validators').set(count_val)

def collect_balance(validator_addr, miner_name):
  api_validators = safe_get_json(f'{API_BASE_URL}/validators/{validator_addr}')
  if not api_validators:
    log.error("validator fetch returned empty JSON")
    return
  elif not api_validators.get('data') or not api_validators['data'].get('owner'):
    log.error("could not find validator data owner in json")
    return
  owner_addr = api_validators['data']['owner']

  api_accounts = safe_get_json(f'{API_BASE_URL}/accounts/{owner_addr}')
  if not api_accounts:
    log.warning(f"no api_accounts. bad result from Helium API? {api_accounts}")
    return
  elif not api_accounts.get('data') or not api_accounts['data'].get('balance'):
    log.debug(f"api_accounts missing data or balance {api_accounts}")
    return

  balance = float(api_accounts['data']['balance'])/1E8
  log.debug(f'balance={balance}')
  BALANCE.labels(validator_addr, miner_name, owner_addr, POD_NAME, NODE_NAME).set(balance)

def collect_rewards(validator_addr, miner_name):
  min_time = "2020-01-01"
  max_time = "2050-01-01" # make sure to update this in 2050
  base_url = f'{API_BASE_URL}/validators/{validator_addr}/rewards?min_time={min_time}&max_time={max_time}'
  rewards = 0
  cursor = ''
  loop_count = 0
  while True:
    url = f"{base_url}&cursor={cursor}" if cursor else base_url
    log.debug(f'making request to {url}')
    json = safe_get_json(url)
    if not json:
      log.error(f"could not fetch validator rewards from Helium API. json={json}")
      return

    data = json.get('data')
    for x in data:
      rewards += x.get('amount')
    cursor = json.get('cursor')
    time.sleep(0.25)
    loop_count += 1

    if not cursor:
      log.debug(f"response missing cursor, aborting loop")
      break

  # TODO finish me
  log.info(f'collect_rewards rewards={rewards} loop_count={loop_count}')
  REWARDS.labels(validator_addr, miner_name, POD_NAME, NODE_NAME).set(rewards)

def get_miner_name():
  # need to fix this. hotspot name really should only be queried once
  out = read_file('info_name')
  hotspot_name = out.output.decode('utf-8').rstrip("\n")
  if not hotspot_name or "Error" in hotspot_name or "failed" in hotspot_name or "not responding" in hotspot_name:
    log.warning(f"Bad data for miner name hotspot_name={hotspot_name}")
    return
  return hotspot_name

def collect_miner_height(miner_name):
  # grab the local blockchain height
  out = read_file('info_height')
  txt = out.output.decode('utf-8').rstrip("\n")
  if not txt or (isinstance(txt, str) and "Error" in txt or "failed" in txt):
    log.warning("bad output from info_height: {out.output")
    return
  VAL.labels('Height', miner_name, POD_NAME, NODE_NAME).set(out.output.split()[1])

def collect_in_consensus(miner_name):
  # check if currently in consensus group
  out = read_file('info_in_consensus')
  incon_txt = out.output.decode('utf-8').rstrip("\n")
  if not incon_txt or "failed" in incon_txt:
    log.warning(f"Bad result from in_consensus={incon_txt}")
  incon = 0
  if incon_txt == 'true':
    incon = 1
  log.debug(f"in_consensus? {incon} / {incon_txt}")
  INCON.labels(miner_name, POD_NAME, NODE_NAME).set(incon)

def collect_block_age(miner_name):
  # collect current block age
  out = read_file('info_block_age')
  ## transform into a number
  age_val = try_int(out.output.decode('utf-8').rstrip("\n"))

  if not out.output or (isinstance(age_val, str) and ("Error" in age_val or "failed" in age_val)):
    log.warning(f"Bad output from block_age... age_val={age_val}")
    return

  BLOCKAGE.labels('BlockAge', miner_name, POD_NAME, NODE_NAME).set(age_val)
  log.debug(f"block_age: {age_val}")

# persist these between calls
hval = {}
def collect_hbbft_performance(miner_name):
  # parse the hbbft performance table for the penalty field
  out = read_file('hbbft_perf.csv')
  #print(out.output)

  for line in out.output.decode('utf-8').split("\n"):
    c = [x.strip() for x in line.split(',')]
    # samples:

    if len(c) == 7 and miner_name == c[0]:
      # name,bba_completions,seen_votes,last_bba,last_seen,tenure,penalty
      # great-clear-chinchilla,5/5,237/237,0,0,2.91,2.91
      log.debug(f"resl7: {c}; {miner_name}/{c[0]}")

      (hval['bba_votes'],hval['bba_tot'])=c[1].split("/")
      (hval['seen_votes'],hval['seen_tot'])=c[2].split("/")
      hval['bba_last_val']=try_float(c[3])
      hval['seen_last_val']=try_float(c[4])
      hval['tenure'] = try_float(c[5])
      hval['pen_val'] = try_float(c[6])
    elif len(c) == 6 and miner_name == c[0]:
      # name,bba_completions,seen_votes,last_bba,last_seen,penalty
      # curly-peach-owl,11/11,368/368,0,0,1.86
      log.debug(f"resl6: {c}; {miner_name}/{c[0]}")

      (hval['bba_votes'],hval['bba_tot'])=c[1].split("/")
      (hval['seen_votes'],hval['seen_tot'])=c[2].split("/")
      hval['bba_last_val']=try_float(c[3])
      hval['seen_last_val']=try_float(c[4])
      hval['pen_val'] = try_float(c[5])

    elif len(c) == 6:
      # not our line
      pass
    elif len(line) == 0:
      # empty line
      pass
    # else:
    #    log.debug(f"wrong len ({len(c)}) and wrong miner_name ({miner_name}) for hbbft: {c}")

    # always set these, that way they get reset when out of CG
    HBBFT_PERF.labels('hbbft_perf','Penalty', miner_name, POD_NAME, NODE_NAME).set(hval.get('pen_val', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Total', miner_name, POD_NAME, NODE_NAME).set(hval.get('bba_tot', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Votes', miner_name, POD_NAME, NODE_NAME).set(hval.get('bba_votes', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Total', miner_name, POD_NAME, NODE_NAME).set(hval.get('seen_tot', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Votes', miner_name, POD_NAME, NODE_NAME).set(hval.get('seen_votes', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Last', miner_name, POD_NAME, NODE_NAME).set(hval.get('bba_last_val', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Last', miner_name, POD_NAME, NODE_NAME).set(hval.get('seen_last_val', 0))
    HBBFT_PERF.labels('hbbft_perf','Tenure', miner_name, POD_NAME, NODE_NAME).set(hval.get('tenure', 0))

def collect_peer_book(miner_name):
  # peer book -s output
  out = read_file('peer_book.csv')
  # parse the peer book output

  # samples
  # address,name,listen_addrs,connections,nat,last_updated
  # /p2p/1YBkfTYH8iCvchuTevbCAbdni54geDjH95yopRRznZtAur3iPrM,bright-fuchsia-sidewinder,1,6,none,203.072s
  # listen_addrs (prioritized)
  # /ip4/174.140.164.130/tcp/2154
  # local,remote,p2p,name
  # /ip4/192.168.0.4/tcp/2154,/ip4/72.224.176.69/tcp/2154,/p2p/1YU2cE9FNrwkTr8RjSBT7KLvxwPF9i6mAx8GoaHB9G3tou37jCM,clever-sepia-bull

  sessions = 0
  for line in out.output.decode('utf-8').split("\n"):
    c = line.split(',')
    if len(c) == 6:
      # log.debug(f"peerbook entry6: {c}")
      (address,peer_name,listen_add,connections,nat,last_update) = c
      conns_num = try_int(connections)

      log.debug(f"miner_name={miner_name} peer_name={peer_name} conns_num={conns_num}")
      if miner_name == peer_name and isinstance(conns_num, int):
        log.debug(f"p2p connections: {conns_num}")
        CONNECTIONS.labels('connections', miner_name, POD_NAME, NODE_NAME).set(conns_num)

    elif len(c) == 4:
      # local,remote,p2p,name
      # log.debug(f"peerbook entry4: {c}")
      if c[0] != 'local':
        sessions += 1
    elif len(c) == 1:
      # log.debug(f"peerbook entry1: {c}")
      # listen_addrs
      pass
    else:
      log.debug(f"could not understand peer book line: {c}")

  log.debug(f"p2p sessions: {sessions}")
  SESSIONS.labels('sessions', miner_name, POD_NAME, NODE_NAME).set(sessions)

def collect_ledger_validators(miner_name):
  # ledger validators output
  out = read_file('ledger_validators.csv')
  results = out.output.decode('utf-8').split("\n")

  if not results or not results[0] or "failed" in results[0]:
    log.warning(f"Failed to fetch 'ledger validators', results[0]={results[0]}")
    return

  # parse the ledger validators output
  for line in [x.rstrip("\r\n") for x in results]:
    c = line.split(',')
    #print(f"{len(c)} {c}")
    if len(c) == 10:
      if c[0] == 'name' and c[1] == 'owner_address':
        # header line
        continue

      (val_name,address,last_heartbeat,stake,status,version,tenure_penalty,dkg_penalty,performance_penalty,total_penalty) = c
      if miner_name == val_name:
        log.debug(f"have penalty line: {c}")
        tenure_penalty_val = try_float(tenure_penalty)
        dkg_penalty_val = try_float(dkg_penalty)
        performance_penalty_val = try_float(performance_penalty)
        total_penalty_val = try_float(total_penalty)
        least_heartbeat=try_float(last_heartbeat)

        log.info(f"L penalty: {total_penalty_val}")
        LEDGER_PENALTY.labels('ledger_penalties', 'tenure', miner_name, POD_NAME, NODE_NAME).set(tenure_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'dkg', miner_name, POD_NAME, NODE_NAME).set(dkg_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'performance', miner_name, POD_NAME, NODE_NAME).set(performance_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'total', miner_name, POD_NAME, NODE_NAME).set(total_penalty_val)
        BLOCKAGE.labels('last_heartbeat', miner_name, POD_NAME, NODE_NAME).set(last_heartbeat)

    elif len(line) == 0:
      # empty lines are fine
      pass
    else:
      log.warning(f"failed to grok line: {c}; section count: {len(c)}")


def collect_miner_version(miner_name):
  out = read_file('versions')
  results = out.output.decode('utf-8').split("\n")
  # sample output
  # $ docker exec validator miner versions
  # Installed versions:
  # * 0.1.48	permanent
  for line in results:
    if m := re.match('^\*\s+([\d\.]+)(.*)', line):
      miner_version = m.group(1)
      log.debug(f"found miner version: {miner_version}")
      VALIDATOR_VERSION.labels(miner_name, POD_NAME, NODE_NAME).info({'version': miner_version})


if __name__ == '__main__':
  prometheus_client.start_http_server(9825) # 9-VAL on your phone
  while True:
    try:
      log.info(f"Fetching stats from {STATS_DIR}...")
      stats()
    except ValueError as ex:
      log.error(f"stats loop failed.", exc_info=ex)
    # except docker.errors.APIError as ex:
    #   log.error(f"stats loop failed with a docker error.", exc_info=ex)

    # sleep 30 seconds
    time.sleep(UPDATE_PERIOD)
