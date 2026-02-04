"""Routing table analyzer"""


class RoutingAnalyzer:
    """Analyzes show ip route output"""
    
    @staticmethod
    def analyze(structured_data, raw_output):
        """
        Analyze routing table
        
        Returns:
            dict: {
                "status": "OK",
                "total_routes": int,
                "details": {...}
            }
        """
        total_routes = 0
        
        if isinstance(structured_data, list):
            total_routes = len(structured_data)
        
        return {
            "status": "OK",
            "total_routes": total_routes,
            "details": {
                "routes": structured_data[:3] if structured_data else []
            }
        }