import os
import subprocess
import sys

def run_cmd(args):
    result = subprocess.run(args, check=True)
    return result.returncode

def main():
    # 1) Run migrations
    run_cmd([sys.executable, "manage.py", "migrate"])

    # 2) Generate connector token and optionally write to file
    connector_token_file = os.getenv("CONNECTOR_TOKEN_FILE")
    if connector_token_file:
        # Run the management command and capture output
        proc = subprocess.run(
            [sys.executable, "manage.py", "generate_connector_token", "--no-color"],
            check=False,
            capture_output=True,
            text=True,
        )
        output = proc.stdout.splitlines()
        # Grab last line that looks like a JWT
        for line in reversed(output):
            line = line.strip()
            if line.count(".") == 2 and all(part for part in line.split(".")):
                os.makedirs(os.path.dirname(connector_token_file), exist_ok=True)
                with open(connector_token_file, "w", encoding="utf-8") as f:
                    f.write(line)
                break

    # 3) Start dev server
    os.execvp(sys.executable, [sys.executable, "manage.py", "runserver", "0.0.0.0:8000"])

if __name__ == "__main__":
    main()