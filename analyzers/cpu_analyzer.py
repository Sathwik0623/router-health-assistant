"""CPU health analyzer"""


class CPUAnalyzer:
    """Analyzes show processes cpu output"""
    
    CPU_THRESHOLD = 70  # Percentage
    
    @staticmethod
    def analyze(structured_data, raw_output):
        """
        Analyze CPU health
        
        Returns:
            dict: {
                "status": "OK|CRITICAL|Unknown",
                "cpu_percent": int,
                "details": {...}
            }
        """
        cpu_percent = 0
        cpu_status = "Unknown"
        
        # Try structured data first
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                cpu_str = structured_data[0].get("cpu_utilization", "0%")
                cpu_percent = int(cpu_str.strip("%"))
                cpu_status = "OK" if cpu_percent < CPUAnalyzer.CPU_THRESHOLD else "CRITICAL"
            else:
                raise ValueError("No structured data")
        except Exception:
            # Fallback to manual parsing
            for line in raw_output.splitlines():
                line = line.strip()
                if "CPU utilization" in line:
                    try:
                        cpu_val = line.split(":")[1].split("%")[0].strip()
                        if "/" in cpu_val:
                            cpu_val = cpu_val.split("/")[0].strip()
                        cpu_percent = int(cpu_val)
                        cpu_status = ("OK" if cpu_percent < CPUAnalyzer.CPU_THRESHOLD 
                                    else "CRITICAL")
                        break
                    except Exception:
                        pass
        
        return {
            "status": cpu_status,
            "cpu_percent": cpu_percent,
            "details": {
                "threshold": CPUAnalyzer.CPU_THRESHOLD
            }
        }