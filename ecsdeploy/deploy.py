#!/usr/bin/env python

import argparse, boto3

class ApplyECS():

    def main(self, cluster, region, service, name):

        self.load(cluster, region, service, name)

    def load(self, cluster, region, service, name):

        client = boto3.client('ecs', region_name=region)

        if service is not None:
           result = client.describe_services(
                cluster=cluster,
                services=[
                    service,
                ]
            )
           if len(result['services']) == 0:
               print "No service found " + ' '.join(map(lambda f: f['reason'] + ' ' + f['arn'], result['failures']))
               exit(1)
           else:
               service1 = result['services'][0]
               taskdef = service1['taskDefinition']

        elif name is not None:
            result = client.list_task_definitions(
                            familyPrefix=name,
                            sort='DESC',
                            maxResults=1
                        )
            if len(result['taskDefinitionArns']) == 0:
               print "No service found " + ' '.join(map(lambda f: f['reason'] + ' ' + f['arn'], result['failures']))
               exit(1)
            else:
                taskdef = result['taskDefinitionArns'][0]

        print "Got task def: " + taskdef

        response = client.describe_task_definition(
                        taskDefinition=taskdef
                    )

        ##Todo - semantic versioning

        new_def = {
            'family': response['taskDefinition']['family'],
            'volumes': response['taskDefinition']['volumes'],
            'containerDefinitions': response['taskDefinition']['containerDefinitions'],
        }
        print new_def

        #Register Task Definition
        response = client.register_task_definition(**new_def)
        status =  response['ResponseMetadata']['HTTPStatusCode']
        if status == 200:
            print "Result of Update: " + response['taskDefinition']['taskDefinitionArn']
            updated_task = response['taskDefinition']['taskDefinitionArn']
        else:
            print "Error registering " + taskdef
            exit(1)

        if service is not None:
            print "Updating Service"
            response = client.update_service(
                cluster=cluster,
                taskDefinition=updated_task,
                service=service
            )
            status = response['ResponseMetadata']['HTTPStatusCode']
            if status == 200:
                print "Result of service update: " + response['service']['serviceArn']
            else:
                print "Error updating service " + service
                exit(1)

            ##Todo - monitor service to see if it comes up

if __name__ == '__main__':
    p = ApplyECS()

    parser = argparse.ArgumentParser(description='Deploys an updated version of a task or service to ECS')
    parser.add_argument('--cluster', help='name of the ecs cluster', default='default')
    parser.add_argument('--region', help='region in aws', default='us-east-1')
    parser.add_argument('--service', help='Name of the Service')
    parser.add_argument('--task', help='name of task')
    args = parser.parse_args()

    if(args.service is None and args.task is None):
        print "ERROR - Either a service or task name is required"
        exit(1)

    p.main(args.cluster, args.region, args.service, args.task)
