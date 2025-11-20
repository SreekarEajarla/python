import subprocess

# Specify the full path to eac.exe
EAC_PATH = r"\\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"
# Specify the full path to deployment_apply.yaml
YAML_PATH = r"I:\ds\cam-cardbasicinfo-infra-ode\deployments\ode1\deployment_apply.yaml"
# Build the full command as a list
CMD = [EAC_PATH, "deployment", "status", "-f", YAML_PATH]

# Run the command and capture the output
result = subprocess.run(CMD, capture_output=True, text=True)

# Print stdout (command output)
print("STDOUT:\n", result.stdout)
# Print stderr (any errors)
print("STDERR:\n", result.stderr)
