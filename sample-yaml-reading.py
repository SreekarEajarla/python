import yaml
import boto3
from botocore.exceptions import ClientError

class ClientManager:
    """
    Manages and caches Boto3 clients.
    Clients are created on-demand the first time they are requested.
    """
    def __init__(self, region=None):
        self._clients = {}
        self.region = region

    def get(self, service_name, region_override=None):
        if service_name not in self._clients:
            # Create the client if it doesn't exist in our cache
            print(f"    (Initializing Boto3 client for '{service_name}'...)")
            self._clients[service_name] = boto3.client(service_name, region_name=region_override or self.region)
        return self._clients[service_name]

# --- Central Client Manager ---
# This will be initialized later with the region from the deployment file.
client_manager = None


# --- Health Check Functions for Each Component Type ---

def _check_rds_aurora(name, properties):
    """Health check for RDSAuroraPostgres."""
    try:
        rds_client = client_manager.get('rds')
        clusters = rds_client.describe_db_clusters()['DBClusters']
        # Search for a cluster where the name from YAML is part of the real name
        cluster = next((c for c in clusters if name in c['DBClusterIdentifier']), None)
        if cluster:
            return f"Found Cluster: {cluster['DBClusterIdentifier']}, Status: {cluster['Status']}"
        return f"Cluster containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_management_host(name, properties):
    """Health check for ManagementHost (EC2 Instance)."""
    try:
        ec2_client = client_manager.get('ec2')
        # A common convention is to have a 'Name' tag. We search for a tag containing the name.
        filters = [{'Name': 'tag:Name', 'Values': [f'*{name}*']}]
        reservations = ec2_client.describe_instances(Filters=filters)['Reservations']
        
        if not reservations or not reservations[0]['Instances']:
            return f"Instance with name tag like '*{name}*' not found."

        instance = reservations[0]['Instances'][0]
        instance_id = instance['InstanceId']
        state = instance['State']['Name']
        
        # For a deeper health check, look at instance status checks
        status_res = ec2_client.describe_instance_status(InstanceIds=[instance_id], IncludeAllInstances=True)
        if status_res['InstanceStatuses']:
            i_status = status_res['InstanceStatuses'][0]['InstanceStatus']['Status']
            s_status = status_res['InstanceStatuses'][0]['SystemStatus']['Status']
            return f"Found Instance: {instance_id}, State: {state}, InstanceStatus: {i_status}, SystemStatus: {s_status}"
        
        return f"Found Instance: {instance_id}, State: {state}. Status checks not available (may be stopped)."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_load_balancer(name, properties):
    """Health check for ApplicationLoadBalancer and NetworkLoadBalancer."""
    try:
        elbv2_client = client_manager.get('elbv2')
        lbs = elbv2_client.describe_load_balancers()['LoadBalancers']
        # Search for a load balancer where the name from YAML is part of the real name
        lb = next((l for l in lbs if name in l['LoadBalancerName']), None)
        if lb:
            return f"Found LB: {lb['LoadBalancerName']}, State: {lb['State']['Code']}"
        return f"Load Balancer containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_iam_role(name, properties):
    """Health check for Roles and GlobalRoles."""
    try:
        iam_client = client_manager.get('iam')
        roles = iam_client.list_roles()['Roles']
        role = next((r for r in roles if name in r['RoleName']), None)
        if role:
             return f"Found Role containing name: {role['RoleName']}"
        return f"Role containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_ecs_cluster(name, properties):
    """Health check for ECSCluster."""
    try:
        ecs_client = client_manager.get('ecs')
        response = ecs_client.describe_clusters(clusters=[name])
        if response.get('failures'):
            return f"ECS Cluster '{name}' not found or error: {response['failures'][0]['reason']}"
        if response.get('clusters'):
            cluster = response['clusters'][0]
            return f"Found Cluster: {cluster['clusterName']}, Status: {cluster['status']}, ActiveServices: {cluster['activeServicesCount']}"
        return f"ECS Cluster '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_kms_key(name, properties):
    """Health check for KMS Key."""
    alias_name = properties.get('key_alias')
    if not alias_name:
        return "Skipped: 'key_alias' not defined in properties."
    try:
        kms_client = client_manager.get('kms')
        response = kms_client.describe_key(KeyId=f'alias/{alias_name}')
        key_id = response['KeyMetadata']['KeyId']
        state = response['KeyMetadata']['KeyState']
        return f"Found Key: {key_id} via alias '{alias_name}', State: {state}"
    except ClientError as e:
        if e.response['Error']['Code'] == 'NotFoundException':
            return f"KMS Key with alias '{alias_name}' not found."
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_sqs_queue(name, properties):
    """Health check for SQS queues."""
    try:
        sqs_client = client_manager.get('sqs')
        response = sqs_client.list_queues()
        queue_urls = response.get('QueueUrls', [])
        queue_url = next((url for url in queue_urls if name in url), None)
        if queue_url:
            return f"Found SQS Queue: {queue_url}"
        return f"SQS Queue containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_lambda_function(name, properties):
    """Health check for Lambda functions."""
    try:
        lambda_client = client_manager.get('lambda')
        functions = lambda_client.list_functions()['Functions']
        func = next((f for f in functions if name in f['FunctionName']), None)
        if func:
            return f"Found Lambda: {func['FunctionName']}, Runtime: {func['Runtime']}, State: {func.get('State', 'N/A')}"
        return f"Lambda function containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_route53_record(name, properties):
    """Health check for Route53Record."""
    return "Skipped: Route53 check is complex and not fully implemented. It requires Hosted Zone ID and record details."


