"""Manual parsers for command outputs"""
import re


class BGPParser:
    """Manual parsers for BGP commands"""
    
    @staticmethod
    def parse_bgp_summary(raw_output):
        """Parse BGP summary output manually"""
        bgp_neighbors = []
        lines = raw_output.splitlines()
        
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.\d+\.\d+\.\d+', line):
                parts = line.split()
                if len(parts) >= 10:
                    neighbor = {
                        'neighbor': parts[0],
                        'version': parts[1],
                        'as': parts[2],
                        'msg_rcvd': parts[3],
                        'msg_sent': parts[4],
                        'tbl_ver': parts[5],
                        'inq': parts[6],
                        'outq': parts[7],
                        'uptime': parts[8],
                        'state_pfxrcd': parts[9] if len(parts) > 9 else 'Unknown'
                    }
                    
                    try:
                        int(neighbor['state_pfxrcd'])
                        neighbor['state'] = 'Established'
                        neighbor['prefixes_received'] = int(neighbor['state_pfxrcd'])
                    except ValueError:
                        neighbor['state'] = neighbor['state_pfxrcd']
                        neighbor['prefixes_received'] = 0
                    
                    bgp_neighbors.append(neighbor)
        
        return bgp_neighbors
    
    @staticmethod
    def parse_bgp_neighbors(raw_output):
        """Parse BGP neighbors detailed output manually"""
        neighbor_details = []
        current_neighbor = None
        lines = raw_output.splitlines()
        
        for line in lines:
            line_stripped = line.strip()
            
            if line_stripped.startswith("BGP neighbor is"):
                if current_neighbor:
                    neighbor_details.append(current_neighbor)
                
                match = re.search(r'BGP neighbor is (\d+\.\d+\.\d+\.\d+)', line_stripped)
                if match:
                    current_neighbor = {
                        'neighbor': match.group(1),
                        'remote_as': None,
                        'state': None,
                        'uptime': None,
                        'prefixes_received': 0,
                        'prefixes_sent': 0,
                        'route_flaps': 0,
                        'last_reset': None
                    }
            
            if current_neighbor:
                if "remote AS" in line_stripped:
                    match = re.search(r'remote AS (\d+)', line_stripped)
                    if match:
                        current_neighbor['remote_as'] = match.group(1)
                
                if "BGP state =" in line_stripped:
                    match = re.search(r'BGP state = (\w+)', line_stripped)
                    if match:
                        current_neighbor['state'] = match.group(1)
                    match = re.search(r'up for (\S+)', line_stripped)
                    if match:
                        current_neighbor['uptime'] = match.group(1)
                
                if "Connections established" in line_stripped:
                    match = re.search(r'Connections established (\d+); dropped (\d+)', 
                                    line_stripped)
                    if match:
                        current_neighbor['route_flaps'] = int(match.group(2))
                
                if "Last reset" in line_stripped:
                    current_neighbor['last_reset'] = line_stripped
                
                if ("prefixes" in line_stripped.lower() and 
                    "accepted" in line_stripped.lower()):
                    match = re.search(r'(\d+)\s+prefixes', line_stripped)
                    if match:
                        current_neighbor['prefixes_received'] = int(match.group(1))
        
        if current_neighbor:
            neighbor_details.append(current_neighbor)
        
        return neighbor_details