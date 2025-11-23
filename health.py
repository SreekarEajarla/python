# File: check_health_robust.py

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
# Create a single instance of the manager to be used by all check functions.
client_manager = ClientManager()


# --- Health Check Functions for Each Component Type ---

def _check_rds_aurora(name, properties):
    """Health check for RDSAuroraPostgres."""
    # In your YAML, `custom_cluster_name` is set. This is a likely identifier.
    # We'll assume the variable part is not known, so we search for a cluster
    # whose name *contains* the component name as a fallback.
    try:
        rds_client = client_manager.get('rds')
        clusters = rds_client.describe_db_clusters()['DBClusters']
        # A more robust method would be to filter by tags if they are consistent.
        cluster = next((c for c in clusters if name in c['DBClusterIdentifier']), None)
        if cluster:
            return f"Found Cluster: {cluster['DBClusterIdentifier']}, Status: {cluster['Status']}"
        return f"Cluster containing name '{name}' not found."
    except ClientError as e:
        return f"AWS API Error: {e.response['Error']['Message']}"

def _check_management_host(name, properties):
    """Health check for ManagementHost (EC2 Instance)."""
    # EC2 instances are best found via tags. Your YAML specifies tags.
    # We will assume a 'Name' tag is created based on the component name.
    try:
        # A common convention is to have a 'Name' tag.
        ec2_client = client_manager.get('ec2')
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
    # The actual role name might be complex. We check for existence.
    # The YAML has `byo: ${ecs_role_name}` or `name: ${lambda_role_name}`.
    # This is hard to resolve here, so we'll check for the component name as a substring.
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
    # The alias is defined in the properties.
    alias_name = properties.get('key_alias')
    if not alias_name:
        return "Skipped: 'key_alias' not defined in properties."
    try:
        # KMS aliases are prefixed with 'alias/'
        kms_client = client_manager.get('kms')
        response = kms_client.describe_key(KeyId=f'alias/{alias_name}')
        key_id = response['KeyMetadata']['KeyId']
        state = response['KeyMetadata']['KeyState']
        return f"Found Key: {key_id} via alias '{alias_name}', State: {state}"
    except ClientError as e:
        if e.response['Error']['Code'] == 'NotFoundException':
            return f"KMS Key with alias '{alias_name}' not found."
        return f"AWS API Error: {e.response['Error']['Message']}"


# --- Health Check Registry ---
# This dictionary maps a component type from YAML to a health check function.
HEALTH_CHECK_REGISTRY = {
    "RDSAuroraPostgres": _check_rds_aurora,
    "ManagementHost": _check_management_host,
    "ApplicationLoadBalancer": _check_load_balancer,
    "NetworkLoadBalancer": _check_load_balancer, # Reuses the same function
    "Roles": _check_iam_role,
    "GlobalRoles": _check_iam_role, # Reuses the same function
    "ECSCluster": _check_ecs_cluster,
    "KMS": _check_kms_key,
    # To add a check for SQS:
    # "SQS": _check_sqs_queue,
    # "Lambda": _check_lambda_function,
}

def get_deployment_config(file_path):
    """Parses the entire deployment file."""
    print(f"Reading configuration from: {file_path}\n")
    try:
        with open(file_path, 'r') as f:
            deployment_data = yaml.safe_load(f)
            return deployment_data
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return None




def get_components_from_deployment(file_path):
    """Parses a deployment.yaml file and extracts component info."""
    print(f"Reading components from: {file_path}\n")
    try:
        with open(file_path, 'r') as f:
            deployment_data = yaml.safe_load(f)
            components = deployment_data.get('components', [])
            if not components:
                print("No components found in the deployment file.")
                return []
            return components
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return []
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        return []

# --- Main Execution Logic ---
if __name__ == "__main__":
    deployment_file = '/home/siva_konda/EAC-python-code/deployment.yaml'
    
    # Load the entire deployment configuration
    config = get_deployment_config(deployment_file)
    
    if not config:
        exit(1)

    # Extract region and components
    region = config.get('spec', {}).get('modulepak', [{}])[0].get('environment', {}).get('awsRegion')
    components_to_check = config.get('components', [])

    # Initialize the client manager with the extracted region
    client_manager = ClientManager(region=region)
    
    if components_to_check:
        print("--- Running Health Checks ---\n")
        for comp in components_to_check:
            comp_type = comp.get('type')
            comp_name = comp.get('name')
            comp_props = comp.get('properties', {})

            if not (comp_type and comp_name):
                print("Skipping component with missing type or name.\n" + "-"*30)
                continue

            print(f"Checking {comp_type}: {comp_name}")
            
            # Dynamic dispatch to the correct health check function
            # IAM is global, so it doesn't need a region.
            is_global_service = comp_type in ["Roles", "GlobalRoles"]
            
            # Pass the region to the client manager
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
