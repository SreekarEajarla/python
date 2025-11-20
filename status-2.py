import subprocess
import sys
import os

# Path to eac.exe (update if needed!)
EAC_CLI_PATH = r"\\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"

# Path to your deployment YAML file (update if needed!)
DEPLOYMENT_YAML_PATH = r"I:\ds\cam-cardbasicinfo-infra-ode\deployments\ode1\deployment_apply.yaml"

# Detect platform and set eac_command
if os.name == 'nt':
    eac_command = EAC_CLI_PATH
else:
    eac_command = "eac"  # Assume eac is in PATH on Unix-like

def execute_eac_deployment_status_with_yaml(yaml_path):
    """
    Execute the EAC deployment status command with the deployment YAML file.
    Returns exit code.
    """
    # Build the command
    command = [eac_command, "deployment", "status", "-f", yaml_path]

    print(f"Executing command: {' '.join(command)}")
    print(f"YAML file: {yaml_path}")
    print("-" * 60)

    # Check if files exist
    if not os.path.isfile(eac_command):
        print(f"Error: EAC CLI not found at '{eac_command}'", file=sys.stderr)
        print("Please verify the EAC_CLI_PATH variable is set correctly.", file=sys.stderr)
        return 1
    if not os.path.isfile(yaml_path):
        print(f"Error: deployment YAML not found at '{yaml_path}'", file=sys.stderr)
        return 1

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        if result.stdout:
            print("Output:")
            print(result.stdout)
        if result.stderr:
            print("Error output:")
            print(result.stderr, file=sys.stderr)
        return result.returncode
    except Exception as e:
        print(f"Error executing command: {e}", file=sys.stderr)
        return 1

def main():
    """Main entry point for the script."""
    exit_code = execute_eac_deployment_status_with_yaml(DEPLOYMENT_YAML_PATH)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