# --- Health Check Registry ---
HEALTH_CHECK_REGISTRY = {
    "RDSAuroraPostgres": _check_rds_aurora,
    "ManagementHost": _check_management_host,
    "SQS": _check_sqs_queue,
    "Lambda": _check_lambda_function,
    "Route53Record": _check_route53_record,
    "ApplicationLoadBalancer": _check_load_balancer,
    "NetworkLoadBalancer": _check_load_balancer,
    "Roles": _check_iam_role,
    "GlobalRoles": _check_iam_role,
    "ECSCluster": _check_ecs_cluster,
    "KMS": _check_kms_key,
}

def run_health_checks(deployment_yaml_path):
    global client_manager
    try:
        with open(deployment_yaml_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: The file {deployment_yaml_path} was not found.")
        return
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return

    # Extract region and components
    region = config.get('spec', {}).get('modulepak', [{}])[0].get('environment', {}).get('awsRegion')
    components_to_check = config.get('components', [])

    if not region:
        print("Error: Could not determine AWS region from deployment file.")
        return

    # Initialize the client manager with the extracted region
    client_manager = ClientManager(region=region)
    print(f"Running checks in AWS Region: {region}\n")

    if not components_to_check:
        print("No components found in the deployment file.")
        return

    print("--- Components Found in deployment.yaml ---")
    for comp in components_to_check:
        comp_type = comp.get('type')
        comp_name = comp.get('name')
        if comp_type and comp_name:
            print(f"Type: {comp_type}, Name: {comp_name}")
    print("-" * 43 + "\n")

    print("--- Running Health Checks ---\n")
    for comp in components_to_check:
        comp_type = comp.get('type')
        comp_name = comp.get('name')
        comp_props = comp.get('properties', {})

        if not (comp_type and comp_name):
            print("Skipping component with missing type or name.\n" + "-"*30)
            continue

        print(f"Checking {comp_type}: {comp_name}")
        
        check_function = HEALTH_CHECK_REGISTRY.get(comp_type)
        
        if check_function:
            try:
                status = check_function(comp_name, comp_props)
                print(f"  -> Status: {status}")
            except Exception as e:
                print(f"  -> An unexpected error occurred during check: {e}")
        else:
            print(f"  -> Status: Health check not implemented for type '{comp_type}'.")
        
        print("-" * 30)

if __name__ == "__main__":
    # Update this path to your YAML file location
    deployment_yaml_path = "/home/siva_konda/EAC-python-code/deployment.yaml"
    run_health_checks(deployment_yaml_path)
