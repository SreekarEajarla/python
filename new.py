import subprocess
import sys
import os
import re

EAC_CLI_PATH = r"\\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"
DEPLOYMENT_YAML_PATH = r"I:\ds\cam-cardbasicinfo-infra-ode\deployments\ode1\deployment_apply.yaml"

def get_eac_command():
    return EAC_CLI_PATH if os.name == "nt" else "eac"

def parse_eac_text_output(text):
    results = {}
    pattern = re.compile(r"(?P<name>[A-Za-z0-9\-_]+)\s+(?P<status>SUCCESS|FAILED|IN_PROGRESS|PENDING)")

    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            results[match.group("name")] = match.group("status")
    
    return results


def get_deployment_status_text(yaml_file):
    cmd = [
        get_eac_command(),
        "deployment",
        "status",
        "-f", yaml_file
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        print("EAC Error:", result.stderr)
        return None

    return parse_eac_text_output(result.stdout)

if __name__ == "__main__":
    statuses = get_deployment_status_text(DEPLOYMENT_YAML_PATH)

    if statuses:
        print("Parsed Deployment Status:\n")
        for resource, status in statuses.items():
            print(f"{resource}: {status}")
