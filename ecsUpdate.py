#!/usr/bin/env python

import os, json, argparse, boto3, sys

def remove_nulls(d):
    return {k: v for k, v in d.iteritems() if v is not None}


class ApplyECS():

    def main(self, cluster, region, name, env, type, dir_):

        #Register Tasks
        if 'all' in type or 'task' in type:
            self.load(cluster, region, name, env, dir_, ApplyECS.register_task)

        #Services must be done after tasks
        if 'all' in type or 'service' in type:
            self.load(cluster, region, name, env, dir_, ApplyECS.register_service)

    def load(self,cluster, region, name, env, dir_, handle_file):

        client = boto3.client('ecs', region_name=region)

        file_dir = os.path.dirname(os.path.realpath(__file__))
        job_path = os.path.join(file_dir, dir_)

        for subdir, dirs, files in os.walk(job_path):
            for fn in files:
                filename = os.path.join(subdir, fn)

                # Skip non-json files
                ext = filename.split('.')[-1]
                if ext != 'json':
                    continue

                if name is None or name in filename:
                    print('Filename is %s' % filename)
                    with open(filename, 'r') as f_h:
                        ecs_json = json.loads(f_h.read(), object_hook=remove_nulls)

                        handle_file(client, cluster, ecs_json, env, region, filename)


    @staticmethod
    def register_task(client, cluster, ecs_json, env, region, filename):
        if 'ecs_tasks' in filename:
            print "Submitting - " + filename
            if env is not None:
                ecs_json['family'] = ecs_json['family'] + '-' + env
                ApplyECS.update_container_tags(ecs_json, env, region)
            response = client.register_task_definition(**ecs_json)
            status =  response['ResponseMetadata']['HTTPStatusCode']
            if status == 200:
                print "Result of load: " + response['taskDefinition']['taskDefinitionArn']
            else:
                print "Error uploading " + filename

    @staticmethod
    def register_service(client, cluster, ecs_json, env, region, filename):
        if 'ecs_services' in filename:
            print "Submitting - " + filename
            ecs_json['cluster'] = cluster
            if env is not None:
                ecs_json['taskDefinition'] = ecs_json['taskDefinition'] + '-' + env
            try:
                # convert to named paramters
                response = client.create_service(**ecs_json)
            except Exception as e:
                print "Error creating:", e.message
                print "Attempting to update service"
                ecs_json['service'] = ecs_json['serviceName']
                del ecs_json['serviceName']
                response = client.update_service(**ecs_json)
            status = response['ResponseMetadata']['HTTPStatusCode']
            if status == 200:
                print "Result of load: " + response['service']['serviceArn']
            else:
                print "Error uploading " + filename



    @staticmethod
    def update_container_tags(task_json, env, region):
        for container in task_json['containerDefinitions']:
            image = container["image"]
            if 'ENV' in image:
                container["image"] = image.replace('ENV', env)
            env_param = container['environment']
            for var in env_param:
                name = var['name']
                value = var['value']
                if value.startswith('$'):
                    var['value'] = os.environ[value.lstrip('$')]
                if 'ENV' in value:
                    var['value'] = value.replace('ENV', env)
                elif 'REGION' in value:
                    var['value'] = value.replace('REGION', region)

            if 'command' in container:
                cmd_param = container['command']
                for i, item in enumerate(cmd_param):
                    if 'ENV' in item:
                        cmd_param[i] = item.replace('ENV', env)
                    elif 'REGION' in item:
                        cmd_param[i] = item.replace('REGION', region)


if __name__ == '__main__':
    p = ApplyECS()

    parser = argparse.ArgumentParser(description='Uploads / Updates ECS Task & Service Definitions to an ECS Cluster')
    parser.add_argument('--cluster', help='name of the ecs cluster', default='default')
    parser.add_argument('--env', help='environment name to append to tasks', default='dev')
    parser.add_argument('--region', help='region in aws', default='us-east-1')
    parser.add_argument('--name', help='name of task or service')
    parser.add_argument('--type', help='name of task or service', default='all')
    parser.add_argument('--dir', help='relative directory name of service and task definitions', default='ecs')
    args = parser.parse_args()

    p.main(args.cluster, args.region, args.name, args.env, args.type, args.dir)
