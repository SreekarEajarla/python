import argparse
import os
import boto3
import json
from collections import defaultdict
import sys

try:
    import yaml
except Exception:
    yaml = None
    # YAML functionality requires PyYAML. If it's missing, we'll instruct user.


def _get_region_from_arn(arn):
    """Extract region from an ARN when possible."""
    if not arn or not arn.startswith('arn:'):
        return ''
    parts = arn.split(':')
    # ARN format: arn:partition:service:region:account:resource
    if len(parts) > 4:
        return parts[3]
    return ''


def _get_resource_name(resource):
    """Try multiple strategies to get a human-friendly resource name from the
    Resource Explorer resource item. Falls back to parsing the ARN.
    """
    if not resource:
        return ''

    # Common direct fields
    for key in ('ResourceName', 'Title', 'Name', 'DisplayName'):
        val = resource.get(key)
        if val:
            return val

    # Try properties/attributes which may be a JSON string or dict
    props = resource.get('Properties') or resource.get('Attributes') or resource.get('Resource')
    pdata = None
    if isinstance(props, str):
        try:
            pdata = json.loads(props)
        except Exception:
            pdata = None
    elif isinstance(props, dict):
        pdata = props

    if pdata:
        for k in ('name', 'Name', 'title', 'Title', 'resourceName'):
            if k in pdata and pdata[k]:
                return pdata[k]

    # Fallback: extract last ARN segment
    arn = resource.get('Arn') or resource.get('ARN')
    if arn:
        # Resource identifiers often follow last '/' or ':'
        seg = arn.split('/')[-1]
        if seg and seg != arn:
            return seg
        seg = arn.split(':')[-1]
        return seg

    return ''


def _shorten(text, max_len=100):
    if not text:
        return ''
    s = str(text)
    if len(s) <= max_len:
        return s
    keep = (max_len - 3) // 2
    return s[:keep] + '...' + s[-keep:]


def _print_resources_table(resources, title=None):
    """Print a list of resources (dicts or raw items) in a neat table.

    Expected keys per resource dict: Service, ResourceType, Name, Region, ARN
    """
    if title:
        print(title)

    headers = ['Service', 'ResourceType', 'Name', 'Region', 'ARN']

    rows = []
    for r in resources:
        if isinstance(r, dict):
            service = r.get('Service') or ''
            rtype = r.get('ResourceType') or ''
            name = r.get('Name') or _get_resource_name(r)
            region = r.get('Region') or ''
            arn = r.get('ARN') or r.get('Arn') or ''
        else:
            service = r.get('Service') or ''
            rtype = r.get('ResourceType') or ''
            name = _get_resource_name(r)
            region = r.get('Region') or _get_region_from_arn(r.get('Arn', ''))
            arn = r.get('Arn') or ''

        rows.append([service, rtype, name, region, arn])

    # Determine column widths (cap ARN width)
    col_widths = []
    for i, h in enumerate(headers):
        maxw = len(h)
        for row in rows:
            cell = row[i] or ''
            l = len(str(cell))
            if l > maxw:
                maxw = l
        if headers[i] == 'ARN' and maxw > 120:
            maxw = 120
        col_widths.append(maxw)

    sep = ' | '
    header_line = sep.join(headers[i].ljust(col_widths[i]) for i in range(len(headers)))
    print(header_line)
    print('-' * len(header_line))

    for row in rows:
        out_cells = []
        for i, cell in enumerate(row):
            text = str(cell) if cell is not None else ''
            if headers[i] == 'ARN':
                text = _shorten(text, max_len=col_widths[i])
            out_cells.append(text.ljust(col_widths[i]))
        print(sep.join(out_cells))

    print(f"\nTotal resources: {len(rows)}\n")


