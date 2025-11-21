import yaml
import boto3
import json
from typing import Dict, List, Tuple, Optional
from botocore.exceptions import ClientError

class AWSServiceVerifier:
    """Verify if services from deployment YAML exist in AWS"""
    
    def __init__(self, region: Optional[str] = None):
        """Initialize AWS clients"""
        self.region = region
        self.clients = {}
        
    def _get_client(self, service_name: str):
        """Lazy initialization of AWS clients"""
        if service_name not in self.clients:
            self.clients[service_name] = boto3.client(service_name, region_name=self.region)
        return self.clients[service_name]
    
    def load_deployment_yaml(self, yaml_file: str) -> Dict:
        """Load and parse the deployment YAML file"""
        try:
            with open(yaml_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading YAML file: {e}")
            return None
    
    def extract_region_from_yaml(self, deployment: Dict) -> str:
        """Extract AWS region from deployment YAML"""
        try:
            env = deployment.get('spec', {}).get('environment', {})
            region = env.get('awsRegion', 'us-east-1')
            return region
        except Exception as e:
            print(f"Warning: Could not extract region from YAML, using default: {e}")
            return 'us-east-1'
    
    def verify_rds_aurora_postgres(self, name: str, properties: Dict) -> Tuple[bool, Optional[str]]:
        """Verify if RDS Aurora PostgreSQL cluster exists"""
        try:
            rds_client = self._get_client('rds')
            response = rds_client.describe_db_clusters(
                DBClusterIdentifier=properties.get('custom_cluster_name', name)
            )
            if response['DBClusters']:
                cluster = response['DBClusters'][0]
                return True, cluster['DBClusterArn']
            return False, None
        except ClientError as e:
            if e.response['Error']['Code'] == 'DBClusterNotFoundFault':
                return False, None
            print(f"Error checking RDS Aurora cluster '{name}': {e}")
            return False, None
    
    def verify_kms_key(self, name: str) -> Tuple[bool, Optional[str]]:
        """Verify if KMS key exists"""
        try:
            kms_client = self._get_client('kms')
            # List all keys and check aliases
            aliases_response = kms_client.list_aliases()
            for alias in aliases_response['Aliases']:
                if alias.get('AliasName') == f"alias/{name}":
                    key_id = alias.get('TargetKeyId')
                    key_response = kms_client.describe_key(KeyId=key_id)
                    return True, key_response['KeyMetadata']['Arn']
            return False, None
        except Exception as e:
            print(f"Error checking KMS key '{name}': {e}")
            return False, None
    
    def verify_lightsail_instance(self, name: str, model: str) -> Tuple[bool, Optional[str]]:
        """Verify if Lightsail instance exists"""
        try:
            lightsail_client = self._get_client('lightsail')
            response = lightsail_client.get_instance(instanceName=name)
            if response['instance']:
                instance = response['instance']
                arn = instance.get('arn')
                return True, arn
            return False, None
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                return False, None
            print(f"Error checking Lightsail instance '{name}': {e}")
            return False, None
    
    def verify_service_by_type(self, component: Dict) -> Dict:
        """Verify service existence based on component type"""
        comp_type = component.get('type', '')
        comp_name = component.get('name', 'unknown')
        
        result = {
            'type': comp_type,
            'name': comp_name,
            'exists': False,
            'arn': None,
            'status': '✗ Not Found',
            'details': {}
        }
        
        try:
            if comp_type == 'RDSAuroraPostgres':
                properties = component.get('properties', {})
                result['details'] = {
                    'instance_version': component.get('instanceVersion', 'N/A'),
                    'action': component.get('action', 'N/A'),
                    'deployment': component.get('deployment', 'N/A')
                }
                exists, arn = self.verify_rds_aurora_postgres(comp_name, properties)
                result['exists'] = exists
                result['arn'] = arn
                result['status'] = '✓ Found' if exists else '✗ Not Found'
                
            elif comp_type == 'KMS':
                exists, arn = self.verify_kms_key(comp_name)
                result['exists'] = exists
                result['arn'] = arn
                result['status'] = '✓ Found' if exists else '✗ Not Found'
                
            elif comp_type == 'Lightsail':
                model = component.get('model', '')
                model_version = component.get('modelVersion', '')
                result['details'] = {
                    'model': model,
                    'model_version': model_version,
                    'deployment': component.get('deployment', 'N/A')
                }
                exists, arn = self.verify_lightsail_instance(comp_name, model)
                result['exists'] = exists
                result['arn'] = arn
                result['status'] = '✓ Found' if exists else '✗ Not Found'
                
            else:
                result['status'] = '⚠ Unknown Type'
                
        except Exception as e:
            result['status'] = f'✗ Error: {str(e)}'
            print(f"Error verifying {comp_type} '{comp_name}': {e}")
        
        return result
    
    def verify_connections(self, component: Dict, all_services: List[Dict]) -> List[Dict]:
        """Verify connected services for a component"""
        connects_to = component.get('connectsTo', [])
        connected_services = []
        
        for connection in connects_to:
            conn_type = connection.get('type', '')
            conn_name = connection.get('name', '')
            
            conn_result = {
                'type': conn_type,
                'name': conn_name,
                'parent': component.get('name'),
                'exists': False,
                'arn': None,
                'status': '✗ Not Found'
            }
            
            # Verify connected service
            if conn_type == 'KMS':
                exists, arn = self.verify_kms_key(conn_name)
                conn_result['exists'] = exists
                conn_result['arn'] = arn
                conn_result['status'] = '✓ Found' if exists else '✗ Not Found'
                
            elif conn_type == 'Lightsail':
                model = connection.get('model', '')
                exists, arn = self.verify_lightsail_instance(conn_name, model)
                conn_result['exists'] = exists
                conn_result['arn'] = arn
                conn_result['status'] = '✓ Found' if exists else '✗ Not Found'
            
            connected_services.append(conn_result)
        
        return connected_services
    
    def verify_services(self, yaml_file: str) -> Dict:
        """Main function to verify all services from deployment YAML"""
        deployment = self.load_deployment_yaml(yaml_file)
        if not deployment:
            return {}
        
        # Extract region from YAML
        if not self.region:
            self.region = self.extract_region_from_yaml(deployment)
        
        # Extract metadata
        metadata = deployment.get('metadata', {})
        spec = deployment.get('spec', {})
        environment = spec.get('environment', {})
        
        results = {
            'deployment_name': metadata.get('name', 'unknown'),
            'seal_id': metadata.get('sealID', 'unknown'),
            'model': {
                'name': deployment.get('model', {}).get('name', 'unknown'),
                'version': deployment.get('model', {}).get('version', 'unknown')
            },
            'environment': {
                'aws_account_id': environment.get('awsAccountID', 'unknown'),
                'aws_region': environment.get('awsRegion', 'unknown'),
                'organization': environment.get('organization', 'unknown')
            },
            'module_pack': {
                'name': spec.get('modulePack', {}).get('name', 'unknown'),
                'version': spec.get('modulePack', {}).get('version', 'unknown')
            },
            'services': [],
            'connections': []
        }
        
        print(f"Using AWS Region: {self.region}")
        print(f"AWS Account ID: {results['environment']['aws_account_id']}")
        
        # Parse components from YAML
        components = spec.get('components', [])
        
        for component in components:
            # Verify main service
            service_result = self.verify_service_by_type(component)
            results['services'].append(service_result)
            
            # Verify connected services
            connected = self.verify_connections(component, results['services'])
            results['connections'].extend(connected)
        
        return results
    
    def print_results(self, results: Dict):
        """Print verification results in a readable format"""
        print("\n" + "="*80)
        print(f"AWS Service Verification Report")
        print("="*80)
        print(f"Deployment: {results['deployment_name']}")
        print(f"Seal ID: {results['seal_id']}")
        print(f"Model: {results['model']['name']} (v{results['model']['version']})")
        print(f"Module Pack: {results['module_pack']['name']} (v{results['module_pack']['version']})")
        print(f"AWS Account: {results['environment']['aws_account_id']}")
        print(f"AWS Region: {results['environment']['aws_region']}")
        print(f"Organization: {results['environment']['organization']}")
        print("-"*80)
        
        # Main services
        print("\n📦 Main Services:")
        print("-"*80)
        for service in results['services']:
            print(f"\n{service['status']} [{service['type']}] {service['name']}")
            if service['exists'] and service['arn']:
                print(f"   ARN: {service['arn']}")
            if service.get('details'):
                for key, value in service['details'].items():
                    print(f"   {key}: {value}")
        
        # Connected services
        if results['connections']:
            print("\n\n🔗 Connected Services:")
            print("-"*80)
            for conn in results['connections']:
                print(f"\n{conn['status']} [{conn['type']}] {conn['name']}")
                print(f"   Connected to: {conn['parent']}")
                if conn['exists'] and conn['arn']:
                    print(f"   ARN: {conn['arn']}")
        
        print("\n" + "="*80)
        
        # Summary
        total_services = len(results['services'])
        found_services = sum(1 for s in results['services'] if s['exists'])
        total_connections = len(results['connections'])
        found_connections = sum(1 for c in results['connections'] if c['exists'])
        
        print(f"📊 Summary:")
        print(f"   Main Services: {found_services}/{total_services} found")
        print(f"   Connected Services: {found_connections}/{total_connections} found")
        print(f"   Total: {found_services + found_connections}/{total_services + total_connections} found")
        print("="*80 + "\n")
        
        return (found_services + found_connections) == (total_services + total_connections)


def main():
    """Main execution function"""
    # Configuration
    DEPLOYMENT_FILE = 'deployment_apply.yaml'
    
    print("🚀 Starting AWS Service Verification...")
    print(f"📄 Deployment file: {DEPLOYMENT_FILE}\n")
    
    # Initialize verifier (region will be extracted from YAML)
    verifier = AWSServiceVerifier()
    
    # Verify services
    results = verifier.verify_services(DEPLOYMENT_FILE)
    
    # Print results
    if results:
        all_exist = verifier.print_results(results)
        
        # Exit code based on results
        if all_exist:
            print("✅ All services verified successfully!")
            return 0
        else:
            print("⚠️  Some services are missing or could not be verified!")
            return 1
    else:
        print("❌ Failed to load or verify services")
        return 1

if __name__ == "__main__":
    exit(main())
