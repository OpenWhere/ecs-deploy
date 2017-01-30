#!/usr/bin/env python

import argparse
import logging
import os
import sys
import time
import botocore
import boto3
import copy

from ecsUpdate import ApplyECS
from multiprocessing.pool import ThreadPool
from multiprocessing import Queue

logging.basicConfig(format="%(asctime)s %(levelname)s [%(threadName)s] - %(message)s", stream=sys.stdout,
                    level=logging.INFO)


class ApplyCF:
    def __init__(self):
        self.success_status = ['CREATE_COMPLETE','UPDATE_COMPLETE']
        self.failed_status = ['CREATE_FAILED', 'ROLLBACK_IN_PROGRESS','ROLLBACK_FAILED','ROLLBACK_COMPLETE','UPDATE_ROLLBACK_IN_PROGRESS','UPDATE_ROLLBACK_FAILED','UPDATE_ROLLBACK_COMPLETE']
        self.q = Queue()

    def catfile(self, fn):
      with open(fn) as f:
        print f.read()

    def main(self, dir_, deployment_type, listener_port, elb_name_suffix, cf_params):

        file_dir = os.path.dirname(os.path.realpath(__file__))
        job_path = os.path.join(file_dir, dir_)

        self.load(job_path, deployment_type, listener_port, elb_name_suffix, cf_params)

    def load(self, job_path, deployment_type, listener_port, elb_name_suffix, cf_params):
        env = cf_params['env']
        region = cf_params['region']
        cluster = cf_params['cluster'] if 'cluster' in cf_params else 'lambda'

        cf_client = boto3.client('cloudformation', region_name=region)

        has_ecs_service = False if deployment_type != 'ecs_service' else True

        filenames = []
        for subdir, dirs, files in os.walk(job_path):
            for fn in files:
                filenames.append(os.path.join(subdir, fn))

        pool = ThreadPool(32)
        imap_result = pool.imap(self.process_cf_file, ((cf_client, cf_params, cluster, elb_name_suffix, env, fn, has_ecs_service, listener_port, region)
                            for idx, fn in enumerate(filenames)), chunksize=1)
        pool.close()
        pool.join()
        print("Completed update of %s" % job_path)
        contains_failure = False
        for i in range(len(filenames)):
            job_result = self.q.get()
            print job_result
            if "Failed" in job_result:
                contains_failure = True
            imap_result.next()
        if contains_failure:
            sys.exit(1)

    def process_cf_file(self, args):
        try:
            cf_client = args[0]
            cf_params_local = copy.deepcopy(args[1])
            cluster = args[2]
            elb_name_suffix = args[3]
            env = args[4]
            filename = args[5]
            has_ecs_service = args[6]
            listener_port = args[7]
            region = args[8]
            if has_ecs_service:
                elb_name = 'ecs-elb-' + cluster
                if elb_name_suffix is not None:
                    elb_name = "-".join([elb_name, elb_name_suffix])
                self.populate_ecs_service_params(cf_params_local, cluster, elb_name, env, region, listener_port)
            # Skip non-cf files
            ext = filename.split('.')[-1]
            if ext != 'template' and ext != 'yml':
                return
            name = filename.split('/')[-1].split('.')[0]
            logging.info("%s: Processing CloudFormation Template" % filename)
            cf_params_local['name'] = name
            parameters = [{'ParameterKey': 'name', 'ParameterValue': name}]
            if name is None or name in filename:
                with open(filename, 'r') as f_h:
                    try:
                        cf_template = f_h.read()
                    except:
                        logging.exception("%s: Error reading file." % (filename))
                        self.catfile(filename)
                        raise
                    validate_response = self.validate_template(cf_client, cf_template, filename)

                    service_name = "%s-%s-%s" % (env, name, cluster)
                    if elb_name_suffix is not None:
                        service_name = "-".join([service_name, elb_name_suffix])
                    cf_command = cf_client.create_stack
                    existing_stack_id = self.find_existing_stack(cf_client, cf_params_local, service_name)
                    if existing_stack_id is not None:
                        cf_command = cf_client.update_stack
                    self.populate_cf_params(cf_params_local, existing_stack_id, filename, parameters, validate_response)
                    logging.info("%s: Updating CloudFormation Stack" % (service_name))
                    try:
                        cf_response = cf_command(StackName=service_name, TemplateBody=cf_template, Parameters=parameters, Capabilities=["CAPABILITY_IAM"])
                        creating_stack_id = cf_response['StackId']
                        stack_status = self.wait_for_stack_creation(cf_client, creating_stack_id, service_name)
                    except botocore.exceptions.ClientError as e:
                        if e.response["Error"]["Message"] == 'No updates are to be performed.':
                            logging.info("%s: No updates to be performed, CF update succeeded." % service_name)
                        else:
                            raise
        except Exception as e:
            logging.error("%s: Error executing CloudFormation Stack" % filename)
            logging.exception(e)
            self.q.put("%s Failed" % filename)
            sys.exit(1)
        self.q.put("%s Succeeded" % filename)

    def f_init(self, q):
        self.q = q

    def populate_cf_params(self, cf_params, existing_stack_id, filename, parameters, validate_response):
        for cf_parameter in validate_response['Parameters']:
            if cf_parameter['ParameterKey'] not in cf_params:
                logging.warning("Parameter: %s is specified by template in %s but not specified after --cfparams" % (cf_parameter['ParameterKey'], filename))
                if existing_stack_id is not None:
                    logging.warning("Using previous value for %s" % cf_parameter['ParameterKey'])
                    parameters.append({'ParameterKey': cf_parameter['ParameterKey'], 'UsePreviousValue': True})
            else:
                parameters.append({'ParameterKey': cf_parameter['ParameterKey'], 'ParameterValue': cf_params[cf_parameter['ParameterKey']]})

    def find_existing_stack(self, cf_client, cf_params, service_name):
        existing_stack_id = None
        try:
            # There will be at most 1 stack returned if running because we are using the stack name instead of ID/ARN
            existing_stacks = cf_client.describe_stacks(StackName=service_name)
            if existing_stacks is not None and len(existing_stacks) > 0:
                existing_stack_id = existing_stacks['Stacks'][0]['StackId']
                for parameter in existing_stacks['Stacks'][0]['Parameters']:
                    if parameter['ParameterKey'] == 'priority':
                        cf_params['priority'] = parameter['ParameterValue']
                        break
        except botocore.exceptions.ClientError as ce:
            logging.info("Stack name: %s not found, creating instead of updating" % service_name)
        return existing_stack_id

    def validate_template(self, cf_client, cf_template, filename):
        validate_response = {}
        try:
            validate_response = cf_client.validate_template(TemplateBody=cf_template)
            logging.info("CloudFormation template validated")
        except Exception as e:
            logging.error("%s: Error validating file." % filename)
            logging.error(validate_response)
            logging.exception(e)
            raise
        return validate_response

    def restart_tasks(self, cf_client, existing_stack_id, region, cluster):
        stack_resources = cf_client.describe_stack_resources(StackName=existing_stack_id)
        for resource in stack_resources['StackResources']:
            if resource['ResourceType'] == "AWS::ECS::TaskDefinition":
                task_definition_arn = resource['PhysicalResourceId']
            if resource['ResourceType'] == "AWS::ECS::Service":
                service_arn = resource['PhysicalResourceId']

        ecs_client = boto3.client('ecs', region_name=region)
        describe_task_response = ecs_client.describe_task_definition(taskDefinition=task_definition_arn)
        new_task = describe_task_response['taskDefinition']
        new_task.pop('requiresAttributes')
        new_task.pop('revision')
        new_task.pop('status')
        new_task.pop('taskDefinitionArn')
        register_task_response = ecs_client.register_task_definition(**new_task)

        update_service_response = ecs_client.update_service(cluster=cluster, service=service_arn, taskDefinition=register_task_response['taskDefinition']['taskDefinitionArn'])
        update_status_code = update_service_response['ResponseMetadata']['HTTPStatusCode']
        logging.info("ECS Task registration complete, status code: %d" % update_status_code)
        if update_status_code >= 400:
            sys.exit(1)

    def wait_for_stack_creation(self, cf_client, creating_stack_id, service_name):
        while True:
            time.sleep(10)
            try:
                describe_stacks_response = cf_client.describe_stacks(StackName=creating_stack_id)
                stack_status = describe_stacks_response['Stacks'][0]['StackStatus']
                if stack_status in self.success_status:
                    logging.info("%s: Stack update complete, status: %s" % (service_name, stack_status))
                    break
                elif stack_status in self.failed_status:
                    logging.error("%s: Stack update failed, status: %s" % (service_name, stack_status))
                    sys.exit(1)
                else:
                    logging.info("%s: Stack update in progress, status: %s" % (service_name, stack_status))
            except Exception as e:
                logging.error("%s: CloudFormation executed OK but stack was not created/updated." % service_name)
                logging.exception(e)
                raise
        return stack_status

    def populate_ecs_service_params(self, cf_params, cluster, elb_name, env, region, listener_port):
        elb_client = boto3.client('elbv2', region_name=region)
        balancer_arn, vpc_id = ApplyECS.get_load_balancer(elb_client, elb_name, cluster, env)
        listener_arn = ApplyECS.get_elb_listener(elb_client, balancer_arn, port=listener_port)
        cf_params['vpcid'] = vpc_id
        cf_params['listenerarn'] = listener_arn
        response = elb_client.describe_rules(ListenerArn=listener_arn)
        rules = response['Rules']
        existing_priorities = set([rule['Priority'] for rule in rules])
        if len(existing_priorities) >= 11:
            logging.error("Listener %s already has %d rules, cannot add more services" % (listener_arn, len(existing_priorities)))
            sys.exit(1)
        for i in range(10, 21):
            if str(i) not in existing_priorities:
                cf_params['priority'] = str(i)
                break

