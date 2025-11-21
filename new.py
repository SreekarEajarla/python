import yaml
import boto3
import json
from typing import Dict, List, Tuple

class AWSServiceVerifier:
    """Verify if services from deployment YAML exist in AWS"""
    
    def __init__(self, region: str = 'us-east-1'):
        """Initialize AWS clients"""
        self.region = region
        self.elbv2_client = boto3.client('elbv2', region_name=region)
        self.eks_client = boto3.client('eks', region_name=region)
        self.ec2_client = boto3.client('ec2', region_name=region)
        
    def load_deployment_yaml(self, yaml_file: str) -> Dict:
        """Load and parse the deployment YAML file"""
        try:
            with open(yaml_file, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading YAML file: {e}")
            return None
    
    def verify_alb(self, alb_name: str) -> Tuple[bool, str]:
        """Verify if Application Load Balancer exists"""
        try:
            response = self.elbv2_client.describe_load_balancers()
            for lb in response['LoadBalancers']:
                if lb['LoadBalancerName'] == alb_name:
                    return True, lb['LoadBalancerArn']
            return False, None
        except Exception as e:
            print(f"Error checking ALB: {e}")
            return False, None
    
    def verify_eks_cluster(self, cluster_name: str) -> Tuple[bool, str]:
        """Verify if EKS cluster exists"""
        try:
            response = self.eks_client.describe_cluster(name=cluster_name)
            return True, response['cluster']['arn']
        except self.eks_client.exceptions.ResourceNotFoundException:
            return False, None
        except Exception as e:
            print(f"Error checking EKS cluster: {e}")
            return False, None
    
    def verify_services(self, yaml_file: str) -> Dict:
        """Main function to verify all services from deployment YAML"""
        deployment = self.load_deployment_yaml(yaml_file)
        if not deployment:
            return {}
        
        results = {
            'model_name': deployment.get('metadata', {}).get('name', 'unknown'),
            'model_version': deployment.get('metadata', {}).get('version', 'unknown'),
            'services': []
        }
        
        # Parse components from YAML
        components = deployment.get('spec', {}).get('components', [])
        
        for component in components:
            comp_type = component.get('type')
            comp_name = component.get('name')
            
            if comp_type == 'ApplicationLoadBalancer':
                exists, arn = self.verify_alb(comp_name)
                results['services'].append({
                    'type': 'ALB',
                    'name': comp_name,
                    'exists': exists,
                    'arn': arn,
                    'status': '✓ Found' if exists else '✗ Not Found'
                })
                
                # Check connected EKS clusters
                connects_to = component.get('connectsTo', [])
                for connection in connects_to:
                    if connection.get('type') == 'EKSCluster':
                        cluster_name = connection.get('name')
                        exists, arn = self.verify_eks_cluster(cluster_name)
                        results['services'].append({
                            'type': 'EKS Cluster',
                            'name': cluster_name,
                            'exists': exists,
                            'arn': arn,
                            'status': '✓ Found' if exists else '✗ Not Found',
                            'connected_to': comp_name
                        })
            
            elif comp_type == 'EKSCluster':
                exists, arn = self.verify_eks_cluster(comp_name)
                results['services'].append({
                    'type': 'EKS Cluster',
                    'name': comp_name,
                    'exists': exists,
                    'arn': arn,
                    'status': '✓ Found' if exists else '✗ Not Found'
                })
        
        return results
    
    def print_results(self, results: Dict):
        """Print verification results in a readable format"""
        print("\n" + "="*70)
        print(f"Service Verification Report")
        print("="*70)
        print(f"Model: {results['model_name']} (v{results['model_version']})")
        print("-"*70)
        
        for service in results['services']:
            print(f"\n{service['status']} {service['type']}: {service['name']}")
            if service['exists']:
                print(f"   ARN: {service['arn']}")
            if 'connected_to' in service:
                print(f"   Connected to: {service['connected_to']}")
        
        print("\n" + "="*70)
        
        # Summary
        total = len(results['services'])
        found = sum(1 for s in results['services'] if s['exists'])
        print(f"Summary: {found}/{total} services found in AWS")
        print("="*70 + "\n")
        
        return found == total


def main():
    """Main execution function"""
    # Configuration
    DEPLOYMENT_FILE = 'deployment_apply.yaml'
    AWS_REGION = 'us-east-1'  # Change to your region
    
    print("Starting AWS Service Verification...")
    print(f"Region: {AWS_REGION}")
    print(f"Deployment file: {DEPLOYMENT_FILE}\n")
    
    # Initialize verifier
    verifier = AWSServiceVerifier(region=AWS_REGION)
    
    # Verify services
    results = verifier.verify_services(DEPLOYMENT_FILE)
    
    # Print results
    if results:
        all_exist = verifier.print_results(results)
        
        # Exit code based on results
        if all_exist:
            print("✓ All services verified successfully!")
            return 0
        else:
            print("✗ Some services are missing!")
            return 1
    else:
        print("Failed to verify services")
        return 1


if __name__ == "__main__":
    exit(main())
