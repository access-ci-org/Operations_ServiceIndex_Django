#!/bin/bash -x

# docker system prune -a
docker build --no-cache --tag=opsreg --file=provision/web/Dockerfile .
docker build --no-cache --tag=nginx --file=provision/nginx/Dockerfile .
docker compose -f provision/docker-compose.yml create
docker compose -f provision/docker-compose.yml start
