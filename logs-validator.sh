#!/bin/sh
while [ 1 ]; do
	docker exec validator tail -n0 -F /var/data/log/console.log /var/data/log/error.log /var/data/log/crash.log
  sleep 10
done
