"""BGP health analyzer"""
from utils.parsers import BGPParser


class BGPAnalyzer:
    """Analyzes BGP summary and neighbor outputs"""
    
    FLAP_THRESHOLD = 5
    
    @staticmethod
    def analyze_summary(structured_data, raw_output):
        """
        Analyze BGP summary
        
        Returns:
            dict: {
                "status": "OK|CRITICAL|NOT_CONFIGURED",
                "total_neighbors": int,
                "established_neighbors": int,
                "down_neighbors": list,
                "details": {...}
            }
        """
        bgp_neighbors = []
        
        # Try structured data first, fallback to manual
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                bgp_neighbors = structured_data
            else:
                bgp_neighbors = BGPParser.parse_bgp_summary(raw_output)
        except Exception:
            bgp_neighbors = BGPParser.parse_bgp_summary(raw_output)
        
        if not bgp_neighbors:
            return {
                "status": "NOT_CONFIGURED",
                "total_neighbors": 0,
                "established_neighbors": 0,
                "down_neighbors": [],
                "details": {}
            }
        
        total_neighbors = len(bgp_neighbors)
        established_neighbors = 0
        down_neighbors = []
        
        for neighbor in bgp_neighbors:
            neighbor_ip = neighbor.get('neighbor', 'Unknown')
            state = neighbor.get('state', neighbor.get('state_pfxrcd', 'Unknown'))
            
            if state == 'Established' or str(state).isdigit():
                established_neighbors += 1
            else:
                down_neighbors.append({
                    'neighbor': neighbor_ip,
                    'as': neighbor.get('as', 'Unknown'),
                    'state': state
                })
        
        bgp_status = "OK" if established_neighbors == total_neighbors else "CRITICAL"
        
        return {
            "status": bgp_status,
            "total_neighbors": total_neighbors,
            "established_neighbors": established_neighbors,
            "down_neighbors": down_neighbors,
            "details": {
                "neighbors_summary": bgp_neighbors
            }
        }
    
    @staticmethod
    def analyze_neighbors(structured_data, raw_output):
        """
        Analyze BGP neighbors detailed
        
        Returns:
            dict: {
                "high_flap_neighbors": list,
                "neighbor_details": list,
                "details": {...}
            }
        """
        neighbor_details = []
        
        # Try structured data first, fallback to manual
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                neighbor_details = structured_data
            else:
                neighbor_details = BGPParser.parse_bgp_neighbors(raw_output)
        except Exception:
            neighbor_details = BGPParser.parse_bgp_neighbors(raw_output)
        
        high_flap_neighbors = []
        
        for neighbor in neighbor_details:
            flaps = neighbor.get('route_flaps', 0)
            if flaps > BGPAnalyzer.FLAP_THRESHOLD:
                high_flap_neighbors.append({
                    'neighbor': neighbor.get('neighbor', 'Unknown'),
                    'flaps': flaps,
                    'last_reset': neighbor.get('last_reset', 'N/A')
                })
        
        return {
            "high_flap_neighbors": high_flap_neighbors,
            "neighbor_details": neighbor_details,
            "details": {
                "flap_threshold": BGPAnalyzer.FLAP_THRESHOLD
            }
        }