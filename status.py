import subprocess

# Specify the full path to eac.exe
EAC_PATH = r"\\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"
# Build the full command as a list
CMD = [EAC_PATH, "deployment", "status", "-f", "deployment_apply.yaml"]

# Run the command and capture the output
result = subprocess.run(CMD, capture_output=True, text=True)

# Print stdout (command output)
print("STDOUT:\n", result.stdout)
# Print stderr (any errors)
print("STDERR:\n", result.stderr)