def list_resource_explorer_indexes(region=None):
    """List Resource Explorer indexes in a given region.

    If `region` is None, prompt the user interactively. Otherwise validate the
    provided region and return the indexes for it.
    Returns (region, indexes_list) where indexes_list is [] if none found.
    """
    print("Checking for Resource Explorer indexes...\n")

    # Discover valid regions to validate user input
    try:
        ec2 = boto3.client('ec2')
        valid_regions = [r['RegionName'] for r in ec2.describe_regions()['Regions']]
    except Exception:
        print("Unable to retrieve AWS regions. Make sure your AWS credentials are configured.")
        return None, []

    if region:
        if region not in valid_regions:
            print(f"Provided region '{region}' is not valid.")
            return None, []
    else:
        while True:
            region = input("Enter AWS region to check (e.g. us-east-1): ").strip()
            if not region:
                print("Region input cannot be empty. Please enter a valid AWS region.")
                continue
            if region not in valid_regions:
                print(f"'{region}' is not a valid region. Example valid regions: {', '.join(valid_regions[:6])}...")
                retry = input("Try again? (y/n): ").strip().lower()
                if retry != 'y':
                    return None, []
                continue
            break

    indexes = []
    try:
        client = boto3.client('resource-explorer-2', region_name=region)
        response = client.list_indexes()

        if response.get('Indexes'):
            for index in response['Indexes']:
                indexes.append({
                    'Region': index.get('Region', region),
                    'Type': index.get('Type', ''),
                    'ARN': index.get('Arn', '')
                })
                print(f"Found index in {region}: {index.get('Type', '')}")
        else:
            print(f"No Resource Explorer index found in region: {region}")
    except client.exceptions.ResourceNotFoundException:
        print("Resource Explorer not configured in this region.")
    except Exception as e:
        print(f"Error checking indexes in {region}: {e}")

    return region, indexes


def get_all_services_using_resource_explorer(region='us-east-1'):
    client = boto3.client('resource-explorer-2', region_name=region)

    services = defaultdict(int)
    resources = []

    try:
        paginator = client.get_paginator('search')
        page_iterator = paginator.paginate(
            QueryString='*'
        )
        print(f"Searching for resources in region '{region}'...\n")

        for page in page_iterator:
            for resource in page.get('Resources', []):
                resource_region = resource.get('Region') or _get_region_from_arn(resource.get('Arn', ''))

                if resource_region != region:
                    continue

                resource_type = resource.get('ResourceType', 'Unknown')
                service = resource_type.split(':')[0] if ':' in resource_type else resource_type

                services[service] += 1
                resources.append({
                    'ResourceType': resource_type,
                    'ARN': resource.get('Arn', ''),
                    'Region': resource_region,
                    'Service': resource.get('Service', ''),
                    'Name': _get_resource_name(resource)
                })

        print(f"Total unique services found: {len(services)}\n")
        print("Services and resource counts:")
        print("-" * 50)

        for service, count in sorted(services.items()):
            print(f"{service}: {count} resources")

        _print_resources_table(resources, title=f"Resources in region: {region}")

        return {
            'services': dict(services),
            'total_services': len(services),
            'total_resources': len(resources),
            'resources': resources
        }

    except client.exceptions.ResourceNotFoundException:
        print("Error: Resource Explorer is not set up in this region.")
        print("Please create an index using the AWS Console or CLI first.")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None


def _extract_arns_from_yaml_data(data):
    """Recursively find strings that look like ARNs in a parsed YAML structure."""
    arns = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and v.startswith('arn:'):
                arns.append(v)
            else:
                arns.extend(_extract_arns_from_yaml_data(v))
            # keys named arn
            if isinstance(k, str) and k.lower() == 'arn' and isinstance(v, str) and v.startswith('arn:'):
                arns.append(v)
    elif isinstance(data, list):
        for item in data:
            arns.extend(_extract_arns_from_yaml_data(item))
    elif isinstance(data, str):
        if data.startswith('arn:'):
            arns.append(data)

    # dedupe
    return list(dict.fromkeys(arns))


