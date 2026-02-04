"""Interface health analyzer"""


class InterfaceAnalyzer:
    """Analyzes show ip interface brief output"""
    
    @staticmethod
    def analyze(structured_data, raw_output):
        """
        Analyze interface health
        
        Returns:
            dict: {
                "status": "Good|Warning",
                "interfaces_down": list,
                "details": {...}
            }
        """
        down_interfaces = []
        
        if isinstance(structured_data, list):
            for intf in structured_data:
                intf_name = intf.get("interface", "unknown")
                ip_addr = (intf.get("ipaddr") or "unassigned").lower()
                status = (intf.get("status") or "").lower()
                protocol = (intf.get("protocol") or "").lower()
                
                # Only check interfaces with assigned IPs
                if ip_addr != "unassigned":
                    if status != "up" or protocol != "up":
                        down_interfaces.append({
                            "interface": intf_name,
                            "status": status,
                            "protocol": protocol
                        })
        
        return {
            "status": "Warning" if down_interfaces else "Good",
            "interfaces_down": down_interfaces,
            "details": {
                "total_checked": len(structured_data) if structured_data else 0
            }
        }