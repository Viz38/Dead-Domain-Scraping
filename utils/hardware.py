import os
import platform
import psutil
import subprocess
import resource

class HardwareOptimizer:
    @staticmethod
    def optimize_system_limits():
        """Increases the file descriptor limit to prevent EPIPE in high-concurrency Playwright sessions."""
        if platform.system() != "Windows":
            try:
                # Get current limits
                soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                # Aim for 8192 or the hard limit
                target = min(8192, hard)
                if soft < target:
                    resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
                    return True, target
            except Exception:
                pass
        return False, 0

    @staticmethod
    def get_specs():
        """Detect OS, CPU, RAM, and GPU presence."""
        specs = {
            "os": platform.system(),
            "cpu_cores": os.cpu_count() or 4,
            "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_ram_gb": round(psutil.virtual_memory().available / (1024**3), 2),
            "gpu_available": False,
            "gpu_details": "None"
        }

        # GPU Detection
        try:
            if specs["os"] == "Darwin":
                cmd = ["system_profiler", "SPDisplaysDataType"]
                output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
                if "Apple M" in output or "Radeon" in output:
                    specs["gpu_available"] = True
                    specs["gpu_details"] = "Apple Silicon / Discrete Mac GPU"
            elif specs["os"] == "Windows":
                cmd = ["wmic", "path", "win32_VideoController", "get", "name"]
                output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
                clean_output = [line.strip() for line in output.split("\n") if line.strip() and "Name" not in line]
                if clean_output:
                    specs["gpu_available"] = True
                    specs["gpu_details"] = ", ".join(clean_output)
            else: # Linux
                try:
                    nv_output = subprocess.check_output(["nvidia-smi", "-L"], stderr=subprocess.DEVNULL).decode()
                    if "GPU" in nv_output:
                        specs["gpu_available"] = True
                        specs["gpu_details"] = nv_output.strip().split("\n")[0]
                except Exception:
                    try:
                        lspci_output = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL).decode()
                        if "VGA" in lspci_output or "3D" in lspci_output:
                            specs["gpu_available"] = True
                            specs["gpu_details"] = "Linux Integrated/Discrete GPU Detected"
                    except Exception:
                        pass
        except Exception:
            pass

        return specs

    @staticmethod
    def calculate_concurrency():
        """
        Calculates optimal concurrency leaving 35% resources free.
        CPU: Utilizes 50% of cores at 10x density (IO heavy).
        RAM: Utilizes 50% of RAM at 300MB per worker.
        """
        specs = HardwareOptimizer.get_specs()
        
        total_cores = int(specs["cpu_cores"])
        total_ram_mb = float(specs["total_ram_gb"] * 1024.0)
        
        # 35% Headroom Rule
        utilizable_cores = total_cores * 0.50
        utilizable_ram_mb = total_ram_mb * 0.50
        
        # Browser tasks are IO-bound, 10 workers per core is a safe multiplier for 50% Load
        cpu_concurrency = int(utilizable_cores * 10)
        
        # 300MB is a safe per-context margin for blocked resources
        ram_concurrency = int(utilizable_ram_mb / 300)
        
        # Take the most constrained resource, floor at 10
        concurrency = max(10, min(cpu_concurrency, ram_concurrency))
        
        # Safety Cap: 15 workers. 
        # Note: Even if hardware (RAM/CPU) supports more, archival APIs (Wayback/IA) 
        # will throttle/block if we exceed 15-20 concurrent CDX requests.
        concurrency = min(concurrency, 15)

        # 20% Boost for GPU systems (offloads some rendering)
        if specs["gpu_available"]:
            concurrency = int(concurrency * 1.2)
            
        return int(concurrency), specs

if __name__ == "__main__":
    opt = HardwareOptimizer()
    conc, details = opt.calculate_concurrency()
    print(f"Dynamic Concurrency (50% Load): {conc}")
    print(f"Details: {details}")
