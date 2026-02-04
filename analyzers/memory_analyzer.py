"""Memory health analyzer"""


class MemoryAnalyzer:
    """Analyzes show process memory output"""
    
    MEMORY_THRESHOLD = 80  # Percentage
    
    @staticmethod
    def analyze(structured_data, raw_output):
        """
        Analyze memory health
        
        Returns:
            dict: {
                "status": "OK|CRITICAL|Unknown",
                "memory_used_percent": int,
                "memory_total_mb": int,
                "memory_used_mb": int,
                "memory_free_mb": int,
                "details": {...}
            }
        """
        memory_used_percent = 0
        memory_status = "Unknown"
        total_memory = 0
        used_memory = 0
        free_memory = 0
        
        # Try structured data first
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                for entry in structured_data:
                    if "processor" in entry.get("pool", "").lower():
                        total_memory = int(entry.get("total", 0))
                        used_memory = int(entry.get("used", 0))
                        free_memory = int(entry.get("free", 0))
                        if total_memory > 0:
                            memory_used_percent = int((used_memory / total_memory) * 100)
                            memory_status = ("OK" if memory_used_percent < 
                                           MemoryAnalyzer.MEMORY_THRESHOLD else "CRITICAL")
                        break
            else:
                raise ValueError("No structured data")
        except Exception:
            # Fallback to manual parsing
            for line in raw_output.splitlines():
                line = line.strip()
                
                if "Processor" in line and ("Total:" in line or len(line.split()) >= 4):
                    try:
                        parts = line.split()
                        if "Total:" in line:
                            for i, part in enumerate(parts):
                                if part == "Total:":
                                    total_memory = int(parts[i + 1])
                                elif part == "Used:":
                                    used_memory = int(parts[i + 1])
                                elif part == "Free:":
                                    free_memory = int(parts[i + 1])
                        else:
                            if len(parts) >= 4:
                                total_memory = int(parts[1])
                                used_memory = int(parts[2])
                                free_memory = int(parts[3])
                        
                        if total_memory > 0:
                            memory_used_percent = int((used_memory / total_memory) * 100)
                            memory_status = ("OK" if memory_used_percent < 
                                           MemoryAnalyzer.MEMORY_THRESHOLD else "CRITICAL")
                        break
                    except Exception:
                        pass
        
        total_mb = total_memory // (1024 * 1024) if total_memory > 0 else 0
        used_mb = used_memory // (1024 * 1024) if used_memory > 0 else 0
        free_mb = free_memory // (1024 * 1024) if free_memory > 0 else 0
        
        return {
            "status": memory_status,
            "memory_used_percent": memory_used_percent,
            "memory_total_mb": total_mb,
            "memory_used_mb": used_mb,
            "memory_free_mb": free_mb,
            "details": {
                "threshold": MemoryAnalyzer.MEMORY_THRESHOLD
            }
        }