import subprocess
import os

# Complete paths for executable and YAML file
EAC_PATH = r"\\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"  # or use the mapped drive, e.g., r"Z:\ds\tools\eac-cli\latest\eac.exe"
YAML_PATH = r"I:\ds\cam-cardbasicinfo-infra-ode\deployments\ode1\deployment_apply.yaml"

# Check that executable and YAML file exist before running
print("Checking paths before running command:")
print(f"EAC executable: {EAC_PATH} Exists? {os.path.isfile(EAC_PATH)}")
print(f"YAML file: {YAML_PATH} Exists? {os.path.isfile(YAML_PATH)}")

if not os.path.isfile(EAC_PATH):
    print("ERROR: Cannot find eac.exe at the specified path.")
elif not os.path.isfile(YAML_PATH):
    print("ERROR: Cannot find deployment_apply.yaml at the specified path.")
else:
    CMD = [EAC_PATH, "deployment", "status", "-f", YAML_PATH]
    try:
        result = subprocess.run(CMD, capture_output=True, text=True)
        print("STDOUT:\n", result.stdout)
        print("STDERR:\n", result.stderr)
    except Exception as e:
        print("ERROR running subprocess:", e)
