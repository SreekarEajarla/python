pip install boto3 pyyaml
python aws_health_check.py /path/to/your/deployment.yaml

import boto3
import yaml
import sys

# Helper: Checkers for each component type
def check_rdsaurora(name, props):
    # Try to get a cluster by custom_cluster_name or database_name
    client = boto3.client('rds')
    cluster_id = props.get('custom_cluster_name', props.get('database_name', name))
    try:
        result = client.describe_db_clusters(DBClusterIdentifier=cluster_id)
        status = result['DBClusters'][0]['Status']
        healthy = status == 'available'
        print(f"RDSAuroraPostgres '{name}' [{cluster_id}] status: {status} (Healthy: {healthy})")
    except Exception as e:
        print(f"RDSAuroraPostgres '{name}' [{cluster_id}] ERROR: {str(e)}")

def check_sqs(name, props):
    client = boto3.client('sqs')
    try:
        # Try to guess queue by name (assumes queue name is the resource name)
        response = client.list_queues(QueueNamePrefix=name)
        queue_urls = response.get("QueueUrls", [])
        if not queue_urls:
            print(f"SQS '{name}' Not found.")
            return
        for url in queue_urls:
            attrs = client.get_queue_attributes(QueueUrl=url, AttributeNames=["All"])
            visible = int(attrs['Attributes']['ApproximateNumberOfMessages'])
            print(f"SQS Queue '{name}' [{url}] messages available: {visible}")
    except Exception as e:
        print(f"SQS '{name}' ERROR: {str(e)}")

def check_kms(name, props):
    client = boto3.client('kms')
    key_alias = props.get('key_alias')
    try:
        resp = client.describe_key(KeyId=f"alias/{key_alias}")
        status = resp['KeyMetadata']['KeyState']
        healthy = status == 'Enabled'
        print(f"KMS key '{name}' [{key_alias}] state: {status} (Healthy: {healthy})")
    except Exception as e:
        print(f"KMS key '{name}' [{key_alias}] ERROR: {str(e)}")

def check_lambda(name, props):
    client = boto3.client('lambda')
    lambda_name = props.get('lambda_name', name)
    try:
        resp = client.get_function(FunctionName=lambda_name)
        conf = resp.get('Configuration', {})
        print(f"Lambda '{name}' [{lambda_name}] runtime: {conf.get('Runtime')}, last modified: {conf.get('LastModified')}")
    except Exception as e:
        print(f"Lambda '{name}' [{lambda_name}] ERROR: {str(e)}")

def check_ecs_cluster(name, props):
    client = boto3.client('ecs')
    try:
        resp = client.describe_clusters(clusters=[name])
        cluster = resp['clusters'][0]
        status = cluster.get('status')
        print(f"ECSCluster '{name}' status: {status}, running tasks: {cluster.get('runningTasksCount')}")
    except Exception as e:
        print(f"ECSCluster '{name}' ERROR: {str(e)}")

def check_load_balancer(type_, name, props):
    client = boto3.client('elbv2')
    try:
        lbs = client.describe_load_balancers(Names=[name])
        lb_arn = lbs['LoadBalancers'][0]['LoadBalancerArn']
        healths = client.describe_target_health(TargetGroupArn=lb_arn)
        states = [t['TargetHealth']['State'] for t in healths['TargetHealthDescriptions']]
        print(f"{type_} '{name}' LB health: {states}")
    except Exception as e:
        print(f"{type_} '{name}' ERROR: {str(e)}")

def skip_health(type_, name, props):
    print(f"{type_} '{name}' -- Health check not implemented, skipping (informational only)")

# Map component types to checkers
COMPONENT_CHECKS = {
    "RDSAuroraPostgres": check_rdsaurora,
    "SQS": check_sqs,
    "KMS": check_kms,
    "Lambda": check_lambda,
    "ECSCluster": check_ecs_cluster,
    "ApplicationLoadBalancer": lambda n,p: check_load_balancer("ApplicationLoadBalancer", n, p),
    "NetworkLoadBalancer": lambda n,p: check_load_balancer("NetworkLoadBalancer", n, p),
    "ManagementHost": skip_health,
    "Route53Record": skip_health,
    "Roles": skip_health,
    "GlobalRoles": skip_health,
    "LightSwitch": skip_health,
}

def main(deployment_yaml_path):
    with open(deployment_yaml_path, "r") as f:
        doc = yaml.safe_load(f)

    components = doc.get("components", [])
    for comp in components:
        ctype = comp.get("type")
        name = comp.get("name")
        props = comp.get("properties", {})
        check_fn = COMPONENT_CHECKS.get(ctype, skip_health)
        print(f"--- Checking {ctype} '{name}' ---")
        check_fn(name, props)
        print("")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python aws_health_check.py <deployment.yaml>")
        sys.exit(1)
    main(sys.argv[1])
