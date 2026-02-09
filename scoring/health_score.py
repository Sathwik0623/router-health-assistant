"""Overall device health scoring"""


class HealthScorer:
    """Calculate overall device health from individual component health"""
    
    @staticmethod
    def calculate_overall_health(component_statuses):
        """
        Calculate overall device health from multiple components
        
        Args:
            component_statuses (dict): {
                "interface_health": "Good|Warning",
                "cpu_health": "OK|CRITICAL|Unknown",
                "memory_health": "OK|CRITICAL|Unknown",
                "bgp_health": "OK|CRITICAL|NOT_CONFIGURED",
                "ospf_health": "OK|WARNING|CRITICAL|NOT_CONFIGURED",
                ...
            }
        
        Returns:
            str: "HEALTHY" or "UNHEALTHY"
        """
        # Extract component statuses with defaults
        interface_health = component_statuses.get("interface_health", "Unknown")
        cpu_health = component_statuses.get("cpu_health", "Unknown")
        memory_health = component_statuses.get("memory_health", "Unknown")
        bgp_health = component_statuses.get("bgp_health", "NOT_CONFIGURED")
        ospf_health = component_statuses.get("ospf_health", "NOT_CONFIGURED")
        
        # Critical components that must be OK for HEALTHY status
        critical_checks = [
            interface_health in ["Good"],
            cpu_health in ["OK"],
            memory_health in ["OK"]
        ]
        
        # If any critical component is not OK, device is UNHEALTHY
        if not all(critical_checks):
            return "UNHEALTHY"
        
        # Check BGP health only if configured
        if bgp_health != "NOT_CONFIGURED" and bgp_health not in ["OK"]:
            return "UNHEALTHY"
        
        # Check OSPF health only if configured
        if ospf_health != "NOT_CONFIGURED":
            # CRITICAL OSPF issues make device UNHEALTHY
            if ospf_health == "CRITICAL":
                return "UNHEALTHY"
            # WARNING is acceptable (device still HEALTHY but needs attention)
            # This allows for LSA warnings without failing health check
        
        # All checks passed
        return "HEALTHY"