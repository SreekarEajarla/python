import subprocess
import sys
import os

# Replace this value with your actual correlation ID
CORRELATION_ID = "REPLACE_ME_CORRELATION_ID"


# On Unix-like systems: Use 'eac' if it's in PATH
EAC_CLI_PATH = r"C:\JPMC\DEV\TMP\ds\tools\eac-cli\latest\eac.exe"

# Check if running on Windows or Unix-like system
if os.name == 'nt':
    # Windows system - use the full path to eac.exe
    eac_command = EAC_CLI_PATH
else:
    # Unix-like system - assume 'eac' is in PATH or use full path if needed
    eac_command = "eac"


def execute_eac_deployment_status(correlation_id):
    """
    Execute the EAC deployment status command with the given correlation ID.
    
    Args:
        correlation_id (str): The correlation ID to use in the command
        
    Returns:
        int: Exit code from the command execution
    """
    # Build the command
    command = [eac_command, "deployment", "status", "-c", correlation_id]
    
    print(f"Executing command: {' '.join(command)}")
    print(f"Correlation ID: {correlation_id}")
    print("-" * 60)
    
    try:
        # Execute the command
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        
        # Print the output
        if result.stdout:
            print("Output:")
            print(result.stdout)
        
        if result.stderr:
            print("Error output:")
            print(result.stderr, file=sys.stderr)
        
        # Return the exit code
        return result.returncode
        
    except FileNotFoundError:
        print(f"Error: EAC CLI not found at '{eac_command}'", file=sys.stderr)
        print("Please verify the EAC_CLI_PATH variable is set correctly.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error executing command: {e}", file=sys.stderr)
        return 1


def main():
    """Main entry point for the script."""
    # Check if correlation ID is still the default placeholder
    if CORRELATION_ID == "REPLACE_ME_CORRELATION_ID":
        print("Warning: CORRELATION_ID is set to the default placeholder value.")
        print("Please update the CORRELATION_ID variable with your actual correlation ID.")
        print("-" * 60)
    
    # Execute the command
    exit_code = execute_eac_deployment_status(CORRELATION_ID)
    
    # Exit with the same code as the command
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
