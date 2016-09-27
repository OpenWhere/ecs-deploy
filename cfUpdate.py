#!/usr/bin/env python

import argparse
import boto3
import logging
import os
import sys
import time

from ecsUpdate import ApplyECS

logging.basicConfig(format="%(asctime)s %(levelname)s [%(threadName)s] - %(message)s", stream=sys.stdout,
                    level=logging.INFO)


class ApplyCF:
    def __init__(self):
        self.success_status = ['CREATE_COMPLETE','UPDATE_COMPLETE']
        self.failed_status = ['CREATE_FAILED', 'ROLLBACK_IN_PROGRESS','ROLLBACK_FAILED','ROLLBACK_COMPLETE','UPDATE_ROLLBACK_IN_PROGRESS','UPDATE_ROLLBACK_FAILED','UPDATE_ROLLBACK_COMPLETE']

    def catfile(self, fn):
      with open(fn) as f:
        print f.read()

    def main(self, dir_, cf_params):

        file_dir = os.path.dirname(os.path.realpath(__file__))
        job_path = os.path.join(file_dir, dir_)

        self.load(job_path, cf_params)

    def load(self, job_path, cf_params):
        name = cf_params['name']
        env = cf_params['env']
        cluster = cf_params['cluster']
        region = cf_params['region']
        elb_name = 'ecs-elb-' + cluster
        cf_client = boto3.client('cloudformation', region_name=region)

        self.extract_common_ecs_params(cf_params, cluster, elb_name, env, region)

        for subdir, dirs, files in os.walk(job_path):
            for fn in files:
                filename = os.path.join(subdir, fn)

                # Skip non-cf files
                ext = filename.split('.')[-1]
                if ext != 'template':
                    continue
                name = filename.split('/')[-1].split('.')[0]
                logging.info("Processing CloudFormation Template: " + filename)
                parameters = [{'ParameterKey': 'name', 'ParameterValue': name}]

                if name is None or name in filename:
                    with open(filename, 'r') as f_h:
                        try:
                            cf_template = f_h.read()
                        except:
                            logging.exception("Error reading file %s " % filename)
                            self.catfile(filename)
                            raise
                        validate_response = {}
                        try:
                            validate_response = cf_client.validate_template(TemplateBody=cf_template)
                            logging.info("CloudFormation template validated")
                        except Exception as e:
                            logging.error("Error validating file: %s" % filename)
                            logging.error(validate_response)
                            logging.exception(e)
                            sys.exit(1)

                        try:
                            for cf_parameter in validate_response['Parameters']:
                                if cf_parameter['ParameterKey'] not in cf_params:
                                    logging.warning("Parameter: %s is specified by template in %s but not specified after --cfparams" % (filename, cf_parameter['ParameterKey']))
                                parameters.append({'ParameterKey': cf_parameter['ParameterKey'],
                                                   'ParameterValue': cf_params[cf_parameter['ParameterKey']]})
                            service_name = "%s-%s-%s" % (env, name, cluster)
                            existing_stacks = cf_client.list_stacks()
                            cf_command = cf_client.create_stack
                            for stack in existing_stacks['StackSummaries']:
                                if stack['StackName'] == service_name and stack['StackStatus'] != 'DELETE_COMPLETE' :
                                    cf_command = cf_client.update_stack
                                    break
                            logging.info("Updating CloudFormation Stack: " + service_name)
                            cf_response = cf_command(StackName=service_name, TemplateBody=cf_template, Parameters=parameters, Capabilities=["CAPABILITY_IAM"])
                        except Exception as e:
                            logging.error("Error executing CloudFormation: %s" % filename)
                            logging.exception(e)
                            sys.exit(1)
                        logging.info(cf_response)

                        while True:
                            time.sleep(5)

                            try:
                                describe_stacks_response = cf_client.describe_stacks(StackName=service_name)
                                stack_status = describe_stacks_response['Stacks'][0]['StackStatus']
                                if stack_status in self.success_status:
                                    logging.info("Stack create/update complete, status: %s" % stack_status)
                                    sys.exit(0)
                                elif stack_status in self.failed_status:
                                    logging.error("Stack create/update failed, status: %s" % stack_status)
                                    sys.exit(1)
                            except Exception as e:
                                logging.error("CloudFormation executed OK but stack was not created/updated: %s" % service_name)
                                logging.exception(e)
                                sys.exit(1)


    def extract_common_ecs_params(self, cf_params, cluster, elb_name, env, region):
        elb_client = boto3.client('elbv2', region_name=region)
        balancer_arn, vpc_id = ApplyECS.get_load_balancer(elb_client, elb_name, cluster, env)
        listener_arn = ApplyECS.get_elb_listener(elb_client, balancer_arn)
        cf_params['vpcid'] = vpc_id
        cf_params['listenerarn'] = listener_arn
        response = elb_client.describe_rules(ListenerArn=listener_arn)
        rules = response['Rules']
        top_priority = max([r['Priority'] if r['Priority'] != 'default' else "0" for r in rules])
        cf_params['priority'] = str(int(top_priority) + 1)


def argv_to_dict(args):
    argsdict = {}
    for farg in args:
        if farg.startswith('--'):
            key = farg[2:]
        else:
            value = farg
            argsdict[key] = value
    return argsdict

if __name__ == '__main__':
    p = ApplyCF()
    print(sys.argv)

    parser = argparse.ArgumentParser(description='Executes CloudFormation templates to create / update ECS related resources')
    parser.add_argument('--dir', help='relative directory name of service and task definitions', default='ecs')
    parser.add_argument('--cfparams', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cf_params = argv_to_dict(args.cfparams)

    p.main(args.dir, cf_params)
