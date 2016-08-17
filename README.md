# ecs-deploy
Automate Deployment of AWS ECS (Elastic Container Service) Tasks and Services

This is a simple python script(s) which allows you to update the deployment of new versions of ECS Tasks and Services. This script assumes you have another build process releasing the new containers. This script then allows you to automatically bump your Task or Service to the new Docker tag or version.

This script also now handles TargetGroup and Rule creation with new AWS Application Load Balancers

##Note
The older deploy.py script is deprecated

## Usage
```python
pip install requirements.txt
docker run --volume ~/.aws:/root/.aws --volume ./ecs:/usr/src/app/ecs openwhere/ecs-deploy ./ecsUpdate.py --help
```

##Alternative Script
An alternative script creates or updates services and tasks based on task definitions in a folder structure. Use this if you also want the script to create from scratch not just update ECS Tasks and services.

We evoke this docker container during our other project build process in order to automatically deploy and update ECS tasks and services, and register them with the AWS Application Load Balancer. Tasks and services are checked inside the project to describe how the project will deployed to ECS. A diretory structure of `ecs/ecs_services`, `ecs/ecs_tasks` is assumed.

Run the script `docker run --volume ~/.aws:/root/.aws --volume ./ecs:/usr/src/app/ecs openwhere/ecs-deploy ./ecsUpdate.py --help`

You may also choose to pass AWS credentials using environment variables

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

##Registering with an Application Load Balancer
You must already have an Application Load balancer created. You must also have a listener created. Currently the listener assumes port 80 as there was no
easy way to put this in the service definition. I may improve this in the future. The script will find your load balancer and listener based on your service definition.
You must also already have an IAM Service role created for your ECS cluster to connect to the Application Load Balancer. See the AWS docs.

```javascript
{
  "serviceName": "foo-service-CLUSTER",
  "taskDefinition": "foo-service",
  "desiredCount": 1,
  "loadBalancers": [
      {
          "loadBalancerName": "ecs-elb-CLUSTER",
          "containerName": "foo-service",
          "containerPort": 5000
      }
  ],
  "role": "ecsServiceRole-CLUSTER"
}
```

In this example, if your cluster is named "dev" the script will look for a Target Group called "foo-service-dev". If it does not exist it will attempt to create it.
Make sure you have proper IAM rights. On subsequent runs it will look up this definition. It will also register a rule based on the container name, in this case
``/foo-service/*` where any calls to ``/foo-service` will route to the target group foo-service-dev running your container. This container name must match "name" inside
your task definition. Also be aware, currently AWS forwards on the full path ``/foo-service` to your contaner so you must handle that as part of your path.

The script will automatically look for CLUSTER or ENV in the serviceName, loadBalancerNAme, and role which allows you to use the same service definition as
part of a CI process for multiple environments and / or clusters.

Other things to note are service's relationship to an ELB or not are immutable. Therefore you must delete services or make services with a new name in order to change
ELB associations. The route rule may be updated at any time (however currently this script will only create not update).

##Credits
This script was inspired by https://github.com/silinternational/ecs-deploy. It was created independently as we needed to manage the deployment of tasks and not just services and prefer to work in python for maintainability of our DevOps automation vs bash. 

We have also made some custom improvements after working more with ECS in order to better manage ECS Tasks and Services across multiple environments.
