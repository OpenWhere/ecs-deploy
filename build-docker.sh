#!/bin/bash
#
# Script to build and upload a docker image for this project
#
# $1 - tag of the image, defaults to latest

set -e

IMAGE_NAME=ecs-deploy
TAG=${1:-latest}

DOCKER_VERSION=`docker --version | cut -f3 | cut -d '.' -f2`
[ ${DOCKER_VERSION} -lt 12 ] && TAG_FLAG='-f' || TAG_FLAG=''

docker build -t ${IMAGE_NAME} .
docker tag ${TAG_FLAG} ${IMAGE_NAME} openwhere/${IMAGE_NAME}:${TAG}
docker push openwhere/${IMAGE_NAME}:${TAG}

