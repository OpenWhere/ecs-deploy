#!/bin/bash
#
# Script to promote an image from develop to release repository.
#
# $1 - tag of the image, defaults to latest

set -e

IMAGE_NAME=ecs-deploy
TAG=${1:-latest}

DOCKER_VERSION=`docker --version | cut -f3 | cut -d '.' -f2`
[ ${DOCKER_VERSION} -lt 12 ] && TAG_FLAG='-f' || TAG_FLAG=''

$(aws ecr get-login)
docker tag ${TAG_FLAG} 639193537090.dkr.ecr.us-east-1.amazonaws.com/develop/${IMAGE_NAME}:${TAG} 639193537090.dkr.ecr.us-east-1.amazonaws.com/release/${IMAGE_NAME}:${TAG}
docker push 639193537090.dkr.ecr.us-east-1.amazonaws.com/release/${IMAGE_NAME}:${TAG}


