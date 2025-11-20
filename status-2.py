import pywinpty
import os

# Path to eac.exe (update if needed)
EAC_CLI_PATH = r"C:\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"

# Path to your deployment YAML file
DEPLOYMENT_YAML_PATH = r"I:\ds\cam-cardbasicinfo-infra-ode\deployments\ode1\deployment_apply.yaml"

# Build the command line
cmd = f'"{EAC_CLI_PATH}" deployment status -f "{DEPLOYMENT_YAML_PATH}"'

# Make sure the files exist before running
print(f"Checking paths before running command:")
print(f"EAC executable: {EAC_CLI_PATH} Exists? {os.path.isfile(EAC_CLI_PATH)}")
print(f"YAML file: {DEPLOYMENT_YAML_PATH} Exists? {os.path.isfile(DEPLOYMENT_YAML_PATH)}")
print("-" * 60)

if not os.path.isfile(EAC_CLI_PATH):
    print("ERROR: Cannot find eac.exe at the specified path.")
elif not os.path.isfile(DEPLOYMENT_YAML_PATH):
    print("ERROR: Cannot find deployment_apply.yaml at the specified path.")
else:
    # Start a pseudo-terminal to capture interactive output
    with pywinpty.PtyProcess.spawn(cmd) as proc:
        # Read everything printed to the terminal until the process exits
        # This may include all interactive screen content
        result = ""
        while True:
            try:
                chunk = proc.read(1024)  # Read 1KB at a time
                if not chunk:
                    break
                result += chunk
            except EOFError:
                break
        print("----- Captured Output -----")
        print(result)
