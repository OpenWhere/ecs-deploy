FROM	python:2.7.11-slim

RUN pip install  --no-cache-dir boto3
 
WORKDIR /usr/src/app
COPY deploy.py /usr/src/app/

ENTRYPOINT [ "python", "./deploy.py" ]
