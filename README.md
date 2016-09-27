# ecs-deploy
Automate Deployment of AWS ECS (Elastic Container Service) Tasks and Services


This is a simple python script(s) which allows you to update the deployment of new versions of ECS Tasks and Services. This script assumes you have another build process releasing the new containers. The script allows you to also initially update and Create ECS Task(s) and Service(s) definitions based on the task and services json definitions checked into your project (or anywhere else). We have found this the most effective method as we can fully automate the Continuous Integration and Delivery of ECS Tasks and Services. ECS applications can be laid down on top of an ECS cluster created via any other means. You can use this script if you want to create from scratch (not just update) ECS Tasks and Services in your cluster. This script is ideally invoked during the deploy process of your build process such from within Jenkins or CircleCI.

8/16 - This script also now supports TargetGroup and Rule creation with new AWS Application Load Balancers. This allows you to automatically route to ECS Services running on random ports in your ECS cluster without the need for something like consul! See [AWS Application Load Balancer](https://aws.amazon.com/elasticloadbalancing/applicationloadbalancer/)

###Note
The older deploy.py script is deprecated as we have determined this method less effective for initial roll out and continous delivery of service  / task updates.

There are two ways to define the services and tasks that get deployed into your environment: 1) json file definitions or 2) CloudFormation templates

## JSON File Definition Usage
```python
pip install requirements.txt
docker run --volume ~/.aws:/root/.aws --volume ./ecs:/usr/src/app/ecs openwhere/ecs-deploy:v1.3 ./ecsUpdate.py --help
```

We invoke this docker container during our other project build process in order to automatically deploy and update ECS tasks and services, and register them with the AWS Application Load Balancer. Tasks and Services are checked inside the project to determine how the project will deployed to ECS. In this way, your Task and Service adjustments are managed just like any other code change. A relative directory structure of `ecs/ecs_services`, `ecs/ecs_tasks` somewhere in your project is assumed for organizing the task and service definitions.

You may also choose to pass AWS credentials using Docker environment variables

## CloudFormation Usage
```python
pip install requirements.txt
docker run --volume ~/.aws:/root/.aws --volume ./ecs:/usr/src/app/ecs openwhere/ecs-deploy:v1.3 ./cfUpdate.py --cfparams --cluster ecs-cluster-name --name service-name --env dev --region us-east-1
```

As with the JSON file definition appraoch, this script is invoked during the build process to deploy and update ECS tasks, services and register them with the load balancer.  It can also create other AWS resources such as IAM Roles assiciated with tasks, and autoscaling targets, policies, and alarms and attach them to the ECS service.  `cfUpdate.py` will look inside the relative `ecs` directory for .template files which are assumed to be CloudFormation templates.  Like `ecsUpdate.py` it assumes there is an existing ApplicationLoadBalancer with a listener.

###Setting CloudFormation Parameters
The values after `--cfparams` are passed to the CloufFormation script.  These can be used to set any parameters in the CloudFormation script.  Four parameters are required after the --cfparams flag for any ECS Service and Task:
*--cluster: The name of the ECS cluster
*--name: The name of the service to create
*--env: The environment name, appended to the service to support having the same service in multiple environments within an account
*--region: The region in which to create the Service, Task and other resources


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
your task definition. Also be aware, currently AWS forwards on the full path ``/foo-service` to your container so you must handle that as part of your path.

The script will automatically look for CLUSTER or ENV in the serviceName, loadBalancerNAme, and role which allows you to use the same service definition as
part of a CI process for multiple environments and / or clusters.

Other things to note are service's relationship to an ELB or not are immutable. Therefore you must delete services or make services with a new name in order to change
ELB associations. The route rule may be updated at any time (however currently this script will only create not update).

##Credits
This script was inspired by https://github.com/silinternational/ecs-deploy. It was created independently as we needed to manage the deployment of tasks and not just services and prefer to work in python for maintainability of our DevOps automation vs bash. 

We have also made some custom improvements after working more with ECS in order to better manage ECS Tasks and Services across multiple environments.
