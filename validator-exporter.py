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
log.setLevel(logging.INFO)
log.info("validator-exporter starting up...!")

# where the validator container stashes its stats files
STATS_DIR = os.environ.get('STATS_DIR', '/var/data/stats')
log.info(f"STATS_DIR={STATS_DIR}")

# time to sleep between scrapes
UPDATE_PERIOD = int(os.environ.get('UPDATE_PERIOD', 30))
VALIDATOR_CONTAINER_NAME = os.environ.get('VALIDATOR_CONTAINER_NAME', 'validator')

# for testnet, https://testnet-api.helium.wtf/v1
API_BASE_URL = os.environ.get('API_BASE_URL', 'https://api.helium.io/v1')

# use the RPC calls where available. This means you have your RPC port open.
# Once all of the exec calls are replaced we can enable this by default.
ENABLE_RPC = os.environ.get('ENABLE_RPC', 0)

# prometheus exporter types Gauge,Counter,Summary,Histogram,Info and Enum
SCRAPE_TIME = prometheus_client.Summary('validator_scrape_time', 'Time spent collecting miner data')
CHAIN_STATS = prometheus_client.Gauge('chain_stats',
                              'Stats about the global chain', ['resource_type'])
VAL = prometheus_client.Gauge('validator_height',
                              "Height of the validator's blockchain",
                              ['resource_type','validator_name'])
INCON = prometheus_client.Gauge('validator_inconsensus',
                              'Is validator currently in consensus group',
                              ['validator_name'])
BLOCKAGE = prometheus_client.Gauge('validator_block_age',
                              'Age of the current block',
                             ['resource_type','validator_name'])
HBBFT_PERF = prometheus_client.Gauge('validator_hbbft_perf',
                              'HBBFT performance metrics from perf, only applies when in CG',
                             ['resource_type','subtype','validator_name'])
CONNECTIONS = prometheus_client.Gauge('validator_connections',
                              'Number of libp2p connections ',
                             ['resource_type','validator_name'])
SESSIONS = prometheus_client.Gauge('validator_sessions',
                              'Number of libp2p sessions',
                             ['resource_type','validator_name'])
LEDGER_PENALTY = prometheus_client.Gauge('validator_ledger',
                              'Validator performance metrics ',
                             ['resource_type', 'subtype','validator_name'])
VALIDATOR_VERSION = prometheus_client.Info('validator_version',
                              'Version number of the miner container',['validator_name'])
BALANCE = prometheus_client.Gauge('validator_api_balance',
                              'Balance of the validator owner account',['validator_name'])
UPTIME = prometheus_client.Gauge('validator_container_uptime',
                              'Time container has been at a given state',
                              ['state_type','validator_name'])
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
  log.debug(f"read_file dir={STATS_DIR} command={command}")
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

  # FIXME how to properly check for blank in python?
  # should we doing this somewhere else?
  if out == "" or type(out) == str:
    print(f"no data for print_keys, aborting")
    return

  printkeys = {}
  for line in out.output.split(b"\n"):
    strline = line.decode('utf-8')

    # := requires py3.8
    if m := re.match(r'{([^,]+),"([^"]+)"}.', strline):
      log.debug(m)
      k = m.group(1)
      v = m.group(2)
      log.debug(k,v)
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
  print("miner_facts...")
  print(miner_facts)
  hotspot_name_str = get_miner_name()
  print("hotspot_name_str...")
  print(hotspot_name_str)
  collect_miner_version(hotspot_name_str)
  collect_block_age(hotspot_name_str)
  collect_miner_height(hotspot_name_str)
  collect_chain_stats()
  collect_in_consensus(hotspot_name_str)
  collect_ledger_validators(hotspot_name_str)
  collect_peer_book(hotspot_name_str)
  collect_hbbft_performance(hotspot_name_str)
  collect_balance(miner_facts['address'], hotspot_name_str)

def safe_get_json(url):
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

def collect_balance(addr, miner_name):
  # should move pubkey to getfacts and then pass it in here
  #out = read_file('miner print_keys')
  #for line in out.output.decode('utf-8').split("\n"):
  #  if 'pubkey' in line:
  #    addr=line[9:60]
  api_validators = safe_get_json(f'{API_BASE_URL}/validators/{addr}')
  if not api_validators:
    log.error("validator fetch returned empty JSON")
    return
  elif not api_validators.get('data') or not api_validators['data'].get('owner'):
    log.error("could not find validator data owner in json")
    return
  owner = api_validators['data']['owner']

  api_accounts = safe_get_json(f'{API_BASE_URL}/accounts/{owner}')
  if not api_accounts:
    return
  if not api_accounts.get('data') or not api_accounts['data'].get('balance'):
    return
  balance = float(api_accounts['data']['balance'])/1E8
  #print(api_accounts)
  #print('balance',balance)
  BALANCE.labels(miner_name).set(balance)


