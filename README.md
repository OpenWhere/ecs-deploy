# ecs-deploy
Automate Deployment of AWS ECS (Elastic Container Service) Tasks and Services

This is a simple python script which allows you to update the deployment of new versions of ECS Tasks and Services. This script assumes you have another build process releasing the new containers. This script then allows you to automatically bump your Task or Service to the new Docker tag or version.

## Usage
`pip install boto3`
`python deploy.py --help`

## Example
Bump a task version `deploy.py --cluster your-cluster --region us-east-1 --task task-name`
Bump a service version `deploy.py --cluster your-cluster --region us-east-1 --service service-name`

##AWS Credentials
This script assumes you have exposed your AWS credentials by one of the typical means, env variables, ~/.aws/credentials, or an IAM Role.
https://github.com/boto/boto3


##Credits
This script was inspired by https://github.com/silinternational/ecs-deploy. It was created independently as we needed to manage the deployment of tasks and not just services and prefer to work in python for maintainability of our DevOps automation vs bash. 
