import tempfile
import subprocess
import os
from typing import Dict, Any

def execute_tests(refactored_code: str, test_code: str, use_docker: bool = False) -> Dict[str, Any]:
    """
    Writes the refactored code and tests to a temporary isolated directory 
    and executes them using pytest. Can optionally use Docker for enhanced security.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write the LLM's refactored code to a module
        target_file = os.path.join(temp_dir, "target_module.py")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(refactored_code)
            
        # Write the LLM's test code to a pytest file
        test_file = os.path.join(temp_dir, "test_target.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)
            
        if use_docker:
            return _run_docker_sandbox(temp_dir, test_file)

        # Execute pytest in that isolated directory
        try:
            result = subprocess.run(
                ["pytest", test_file, "-v"],
                capture_output=True,
                text=True,
                cwd=temp_dir,
                timeout=15 # Hard timeout to prevent infinite loops from bad code
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout + "\n" + result.stderr
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"Sandbox execution crashed or timed out: {str(e)}"
            }

def _run_docker_sandbox(temp_dir: str, test_file_path: str) -> Dict[str, Any]:
    """Executes the tests securely inside a lightweight Python Docker container."""
    try:
        import docker
        client = docker.from_env()
    except ImportError:
        return {"success": False, "output": "Docker library not installed. Run: pip install docker"}
    except docker.errors.DockerException:
        return {"success": False, "output": "Docker is not running. Please start Docker Engine."}

    try:
        # Bind the temp directory to /app in the container
        # We install pytest on the fly, then run it against the target file
        test_file_name = os.path.basename(test_file_path)
        logs = client.containers.run(
            image="python:3.10-slim",
            command=f'sh -c "pip install pytest > /dev/null 2>&1 && pytest {test_file_name} -v"',
            volumes={os.path.abspath(temp_dir): {'bind': '/app', 'mode': 'rw'}},
            working_dir="/app",
            remove=True,
            mem_limit="256m" # Prevent AI-generated infinite loops from eating RAM
        )
        return {"success": True, "output": logs.decode("utf-8")}
    except docker.errors.ContainerError as e:
        # ContainerError is raised when pytest fails (non-zero exit code)
        output = e.stderr.decode("utf-8") if e.stderr else str(e)
        return {"success": False, "output": output}
    except Exception as e:
        return {"success": False, "output": f"Docker sandbox error: {str(e)}"}