def extract_location_and_services_from_yaml(yaml_path):
    """Extract awsRegion and component list from the deployment YAML.

    Returns a tuple: (region_or_None, components_list)
    Each component in components_list is a dict with at least keys 'type' and 'name'.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse the inventory YAML. Install with 'pip install pyyaml'.")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(yaml_path)

    with open(yaml_path, 'r', encoding='utf-8') as f:
        parsed = yaml.safe_load(f)

    # navigate common structure: spec -> environment -> awsRegion
    region = None
    try:
        region = parsed.get('spec', {}).get('environment', {}).get('awsRegion')
    except Exception:
        region = None

    # components may be under spec.components
    components = []
    try:
        comps = parsed.get('spec', {}).get('components') or parsed.get('components') or []
        for c in comps:
            if not isinstance(c, dict):
                continue
            comp = {
                'type': c.get('type'),
                'name': c.get('name'),
                'properties': c.get('properties', {})
            }
            components.append(comp)
    except Exception:
        components = []

    return region, components


def compare_components_with_inventory(yaml_path, region=None, existing_resources=None):
    """Compare components listed in the YAML to existing resources in `region`.

    Returns list of { component, exists(bool), matches(list) }.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse the inventory YAML. Install with 'pip install pyyaml'.")

    parsed_region, components = extract_location_and_services_from_yaml(yaml_path)
    if region is None:
        region = parsed_region

    if region is None:
        raise ValueError("Region not specified in arguments or YAML; cannot compare components.")

    if existing_resources is None:
        result = get_all_services_using_resource_explorer(region=region)
        existing_resources = result.get('resources', []) if result else []

    matches_report = []
    # prepare searchable fields
    for comp in components:
        cname = (comp.get('name') or '').lower()
        ctype = (comp.get('type') or '').lower()
        matches = []
        for r in existing_resources:
            rname = (r.get('Name') or '').lower()
            rarn = (r.get('ARN') or r.get('Arn') or '')
            rtype = (r.get('ResourceType') or '').lower()

            found = False
            if cname and rname and cname == rname:
                found = True
            elif cname and rarn and cname in rarn.lower():
                found = True
            elif ctype and ctype in rtype:
                found = True

            if found:
                matches.append(r)

        matches_report.append({
            'component': comp,
            'exists': len(matches) > 0,
            'matches': matches
        })

    return region, matches_report


