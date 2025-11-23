import yaml

def get_component_types_and_names(deployment_yaml_path):
    with open(deployment_yaml_path, "r") as f:
        config = yaml.safe_load(f)

    # Correctly handles components being under spec
    components = config.get("spec", {}).get("components", [])
    for comp in components:
        comp_type = comp.get("type")
        comp_name = comp.get("name")
        print(f"Type: {comp_type}, Name: {comp_name}")

if __name__ == "__main__":
    # Update this path to your YAML file location
    deployment_yaml_path = r"C:\Users\SivaReddyKonda\Saved Games\deployment_apply.yaml"
    get_component_types_and_names(deployment_yaml_path)