def get_miner_name():
  # need to fix this. hotspot name really should only be queried once
  out = read_file('info_name')
  log.debug(out.output)
  hotspot_name = out.output.decode('utf-8').rstrip("\n")
  return hotspot_name

def collect_miner_height(miner_name):
  # grab the local blockchain height
  out = read_file('info_height')
  log.debug(out.output)
  txt = out.output.decode('utf-8').rstrip("\n")
  VAL.labels('Height', miner_name).set(out.output.split()[1])

def collect_in_consensus(miner_name):
  # check if currently in consensus group
  out = read_file('info_in_consensus')
  incon_txt = out.output.decode('utf-8').rstrip("\n")
  incon = 0
  if incon_txt == 'true':
    incon = 1
  log.info(f"in consensus? {incon} / {incon_txt}")
  INCON.labels(miner_name).set(incon)

def collect_block_age(miner_name):
  # collect current block age
  out = read_file('info_block_age')
  ## transform into a number
  age_val = try_int(out.output.decode('utf-8').rstrip("\n"))

  BLOCKAGE.labels('BlockAge', miner_name).set(age_val)
  log.debug(f"age: {age_val}")

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
    else:
      log.debug(f"wrong len ({len(c)}) + miner_name ({miner_name}) for hbbft: {c}")

    # always set these, that way they get reset when out of CG
    HBBFT_PERF.labels('hbbft_perf','Penalty', miner_name).set(hval.get('pen_val', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Total', miner_name).set(hval.get('bba_tot', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Votes', miner_name).set(hval.get('bba_votes', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Total', miner_name).set(hval.get('seen_tot', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Votes', miner_name).set(hval.get('seen_votes', 0))
    HBBFT_PERF.labels('hbbft_perf','BBA_Last', miner_name).set(hval.get('bba_last_val', 0))
    HBBFT_PERF.labels('hbbft_perf','Seen_Last', miner_name).set(hval.get('seen_last_val', 0))
    HBBFT_PERF.labels('hbbft_perf','Tenure', miner_name).set(hval.get('tenure', 0))

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
  for line in out.output.decode('utf-8').split("\r\n"):
    c = line.split(',')
    if len(c) == 6:
      log.debug(f"peerbook entry6: {c}")
      (address,peer_name,listen_add,connections,nat,last_update) = c
      conns_num = try_int(connections)

      if miner_name == peer_name and isinstance(conns_num, int):
        CONNECTIONS.labels('connections', miner_name).set(conns_num)

    elif len(c) == 4:
      # local,remote,p2p,name
      log.debug(f"peerbook entry4: {c}")
      if c[0] != 'local':
        sessions += 1
    elif len(c) == 1:
      log.debug(f"peerbook entry1: {c}")
      # listen_addrs
      pass
    else:
      log.warning(f"could not understand peer book line: {c}")

  log.debug(f"sess: {sessions}")
  SESSIONS.labels('sessions', miner_name).set(sessions)

def collect_ledger_validators(miner_name):
  # ledger validators output
  out = read_file('ledger_validators.csv')
  results = out.output.decode('utf-8').split("\n")
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
        log.debug(f"have pen line: {c}")
        tenure_penalty_val = try_float(tenure_penalty)
        dkg_penalty_val = try_float(dkg_penalty)
        performance_penalty_val = try_float(performance_penalty)
        total_penalty_val = try_float(total_penalty)
        least_heartbeat=try_float(last_heartbeat)

        log.info(f"L penalty: {total_penalty_val}")
        LEDGER_PENALTY.labels('ledger_penalties', 'tenure', miner_name).set(tenure_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'dkg', miner_name).set(dkg_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'performance', miner_name).set(performance_penalty_val)
        LEDGER_PENALTY.labels('ledger_penalties', 'total', miner_name).set(total_penalty_val)
        BLOCKAGE.labels('last_heartbeat', miner_name).set(last_heartbeat)

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
      log.info(f"found miner version: {miner_version}")
      VALIDATOR_VERSION.labels(miner_name).info({'version': miner_version})


if __name__ == '__main__':
  prometheus_client.start_http_server(9825) # 9-VAL on your phone
  while True:
    #log.warning("starting loop.")
    try:
      stats()
    except ValueError as ex:
      log.error(f"stats loop failed.", exc_info=ex)
    # except docker.errors.APIError as ex:
    #   log.error(f"stats loop failed with a docker error.", exc_info=ex)

    # sleep 30 seconds
    time.sleep(UPDATE_PERIOD)