def argv_to_dict(args):
    argsdict = {}
    for farg in args:
        if farg.startswith('--'):
            key = farg[2:]
        else:
            value = farg
            argsdict[key] = value
    return argsdict


def validate_cf_params(args, cf_params):
    if args.deployment_type != 'ecs_service' and args.deployment_type != 'ecs_task' and args.deployment_type != 'lambda':
        logging.error("--deployment_type must be of the values: ecs_service, ecs_task, lambda")
        sys.exit(1)

    if 'env' not in cf_params:
            logging.error("--cfparams must contain --env [value]")
            sys.exit(1)
    if 'region' not in cf_params:
            logging.error("--cfparams must contain --region [value]")
            sys.exit(1)
    if args.deployment_type == 'ecs_service' or args.deployment_type == 'ecs_task':
        if 'cluster' not in cf_params:
            logging.error("--cfparams must contain --cluster [value]")
            sys.exit(1)


if __name__ == '__main__':
    p = ApplyCF()
    print(sys.argv)

    parser = argparse.ArgumentParser(description='Executes CloudFormation templates to create / update ECS related resources')
    parser.add_argument('--dir', help='relative directory name of service and task definitions', default='ecs')
    parser.add_argument('--deployment_type', help='Specify type of CF being deployed, valid values: ecs_service, ecs_task, lambda', default='ecs_service')
    parser.add_argument('--listener-port', help='Protocol of ALB listener to register service with', default=80)
    parser.add_argument('--elb-name-suffix', help='Append to default ALB name when finding ALB to assign this service to', default=None)
    parser.add_argument('--cfparams', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cf_params = argv_to_dict(args.cfparams)
    validate_cf_params(args, cf_params)
    p.main(args.dir, args.deployment_type, int(args.listener_port), args.elb_name_suffix, cf_params)
