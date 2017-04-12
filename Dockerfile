FROM	python:2.7.11-alpine

RUN pip install --no-cache-dir boto3 && mkdir ~/.aws
 
WORKDIR /usr/src/app
VOLUME ["~/.aws"]
RUN mkdir /usr/src/app/ecs
VOLUME ["ecs"]
COPY ecsdeploy/deploy.py /usr/src/app/
COPY ecsdeploy/ecsUpdate.py /usr/src/app/
COPY ecsdeploy/cfUpdate.py /usr/src/app/

ENTRYPOINT [ "python" ]
CMD ["./ecsUpdate.py"]
