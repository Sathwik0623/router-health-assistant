"""OSPF health analyzer"""
import re
from config.thresholds import (
    OSPF_NEIGHBOR_DOWN_CRITICAL,
    OSPF_LSA_FLOOD_THRESHOLD,
    OSPF_DEAD_TIME_WARNING_SECONDS
)


class OSPFAnalyzer:
    """Analyzes OSPF neighbor states and database health"""
    
    @staticmethod
    def analyze_neighbors(structured_data, raw_output):
        """
        Analyze OSPF neighbor states
        
        Returns:
            dict: {
                "status": "OK|WARNING|CRITICAL|NOT_CONFIGURED",
                "total_neighbors": int,
                "full_neighbors": int,
                "down_neighbors": list,
                "neighbors_by_area": dict,
                "low_dead_time_neighbors": list,
                "details": {...}
            }
        """
        neighbors = []
        
        # Try structured data first, fallback to manual parsing
        if isinstance(structured_data, list) and len(structured_data) > 0:
            neighbors = structured_data
        else:
            neighbors = OSPFAnalyzer._parse_ospf_neighbors_manual(raw_output)
        
        if not neighbors:
            return {
                "status": "NOT_CONFIGURED",
                "total_neighbors": 0,
                "full_neighbors": 0,
                "down_neighbors": [],
                "neighbors_by_area": {},
                "low_dead_time_neighbors": [],
                "details": {"reason": "OSPF not configured or no neighbors found"}
            }
        
        # Analyze neighbor states
        total_neighbors = len(neighbors)
        full_neighbors = 0
        down_neighbors = []
        neighbors_by_area = {}
        low_dead_time_neighbors = []
        
        for neighbor in neighbors:
            neighbor_id = neighbor.get('neighbor_id', 'Unknown')
            state = neighbor.get('state', '').upper()
            interface = neighbor.get('interface', 'Unknown')
            dead_time = neighbor.get('dead_time', '00:00:00')
            priority = neighbor.get('priority', 0)
            address = neighbor.get('address', 'Unknown')
            
            # Extract area from interface or default to 0
            area = neighbor.get('area', '0.0.0.0')
            if area not in neighbors_by_area:
                neighbors_by_area[area] = {'total': 0, 'full': 0, 'down': 0}
            neighbors_by_area[area]['total'] += 1
            
            # Check neighbor state
            if 'FULL' in state:
                full_neighbors += 1
                neighbors_by_area[area]['full'] += 1
            else:
                down_neighbors.append({
                    'neighbor_id': neighbor_id,
                    'state': state,
                    'interface': interface,
                    'address': address,
                    'area': area,
                    'priority': priority
                })
                neighbors_by_area[area]['down'] += 1
            
            # Check for low dead timers (potential instability)
            dead_seconds = OSPFAnalyzer._parse_dead_time(dead_time)
            if dead_seconds is not None and dead_seconds <= OSPF_DEAD_TIME_WARNING_SECONDS:
                low_dead_time_neighbors.append({
                    'neighbor_id': neighbor_id,
                    'interface': interface,
                    'dead_time': dead_time,
                    'dead_seconds': dead_seconds
                })
        
        # Determine overall OSPF neighbor health
        if down_neighbors:
            status = "CRITICAL"
        elif low_dead_time_neighbors:
            status = "WARNING"
        else:
            status = "OK"
        
        return {
            "status": status,
            "total_neighbors": total_neighbors,
            "full_neighbors": full_neighbors,
            "down_neighbors": down_neighbors,
            "neighbors_by_area": neighbors_by_area,
            "low_dead_time_neighbors": low_dead_time_neighbors,
            "details": {
                "neighbors": neighbors,
                "threshold": OSPF_NEIGHBOR_DOWN_CRITICAL
            }
        }
    
    @staticmethod
    def analyze_database(structured_data, raw_output):
        """
        Analyze OSPF LSA database for flooding or anomalies
        
        Returns:
            dict: {
                "status": "OK|WARNING",
                "total_lsas": int,
                "lsa_by_type": dict,
                "lsa_by_area": dict,
                "flooding_detected": bool,
                "details": {...}
            }
        """
        lsa_by_type = {}
        lsa_by_area = {}
        total_lsas = 0
        
        # Parse LSA database from raw output
        lines = raw_output.splitlines()
        current_area = None
        current_type = None
        
        for line in lines:
            line_stripped = line.strip()
            
            # Detect area and LSA type
            # Example: "Router Link States (Area 0)"
            if "Link States" in line:
                type_match = re.search(r'(\w+(?:\s+\w+)*)\s+Link States.*Area\s+([0-9.]+)', line)
                if type_match:
                    current_type = type_match.group(1).strip()
                    current_area = type_match.group(2)
                    
                    if current_type not in lsa_by_type:
                        lsa_by_type[current_type] = 0
                    if current_area not in lsa_by_area:
                        lsa_by_area[current_area] = 0
            
            # Count LSA entries (lines with Link ID patterns)
            if current_type and re.match(r'^\d+\.\d+\.\d+\.\d+', line_stripped):
                parts = line_stripped.split()
                if len(parts) >= 3:  # Valid LSA entry
                    lsa_by_type[current_type] += 1
                    if current_area:
                        lsa_by_area[current_area] += 1
                    total_lsas += 1
        
        # Check for LSA flooding
        flooding_detected = total_lsas > OSPF_LSA_FLOOD_THRESHOLD
        
        # Determine status
        if flooding_detected:
            status = "WARNING"
        else:
            status = "OK"
        
        return {
            "status": status,
            "total_lsas": total_lsas,
            "lsa_by_type": lsa_by_type,
            "lsa_by_area": lsa_by_area,
            "flooding_detected": flooding_detected,
            "details": {
                "flood_threshold": OSPF_LSA_FLOOD_THRESHOLD,
                "recommendation": "Check for routing loops or LSA origination issues" if flooding_detected else None
            }
        }
    
    @staticmethod
    def analyze_interfaces(structured_data, raw_output):
        """
        Analyze OSPF interface states
        
        Returns:
            dict: {
                "status": "OK|WARNING",
                "total_interfaces": int,
                "ospf_enabled_interfaces": list,
                "passive_interfaces": list,
                "issues": list
            }
        """
        interfaces = []
        issues = []
        
        # Parse OSPF interface brief
        if isinstance(structured_data, list):
            interfaces = structured_data
        else:
            interfaces = OSPFAnalyzer._parse_ospf_interfaces_manual(raw_output)
        
        ospf_enabled = []
        passive = []
        
        for intf in interfaces:
            intf_name = intf.get('interface', 'Unknown')
            state = intf.get('state', 'Unknown')
            neighbors = intf.get('neighbors', 0)
            area = intf.get('area', '0.0.0.0')
            
            ospf_enabled.append({
                'interface': intf_name,
                'area': area,
                'state': state,
                'neighbors': neighbors
            })
            
            # Check for potential issues
            if state and state.upper() in ['DOWN', 'WAITING']:
                issues.append({
                    'interface': intf_name,
                    'issue': f'Interface state is {state}',
                    'area': area
                })
        
        status = "WARNING" if issues else "OK"
        
        return {
            "status": status,
            "total_interfaces": len(interfaces),
            "ospf_enabled_interfaces": ospf_enabled,
            "passive_interfaces": passive,
            "issues": issues,
            "details": {}
        }
    
    @staticmethod
    def _parse_ospf_neighbors_manual(raw_output):
        """Manual parser for OSPF neighbors"""
        neighbors = []
        lines = raw_output.splitlines()
        
        # Expected format:
        # Neighbor ID     Pri   State           Dead Time   Address         Interface
        # 10.1.12.2         1   FULL/DR         00:00:37    10.1.12.2       GigabitEthernet0/0
        
        for line in lines:
            line_stripped = line.strip()
            # Look for lines starting with IP address (neighbor ID)
            if re.match(r'^\d+\.\d+\.\d+\.\d+', line_stripped):
                parts = line_stripped.split()
                if len(parts) >= 6:
                    neighbors.append({
                        'neighbor_id': parts[0],
                        'priority': parts[1],
                        'state': parts[2],
                        'dead_time': parts[3],
                        'address': parts[4],
                        'interface': parts[5],
                        'area': '0.0.0.0'  # Default, area not in this output
                    })
        
        return neighbors
    
    @staticmethod
    def _parse_ospf_interfaces_manual(raw_output):
        """Manual parser for OSPF interface brief"""
        interfaces = []
        lines = raw_output.splitlines()
        
        for line in lines:
            # Look for interface lines
            if re.match(r'^[A-Za-z]+[0-9/]+', line.strip()):
                parts = line.split()
                if len(parts) >= 4:
                    interfaces.append({
                        'interface': parts[0],
                        'area': parts[1] if len(parts) > 1 else '0.0.0.0',
                        'state': parts[2] if len(parts) > 2 else 'Unknown',
                        'neighbors': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                    })
        
        return interfaces
    
    @staticmethod
    def _parse_dead_time(dead_time_str):
        """
        Parse OSPF dead time string to seconds
        
        Args:
            dead_time_str (str): Format like "00:00:37" or "00:01:30"
        
        Returns:
            int: Total seconds, or None if parse fails
        """
        try:
            parts = dead_time_str.split(':')
            if len(parts) == 3:
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
        except Exception:
            pass
        return None