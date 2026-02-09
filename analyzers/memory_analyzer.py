"""Memory health analyzer"""
import re


class MemoryAnalyzer:
    """Analyzes memory statistics output"""
    
    MEMORY_THRESHOLD = 80  # Percentage
    
    @staticmethod
    def analyze(structured_data, raw_output):
        """
        Analyze memory health from 'show memory statistics'
        
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
                    pool_name = str(entry.get("pool", "")).lower()
                    if "processor" in pool_name:
                        total_memory = int(entry.get("total", 0))
                        free_memory = int(entry.get("free", 0))
                        used_memory = int(entry.get("used", 0))
                        
                        if total_memory > 0:
                            memory_used_percent = int((used_memory / total_memory) * 100)
                            memory_status = ("OK" if memory_used_percent < 
                                           MemoryAnalyzer.MEMORY_THRESHOLD else "CRITICAL")
                        break
            else:
                raise ValueError("No structured data")
        except Exception:
            # Manual parsing for show memory statistics output
            # Expected format:
            #             Head    Total(b)     Used(b)     Free(b)   Lowest(b)  Largest(b)
            # Processor  65BD3F10   315565420   253776452    61788968    60649816    58493096
            
            lines = raw_output.splitlines()
            
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                
                # Look for header line
                if "Head" in line and "Total(b)" in line and "Used(b)" in line:
                    # The next line should have Processor data
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        
                        if next_line.startswith("Processor"):
                            try:
                                # Split and extract numeric values
                                parts = next_line.split()
                                # Format: Processor <hex> <total> <used> <free> <lowest> <largest>
                                if len(parts) >= 5:
                                    total_memory = int(parts[2])  # Total(b)
                                    used_memory = int(parts[3])   # Used(b)
                                    free_memory = int(parts[4])   # Free(b)
                                    
                                    if total_memory > 0:
                                        memory_used_percent = int((used_memory / total_memory) * 100)
                                        memory_status = ("OK" if memory_used_percent < 
                                                       MemoryAnalyzer.MEMORY_THRESHOLD else "CRITICAL")
                                        print(f"  [DEBUG] Memory statistics parsed successfully")
                                    break
                            except (ValueError, IndexError) as e:
                                print(f"  [DEBUG] Parse error: {e}")
                                continue
            
            # Diagnostic output if parsing failed
            if total_memory == 0:
                print(f"  [DEBUG] No memory data found in output")
                print(f"  [DEBUG] Searching in {len(lines)} lines")
                print(f"  [DEBUG] Full output sample (first 15 lines):")
                for i, line in enumerate(lines[:15]):
                    print(f"    {i+1}: {line}")
        
        # Convert to MB
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