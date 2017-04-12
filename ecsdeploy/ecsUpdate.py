#!/usr/bin/env python

import os, json, argparse, boto3, sys
import logging

logging.basicConfig(format="%(asctime)s %(levelname)s [%(threadName)s] - %(message)s", stream=sys.stdout,
                    level=logging.INFO)

def remove_nulls(d):
    return {k: v for k, v in d.iteritems() if v is not None}

def rule_matches(r, name):
    conditions = r['Conditions']
    for c in conditions:
        values = c['Values']
        for v in values:
            rule = "/%s/*" % name
            if rule == v:
                return True
    return False


class ApplyECS():

    def catfile(self, fn):
      with open(fn) as f:
        print f.read()

    def main(self, cluster, region, name, env, type, dir_, healthcheckpath):

        file_dir = os.path.dirname(os.path.realpath(__file__))
        job_path = os.path.join(file_dir, dir_)

        #Register Tasks
        if 'all' in type or 'task' in type:
            logging.info("Checking directory %s/ecs_tasks for tasks" % job_path)
            self.load(cluster, region, name, env, job_path, healthcheckpath, ApplyECS.register_task)

        #Services must be done after tasks
        if 'all' in type or 'service' in type:
            logging.info("Checking directory %s/ecs_services for services" % job_path)
            self.load(cluster, region, name, env, job_path, healthcheckpath, ApplyECS.register_service)

    def load(self,cluster, region, name, env, job_path, healthcheckpath, handle_file):

        client = boto3.client('ecs', region_name=region)
        elb_client = boto3.client('elbv2', region_name=region)

        count = 0
        for subdir, dirs, files in os.walk(job_path):
            for fn in files:
                filename = os.path.join(subdir, fn)

                # Skip non-json files
                ext = filename.split('.')[-1]
                if ext != 'json':
                    continue

                if name is None or name in filename:
                    with open(filename, 'r') as f_h:
                        try:
                            ecs_json = json.loads(f_h.read(), object_hook=remove_nulls)
                            count += 1
                            handle_file(client, cluster, ecs_json, env, region, filename, count, elb_client, healthcheckpath)
                        except:
                            logging.exception("Error reading file %s " % filename)
                            self.catfile(filename)
                            raise


    @staticmethod
    def register_task(client, cluster, ecs_json, env, region, filename, count, elb_client, healthcheckpath):
        if 'ecs_tasks' in filename:
            logging.info("Submitting - " + filename)
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
    def register_service(client, cluster, ecs_json, env, region, filename, count, elb_client, healthcheckpath):
        if 'ecs_services' in filename:
            logging.info("Submitting - " + filename)
            ecs_json['cluster'] = cluster
            if env is not None:
                ecs_json['taskDefinition'] = ecs_json['taskDefinition'] + '-' + env
            try:
                # Perform all ALB magic if a load balancer service

                if 'loadBalancers' in ecs_json:
                    lb = ecs_json['loadBalancers'][0]
                    elb_name = lb['loadBalancerName']
                    container_name = lb['containerName']
                    service_name = ApplyECS.update_name_for_config(ecs_json['serviceName'], cluster, env)
                    #Correct role to handle multiple per account
                    ecs_json['role'] = ApplyECS.update_name_for_config(ecs_json['role'], cluster, env)

                    target_arn = ApplyECS.configure_alb_and_rules(client=elb_client, elb_name=elb_name,
                                                                  service_name=service_name,
                                                                  container_name=container_name, cluster=cluster,
                                                                  env=env, priority=count,
                                                                  health_check_path=healthcheckpath)

                    ecs_json['serviceName'] = service_name
                    lb['targetGroupArn'] = target_arn

                    #delete lB as can't have both
                    lb.pop('loadBalancerName', None)

                # convert to named paramters
                response = client.create_service(**ecs_json)
            except Exception as e:
                logging.exception("Did not create %s" % e.message)
                logging.info("Attempting to update an existing service")
                ecs_json['service'] = ecs_json['serviceName']
                del ecs_json['serviceName']
                if 'loadBalancers' in ecs_json:
                    del ecs_json['loadBalancers']
                if 'role' in ecs_json:
                    del ecs_json['role']
                response = client.update_service(**ecs_json)
            status = response['ResponseMetadata']['HTTPStatusCode']
            if status == 200:
                logging.info("Result of load: " + response['service']['serviceArn'])
            else:
                logging.error("Error uploading " + filename)

    @staticmethod
    def configure_alb_and_rules(client, elb_name, service_name, container_name, cluster, env, priority, health_check_path, listener_proto='HTTP'):
        # 1. Get the ALB
        balancer_arn, vpc_id = ApplyECS.get_load_balancer(client, elb_name, cluster, env)
        # 2. Find the listener
        listener_arn = ApplyECS.get_elb_listener(client, balancer_arn, protocol=listener_proto)
        # 3. Check or Create Target Group
        target_arn = ApplyECS.get_or_create_elb_target_group(client, elb_arn=balancer_arn, vpc_id=vpc_id,
                                                             cluster=cluster, env=env,
                                                             service_name=service_name,
                                                             health_check_path=health_check_path)
        # 4. Check or Create Routing Rule
        ApplyECS.check_or_create_rule(client, listener_arn, target_arn, container_name, priority)
        return target_arn

    @staticmethod
    def get_load_balancer(client, elb_name, cluster, env):

        env_elb_name = ApplyECS.update_name_for_config(elb_name, cluster, env)
        balancer_response = client.describe_load_balancers(
            Names=[
                env_elb_name
            ]
        )
        balancers = [ x for x in balancer_response['LoadBalancers'] if x['LoadBalancerName'] == env_elb_name]
        if len(balancers) > 0:
            balancer = balancers[0]
            balancer_arn = balancer["LoadBalancerArn"]
            vpc_id = balancer["VpcId"]
            logging.info("Found ELB %s with ARN: %s" % (env_elb_name, balancer))
            return balancer_arn, vpc_id
        else:
            logging.error("No ELB found with name %s " % elb_name)
            sys.exit(1)

    @staticmethod
    def get_elb_listener(client, elb_arn, port=80):
        logging.info("Checking for listeners")
        response = client.describe_listeners(
            LoadBalancerArn=elb_arn
        )
        listeners = response['Listeners']
        if len(listeners) > 0:
            listener_list = [x for x in listeners if x['Port'] == port]
            if len(listener_list) == 0:
                logging.error("No listeners found for ELB %s on port %d" % (elb_arn, port))
                sys.exit(1)
            listener = listener_list[0]
            listener_arn = listener['ListenerArn']
            logging.info("Found Listener with ARN: %s" % listener_arn)
            return listener_arn
        else:
            logging.error("No listeners found for ELB %s " % elb_arn)
            sys.exit(1)

    @staticmethod
    def get_or_create_elb_target_group(client, elb_arn, vpc_id, cluster, env, service_name, health_check_path):

        env_service_name = ApplyECS.update_name_for_config(service_name, cluster, env)
        logging.info("Checking for target group")
        response = client.describe_target_groups(
            LoadBalancerArn=elb_arn,
        )
        target_groups =  [ x for x in response['TargetGroups'] if x['TargetGroupName'] == env_service_name]
        if len(target_groups) == 0:
            logging.info("No target group found for %s, creating" % env_service_name)
            response = client.create_target_group(
                Name=env_service_name,
                Protocol='HTTP',
                Port=80, # TODO - way not to hardcode this?
                VpcId=vpc_id,
                HealthCheckPath=health_check_path
            )
            target = response['TargetGroups'][0]
            target_arn = target['TargetGroupArn']
            logging.info("Created TargetGroup %s with ARN %s" % (env_service_name, target_arn))
            return target_arn
        else:
            target = target_groups[0]
            target_arn = target['TargetGroupArn']
            logging.info("Found TargetGroup %s with ARN %s, updating" % (env_service_name, target_arn))
            response = client.modify_target_group(
                TargetGroupArn=target_arn,
                HealthCheckProtocol='HTTP',
                HealthCheckPath=health_check_path
            )
            logging.info("Update response: %d to ARN %s" % (response['ResponseMetadata']['HTTPStatusCode'], target_arn))
            return target_arn

    @staticmethod
    def check_or_create_rule(client, listener_arn, target_arn, rule_name,  priority):
        response = client.describe_rules(
            ListenerArn=listener_arn
        )
        rules = response['Rules']
        top_priority = max([r['Priority'] if r['Priority'] != 'default' else "0" for r in rules])
        matching_rules = [r for r in rules if rule_matches(r, rule_name)]
        if len(matching_rules) == 0:
            logging.info('No rule found, creating rule for %s' % rule_name)
            c_response = client.create_rule(
                ListenerArn=listener_arn,
                Conditions=[
                    {
                        'Field': 'path-pattern',
                        'Values': [
                            '/%s/*' % rule_name,
                        ]
                    },
                ],
                Priority=priority + int(top_priority),
                Actions=[
                    {
                        'Type': 'forward',
                        'TargetGroupArn': target_arn
                    },
                ]
            )
            logging.info("Created rule %s for container %s" % (c_response['Rules'][0]['RuleArn'], rule_name))
        else:
            # TODO - Attempt update?
            rule = matching_rules[0]
            logging.info("Found rule %s for container %s" % (rule['RuleArn'], rule_name))

    @staticmethod
    def update_name_for_config(name, cluster, env):
        if 'ENV' in name:
            name = name.replace('ENV', env)
        if 'CLUSTER' in name:
            name = name.replace('CLUSTER', cluster)
        return name

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
    parser.add_argument('--healthcheckpath', help='path to use for target group health check', default='/') #TODO replace this is target group definition file
    args = parser.parse_args()

    p.main(args.cluster, args.region, args.name, args.env, args.type, args.dir, args.healthcheckpath)
