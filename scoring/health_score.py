"""Overall device health scoring"""


class HealthScorer:
    """Calculate overall device health from individual component health"""
    
    @staticmethod
    def calculate_overall_health(interface_health, cpu_health, memory_health, bgp_health):
        """
        Calculate overall device health
        
        Args:
            interface_health (str): "Good" or "Warning"
            cpu_health (str): "OK" or "CRITICAL"
            memory_health (str): "OK" or "CRITICAL"
            bgp_health (str): "OK", "CRITICAL", or "NOT_CONFIGURED"
        
        Returns:
            str: "HEALTHY" or "UNHEALTHY"
        """
        if bgp_health == "NOT_CONFIGURED":
            # BGP not configured, only check other metrics
            if (interface_health == "Good" and 
                cpu_health == "OK" and 
                memory_health == "OK"):
                return "HEALTHY"
            else:
                return "UNHEALTHY"
        else:
            # BGP configured, include in health check
            if (interface_health == "Good" and 
                cpu_health == "OK" and 
                memory_health == "OK" and 
                bgp_health == "OK"):
                return "HEALTHY"
            else:
                return "UNHEALTHY"