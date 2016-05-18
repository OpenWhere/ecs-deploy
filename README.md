# ecs-deploy
Automate Deployment of AWS ECS (Elastic Container Service) Tasks and Services

This is a simple python script which allows you to update the deployment of new versions of ECS Tasks and Services. This script assumes you have another build process releasing the new containers. This script then allows you to automatically bump your Task or Service to the new Docker tag or version.

## Usage
```python
pip install boto3
python deploy.py --help
```

## Example
Bump a task version `deploy.py --cluster your-cluster --region us-east-1 --task task-name`
Bump a service version `deploy.py --cluster your-cluster --region us-east-1 --service service-name`

##Alternative Script
An alternative script creates or updates services and tasks based on task definitions in a folder structure. Use this if you also want the script to create from scratch not just update ECS Tasks and services.

We evoke this docker container during our other project build process in order to automatically deploy and update ECS tasks and services. Tasks and services are checked inside the project to describe how the project will deployed to ECS. A diretory structure of `ecs/ecs_services`, `ecs/ecs_tasks` is assumed.

Run the script `docker run --volume ~/.aws:/root/.aws --volume ./ecs:/usr/src/app/ecs openwhere/ecs-deploy ./ecsUpdate.py --help`

###Overriding environment variables
This script can automatically configure environment specific settings inside your task definitions. It will also namespace tasks by environment as tasks names are unique per account not VPC. `ENV` and `REGOION` are subsituted by default inside the `containerDefinitions.environment` section of a task definition as well as in the `containderDefinitions.image`

To override your own custom variable simply prefix the value with a `$` inside the task definition and provide the variable to docker via `-e`. For example

```
{
    "name": "MY_ENVIRONMENT_VARIABLE",
    "value": "$MY_ENVIRONMENT_VARIABLE"
}


docker run -e MY_ENVIRONMENT_VARIABLE=foo openwhere/ecs-deploy ./ecsUpdate.py -env dev -region us-east-1
```

Here is a full example of typical invocation:
`docker run --rm --volume ${PWD}/ecs:/usr/src/app/ecs -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID -e MY_ENVIRONMENT_VARIABLE=foo openwhere/ecs-deploy ./ecsUpdate.py --cluster analytics-pgp --env pgp --region us-east-1`

##AWS Credentials
This script assumes you have exposed your AWS credentials by one of the typical means, env variables, ~/.aws/credentials, or an IAM Role.
https://github.com/boto/boto3

Examples include, passing the environment variables:

`-e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID `

Mounting a volume (where environment_profile is your profile name or omitted to use the default):

` --volume ~/.aws:/root/.aws -e AWS_PROFILE=environment_profile`

##Credits
This script was inspired by https://github.com/silinternational/ecs-deploy. It was created independently as we needed to manage the deployment of tasks and not just services and prefer to work in python for maintainability of our DevOps automation vs bash. 

We have also made some custom improvements after working more with ECS in order to better manage ECS Tasks and Services across multiple environments.
