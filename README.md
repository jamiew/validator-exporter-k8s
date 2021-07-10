# validator-exporter-k8s

Prometheus exporter for a [Helium validator)](https://github.com/helium/miner), specifically one running inside a Kubernetes (k8s) cluster configured using [caseypugh/helium-validator-k8s](https://github.com/caseypugh/helium-validator-k8s). 

Forked from [tedder/miner_exporter](https://github.com/tedder/miner_exporter) - thank you for sharing your work. The original scrapes metrics directly from a Docker container; to be Kubernetes-compatible, this fork scrapes from static files exported by the validator container. When possible we'll switch to using the validator's JSON-RPC, and these two forks can likely be merged.

Docker builds of this repository are automatically build and published to Docker Hub: [jamiedubs/validator-exporter](https://hub.docker.com/r/jamiedubs/validator-exporter)

Note [port 9825 is the 'reserved' port for this specific exporter](https://github.com/prometheus/prometheus/wiki/Default-port-allocations). Feel free to use whatever you like, of course, but you won't be able to dial 9VAL on your phone.

## Running in production

[helium-validator-k8s](https://github.com/caseypugh/helium-validator-k8s) is setup to use this image out-of-the-box. To see how to configure it, check out that repo's [validator.yml config](https://github.com/caseypugh/helium-validator-k8s/blob/main/k8s/validator.yml)

## Running locally

On the miner machine, install python3, [setup a venv](https://docs.python.org/3/library/venv.html) if you'd like, then:

```
pip install -r requirements.txt
```

Then, if you're connected to a [helium-validators kubernetes cluster](https://github.com/caseypugh/helium-validators), you can do a quick test using:

```
./save-stats.sh
```
```

This captures stats from the `validator-0` pod and then tries to serve them using our local `validator-exporter.py` prometheus endpoint


Then run the exporter, with some default ENV variables normally exposed by the k8s cluster:

```
./test-run.sh
```

## Configuration

The following have valid defaults, but you can change them:

```
DEBUG # set to 1 to show additional logging
UPDATE_PERIOD  # seconds between scrapes, int
STATS_DIR # where the stats files are saved; test run uses ./stats
API_BASE_URL # URL for Helium API. For testnet, set to "https://testnet-api.helium.wtf/v1"
ENABLE_RPC # opt in to using the RPC API with a truthy value (defaults to falsey value until `exec` calls are fully replaced).
```

## Build on Docker Hub (CI)

This repository has a GitHub action to automatically build a new image and push to [Docker Hub](https://hub.docker.com/r/jamiedubs/validator-exporter) on every commit (with no real test suite!). 

To configure on your own fork, create GitHub secrets for `DOCKER_USERNAME` and `DOCKER_PASSWORD`. For the password, use a [Docker Hub access token](https://hub.docker.com/settings/security)

## License

MIT

Pull requests welcome!