def compare_arns_with_inventory(yaml_path, region, existing_resources=None):
    """Compare ARNs declared in `yaml_path` with existing resources in `region`.

    Returns a list of dicts: { requested_arn, exists(bool), matched_resource or None }
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse the inventory YAML. Install with 'pip install pyyaml'.")

    if not os.path.exists(yaml_path):
        raise FileNotFoundError(yaml_path)

    with open(yaml_path, 'r', encoding='utf-8') as f:
        parsed = yaml.safe_load(f)

    requested_arns = _extract_arns_from_yaml_data(parsed)

    if existing_resources is None:
        result = get_all_services_using_resource_explorer(region=region)
        if not result:
            existing_resources = []
        else:
            existing_resources = result.get('resources', [])

    existing_arn_map = {r.get('ARN') or r.get('Arn'): r for r in existing_resources if (r.get('ARN') or r.get('Arn'))}

    report = []
    for arn in requested_arns:
        matched = existing_arn_map.get(arn)
        exists = matched is not None
        # also attempt suffix match: sometimes inventory contains partial ARNs
        if not exists:
            for e_arn, r in existing_arn_map.items():
                if e_arn and arn.endswith(e_arn):
                    matched = r
                    exists = True
                    break
                if e_arn and e_arn.endswith(arn):
                    matched = r
                    exists = True
                    break

        report.append({
            'requested_arn': arn,
            'exists': exists,
            'matched_resource': matched
        })

    return report


def search_by_service(service_type, region='us-east-1'):
    """
    Search for resources of a specific service type.
    
    Args:
        service_type: AWS service (e.g., 'ec2', 's3', 'lambda')
        region: AWS region where Resource Explorer is set up
    """

    client = boto3.client('resource-explorer-2', region_name=region)

    try:
        paginator = client.get_paginator('search')
        page_iterator = paginator.paginate(
            QueryString=f'service:{service_type}'
        )

        resources = []
        for page in page_iterator:
            for resource in page.get('Resources', []):
                resource_region = resource.get('Region') or _get_region_from_arn(resource.get('Arn', ''))
                if resource_region != region:
                    continue
                resources.append({
                    'ResourceType': resource.get('ResourceType', ''),
                    'ARN': resource.get('Arn', ''),
                    'Region': resource_region,
                    'Service': resource.get('Service', ''),
                    'Name': _get_resource_name(resource)
                })

        print(f"\nFound {len(resources)} resources for service: {service_type} in region {region}")

        # Print results as a table
        _print_resources_table(resources, title=f"Resources for service: {service_type} in {region}")

        return resources

    except Exception as e:
        print(f"Error searching for {service_type}: {str(e)}")
        return []


if __name__ == "__main__":
    # First, check if Resource Explorer is set up
    print("=" * 60)
    print("AWS Resource Explorer - Service Discovery")
    print("=" * 60)
    print()

    parser = argparse.ArgumentParser(description='AWS Resource Explorer inventory and YAML ARN comparison')
    parser.add_argument('-f', '--file', help='Path to inventory YAML file to compare ARNs')
    parser.add_argument('-r', '--region', help='AWS region to query (e.g. us-east-1)')
    parser.add_argument('-o', '--output', help='Optional output JSON file to write the comparison report')
    args = parser.parse_args()

    region, indexes = list_resource_explorer_indexes(region=args.region)

    if not region:
        print("\nNo region selected or unable to determine region.")
        print("To use Resource Explorer, you need to:")
        print("1. Create an aggregator index in the region you want to query")
        print("2. Create local indexes in other regions (optional)")
        print("\nSee: https://docs.aws.amazon.com/resource-explorer/latest/userguide/")
        sys.exit(1)

    if not indexes:
        print(f"\nNo Resource Explorer indexes found in region {region}.")
        print("Create an index in that region using the Console or CLI and try again.")
        sys.exit(1)

    print(f"\nFound {len(indexes)} Resource Explorer index(es) in region {region}")
    print("\nFetching all services...\n")

    # Use the user-selected region
    aggregator_region = region

    print(f"Using index in region: {aggregator_region}\n")

    # Get all services
    result = get_all_services_using_resource_explorer(region=aggregator_region)

    if result:
        print(f"\n{'=' * 60}")
        print(f"Summary: {result['total_resources']} total resources across {result['total_services']} services")
        print(f"{'=' * 60}")

    # If YAML file provided compare ARNs and print JSON report
    if args.file:
        try:
            # First, extract region/components from YAML (region may override)
            yaml_region, components = extract_location_and_services_from_yaml(args.file)
            use_region = aggregator_region or yaml_region

            # ARN-based comparison (if YAML contains ARNs)
            arn_report = []
            try:
                arn_report = compare_arns_with_inventory(args.file, region=use_region)
            except Exception as e:
                # continue, but include error info
                arn_report = {'error': str(e)}

            # Component-based comparison (by name/type)
            comp_report = []
            try:
                comp_region, comp_report = compare_components_with_inventory(args.file, region=use_region)
            except Exception as e:
                comp_report = {'error': str(e)}

            combined = {
                'yaml_region': yaml_region,
                'use_region': use_region,
                'arn_comparison': arn_report,
                'components': comp_report
            }

            out_json = json.dumps(combined, indent=2, default=str)
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as of:
                    of.write(out_json)
                print(f"Comparison written to {args.output}")
            else:
                print(out_json)

        except Exception as e:
            print(f"Error comparing YAML: {e}")
