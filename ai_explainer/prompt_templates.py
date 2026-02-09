"""Prompt templates for AI explanation generation"""
from config.thresholds import OSPF_LSA_FLOOD_THRESHOLD, OSPF_DEAD_TIME_WARNING_SECONDS


class PromptTemplates:
    """System and user prompt templates for network health explanation"""
    
    SYSTEM_PROMPT = """You are an expert Cisco network engineer assistant specializing in device health analysis and troubleshooting.

Your role is to:
1. Analyze device health data and CLI output from Cisco IOS devices
2. Explain WHY a device might be unhealthy in clear, technical language
3. Identify which components need attention
4. Suggest specific, actionable troubleshooting steps

Important guidelines:
- Base explanations ONLY on the data provided - do not hallucinate or assume information
- Be concise but technically accurate
- Focus on root causes, not just symptoms
- Prioritize critical issues (CPU, memory, routing protocols) over warnings
- Provide specific Cisco IOS commands for troubleshooting when relevant
- If data is missing or unknown, explicitly state that and suggest how to obtain it
- Use clear, professional language suitable for network engineers

Output format:
- Start with a brief overall assessment (1-2 sentences)
- List specific issues found (bullet points)
- Provide prioritized troubleshooting steps
- Keep total response under 300 words"""

    @staticmethod
    def build_device_health_prompt(device_name, device_data):
        """
        Build a prompt for device health explanation
        
        Args:
            device_name (str): Device hostname
            device_data (dict): Device health summary data
        
        Returns:
            str: Formatted prompt for AI
        """
        # Extract key metrics
        reachable = device_data.get('reachable', False)
        overall_health = device_data.get('overall_health', 'Unknown')
        
        interface_health = device_data.get('interface_health', 'Unknown')
        interfaces_down = device_data.get('interfaces_down', [])
        
        cpu_health = device_data.get('cpu_health', 'Unknown')
        cpu_percent = device_data.get('cpu_percent', 'N/A')
        
        memory_health = device_data.get('memory_health', 'Unknown')
        memory_percent = device_data.get('memory_used_percent', 'N/A')
        memory_total_mb = device_data.get('memory_total_mb', 'N/A')
        memory_used_mb = device_data.get('memory_used_mb', 'N/A')
        
        bgp_health = device_data.get('bgp_health', 'NOT_CONFIGURED')
        bgp_total = device_data.get('bgp_total_neighbors', 0)
        bgp_established = device_data.get('bgp_established_neighbors', 0)
        bgp_down = device_data.get('bgp_down_neighbors', [])
        bgp_high_flap = device_data.get('bgp_high_flap_neighbors', [])
        
        ospf_health = device_data.get('ospf_health', 'NOT_CONFIGURED')
        ospf_total = device_data.get('ospf_total_neighbors', 0)
        ospf_full = device_data.get('ospf_full_neighbors', 0)
        ospf_down = device_data.get('ospf_down_neighbors', [])
        ospf_lsa_total = device_data.get('ospf_lsa_total', 0)
        ospf_flooding = device_data.get('ospf_flooding_detected', False)
        ospf_areas = device_data.get('ospf_neighbors_by_area', {})
        ospf_low_dead = device_data.get('ospf_low_dead_time_neighbors', [])
        
        total_routes = device_data.get('total_routes', 'N/A')
        
        # Build the prompt
        prompt = f"""Analyze the following Cisco device health data and provide a clear explanation:

**Device:** {device_name}
**Reachable:** {"Yes" if reachable else "No"}
**Overall Health:** {overall_health}

**Component Status:**

**Interfaces:**
- Status: {interface_health}
- Interfaces Down: {len(interfaces_down)} interface(s)
"""
        
        if interfaces_down:
            prompt += "- Down Interface Details:\n"
            for intf in interfaces_down[:5]:
                if isinstance(intf, dict):
                    prompt += f"  - {intf.get('interface', 'Unknown')}: {intf.get('status', 'unknown')}/{intf.get('protocol', 'unknown')}\n"
                else:
                    prompt += f"  - {intf}\n"
        
        prompt += f"""
**CPU:**
- Status: {cpu_health}
- Utilization: {cpu_percent}%

**Memory:**
- Status: {memory_health}
- Utilization: {memory_percent}%
- Total: {memory_total_mb} MB
- Used: {memory_used_mb} MB

**Routing Table:**
- Total Routes: {total_routes}

**BGP:**
- Status: {bgp_health}
"""
        
        if bgp_health != "NOT_CONFIGURED":
            prompt += f"- Neighbors: {bgp_established}/{bgp_total} Established\n"
            if bgp_down:
                prompt += "- Down Neighbors:\n"
                for neighbor in bgp_down[:3]:
                    prompt += f"  - {neighbor.get('neighbor', 'Unknown')} (AS {neighbor.get('as', '?')}): {neighbor.get('state', 'Unknown')}\n"
            if bgp_high_flap:
                prompt += "- High Flap Neighbors:\n"
                for neighbor in bgp_high_flap[:3]:
                    prompt += f"  - {neighbor.get('neighbor', 'Unknown')}: {neighbor.get('flaps', 0)} flaps\n"
        
        prompt += f"""
**OSPF:**
- Status: {ospf_health}
"""
        
        if ospf_health != "NOT_CONFIGURED":
            prompt += f"- Neighbors: {ospf_full}/{ospf_total} FULL\n"
            
            # Show area breakdown
            if ospf_areas:
                prompt += "- Neighbors by Area:\n"
                for area, stats in ospf_areas.items():
                    prompt += f"  - Area {area}: {stats['full']}/{stats['total']} FULL\n"
            
            # Show down neighbors
            if ospf_down:
                prompt += "- Down Neighbors:\n"
                for neighbor in ospf_down[:3]:
                    prompt += (f"  - {neighbor.get('neighbor_id', 'Unknown')} "
                              f"on {neighbor.get('interface', 'Unknown')}: "
                              f"{neighbor.get('state', 'Unknown')} "
                              f"(Area {neighbor.get('area', '0')})\n")
            
            # LSA database info
            prompt += f"- LSA Database: {ospf_lsa_total} total LSAs\n"
            if ospf_flooding:
                prompt += f"  ⚠ WARNING: Potential LSA flooding detected (>{OSPF_LSA_FLOOD_THRESHOLD} LSAs)\n"
            
            # Low dead time warnings
            if ospf_low_dead:
                prompt += f"- Low Dead Time: {len(ospf_low_dead)} neighbor(s) with dead timer < {OSPF_DEAD_TIME_WARNING_SECONDS}s\n"
        
        prompt += f"""
---

Based on this data, provide:
1. A brief overall assessment of {device_name}'s health
2. Specific issues identified (prioritized by severity)
3. Root cause analysis for the {overall_health} status
4. Concrete troubleshooting steps with relevant Cisco IOS commands
5. Any missing data that should be investigated

Keep your response concise, technical, and actionable for a network engineer."""

        return prompt
    
    @staticmethod
    def build_comparison_prompt(device_summaries):
        """Build a prompt for comparing multiple devices"""
        prompt = """Analyze the following network-wide device health summary and identify patterns, critical issues, and recommended actions:

**Network Health Overview:**

"""
        
        healthy_count = sum(1 for d in device_summaries.values() 
                          if isinstance(d, dict) and d.get('overall_health') == 'HEALTHY')
        total_count = len([d for d in device_summaries if d != 'network_analysis'])
        
        prompt += f"- Total Devices: {total_count}\n"
        prompt += f"- Healthy: {healthy_count}\n"
        prompt += f"- Unhealthy: {total_count - healthy_count}\n\n"
        
        prompt += "**Device Details:**\n\n"
        
        for device_name, data in device_summaries.items():
            if device_name == 'network_analysis' or not isinstance(data, dict):
                continue
                
            prompt += f"**{device_name}:**\n"
            prompt += f"- Overall Health: {data.get('overall_health', 'Unknown')}\n"
            prompt += f"- Reachable: {'Yes' if data.get('reachable') else 'No'}\n"
            prompt += f"- CPU: {data.get('cpu_health', 'Unknown')} ({data.get('cpu_percent', 'N/A')}%)\n"
            prompt += f"- Memory: {data.get('memory_health', 'Unknown')} ({data.get('memory_used_percent', 'N/A')}%)\n"
            prompt += f"- Interfaces: {data.get('interface_health', 'Unknown')}\n"
            prompt += f"- BGP: {data.get('bgp_health', 'N/A')}\n"
            prompt += f"- OSPF: {data.get('ospf_health', 'N/A')}\n"
            
            if data.get('interfaces_down'):
                prompt += f"  - Down Interfaces: {len(data.get('interfaces_down', []))}\n"
            if data.get('bgp_down_neighbors'):
                prompt += f"  - BGP Down Neighbors: {len(data.get('bgp_down_neighbors', []))}\n"
            if data.get('ospf_down_neighbors'):
                prompt += f"  - OSPF Down Neighbors: {len(data.get('ospf_down_neighbors', []))}\n"
            
            prompt += "\n"
        
        prompt += """
Provide:
1. Network-wide patterns or common issues across devices
2. Most critical devices requiring immediate attention (prioritized)
3. Recommended troubleshooting sequence
4. Any systemic issues affecting multiple devices (especially routing protocols)
5. Overall network health assessment

Keep your response concise and actionable."""
        
        return prompt