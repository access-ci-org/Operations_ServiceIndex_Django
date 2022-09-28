#!/bin/bash -x

# docker system prune -a

# Development laptop one container
docker build --tag=combo --file=provision/combo/Dockerfile .
docker run -it -u root -p 8443:8443 -e PGHOST=192.168.99.68 --rm combo:latest

# Development laptop two containers
docker build --no-cache --tag=opsreg --file=provision/web/Dockerfile .
docker build --no-cache --tag=nginx --file=provision/nginx/Dockerfile .
docker compose -f provision/docker-compose.yml create
docker compose -f provision/docker-compose.yml start
