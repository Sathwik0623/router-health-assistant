"""Manual rule-based health explanation generator (no AI API required)"""


class ManualExplainer:
    """Generate device health explanations using rules"""
    
    @staticmethod
    def explain_device_health(device_name, device_data):
        """
        Generate explanation based on rules
        
        Args:
            device_name (str): Device hostname
            device_data (dict): Device health summary
        
        Returns:
            str: Formatted explanation
        """
        lines = []
        lines.append(f"**Health Report for {device_name}**")
        lines.append("="*50 + "\n")
        
        overall = device_data.get('overall_health', 'Unknown')
        
        # Overall Status
        if overall == "HEALTHY":
            lines.append("✓ **Overall Status: HEALTHY**")
            lines.append("All critical systems are operational.\n")
        elif overall == "UNHEALTHY":
            lines.append("✗ **Overall Status: UNHEALTHY**")
            lines.append("One or more critical issues detected.\n")
        else:
            lines.append(f"⚠ **Overall Status: {overall}**\n")
        
        lines.append("**Component Analysis:**\n")
        
        # CPU Analysis
        cpu_health = device_data.get('cpu_health', 'Unknown')
        cpu_percent = device_data.get('cpu_percent', 'N/A')
        
        if cpu_health == "OK":
            lines.append(f"✓ **CPU:** {cpu_health} ({cpu_percent}%)")
            lines.append("  - CPU utilization is within normal operating range\n")
        elif cpu_health == "CRITICAL":
            lines.append(f"✗ **CPU:** {cpu_health} ({cpu_percent}%)")
            lines.append("  - **Issue:** High CPU utilization detected")
            lines.append("  - **Impact:** May affect device performance and responsiveness")
            lines.append("  - **Action:** Investigate high CPU processes")
            lines.append("  - **Commands:** `show processes cpu sorted`, `show processes cpu history`\n")
        else:
            lines.append(f"⚠ **CPU:** {cpu_health}")
            lines.append("  - **Issue:** CPU status could not be determined")
            lines.append("  - **Action:** Manually verify with `show processes cpu`\n")
        
        # Memory Analysis
        mem_health = device_data.get('memory_health', 'Unknown')
        mem_percent = device_data.get('memory_used_percent', 'N/A')
        mem_total = device_data.get('memory_total_mb', 'N/A')
        mem_used = device_data.get('memory_used_mb', 'N/A')
        
        if mem_health == "OK":
            lines.append(f"✓ **Memory:** {mem_health} ({mem_percent}%)")
            lines.append(f"  - Total: {mem_total} MB, Used: {mem_used} MB")
            lines.append("  - Memory utilization is healthy\n")
        elif mem_health == "CRITICAL":
            lines.append(f"✗ **Memory:** {mem_health} ({mem_percent}%)")
            lines.append(f"  - Total: {mem_total} MB, Used: {mem_used} MB")
            lines.append("  - **Issue:** High memory utilization")
            lines.append("  - **Impact:** Risk of memory exhaustion and process failures")
            lines.append("  - **Action:** Identify memory-intensive processes")
            lines.append("  - **Commands:** `show processes memory sorted`, `show memory statistics`\n")
        else:
            lines.append(f"⚠ **Memory:** {mem_health}")
            lines.append("  - **Issue:** Memory status could not be determined")
            lines.append("  - **Action:** Verify memory manually")
            lines.append("  - **Commands:** `show memory statistics`, `show processes memory`\n")
        
        # Interface Analysis
        iface_health = device_data.get('interface_health', 'Unknown')
        ifaces_down = device_data.get('interfaces_down', [])
        
        if iface_health == "Good":
            lines.append(f"✓ **Interfaces:** {iface_health}")
            lines.append("  - All assigned-IP interfaces are operational\n")
        elif iface_health == "Warning":
            lines.append(f"⚠ **Interfaces:** {iface_health}")
            lines.append(f"  - **Issue:** {len(ifaces_down)} interface(s) down")
            for intf in ifaces_down[:3]:
                if isinstance(intf, dict):
                    lines.append(f"    • {intf.get('interface')}: {intf.get('status')}/{intf.get('protocol')}")
            lines.append("  - **Action:** Check interface configuration and physical connectivity")
            lines.append("  - **Commands:** `show interface <name>`, `show ip interface <name>`\n")
        
        # Routing Table
        total_routes = device_data.get('total_routes', 'N/A')
        lines.append(f"ℹ **Routing Table:** {total_routes} routes")
        
        if isinstance(total_routes, int):
            if total_routes == 0:
                lines.append("  - **Warning:** No routes in routing table")
                lines.append("  - **Action:** Verify routing protocols and static routes\n")
            elif total_routes < 5:
                lines.append("  - **Note:** Limited routing table - may be expected for lab/test environment\n")
            else:
                lines.append("")
        
        # BGP Analysis
        bgp_health = device_data.get('bgp_health', 'NOT_CONFIGURED')
        
        if bgp_health == "NOT_CONFIGURED":
            lines.append("ℹ **BGP:** Not configured\n")
        elif bgp_health == "OK":
            bgp_est = device_data.get('bgp_established_neighbors', 0)
            bgp_total = device_data.get('bgp_total_neighbors', 0)
            lines.append(f"✓ **BGP:** {bgp_health}")
            lines.append(f"  - All neighbors established ({bgp_est}/{bgp_total})\n")
        elif bgp_health == "CRITICAL":
            bgp_est = device_data.get('bgp_established_neighbors', 0)
            bgp_total = device_data.get('bgp_total_neighbors', 0)
            bgp_down = device_data.get('bgp_down_neighbors', [])
            lines.append(f"✗ **BGP:** {bgp_health}")
            lines.append(f"  - **Issue:** {len(bgp_down)} BGP neighbor(s) down")
            lines.append(f"  - Established: {bgp_est}/{bgp_total}")
            for neighbor in bgp_down[:3]:
                lines.append(f"    • {neighbor.get('neighbor')} (AS {neighbor.get('as')}): {neighbor.get('state')}")
            lines.append("  - **Action:** Investigate BGP neighbor connectivity")
            lines.append("  - **Commands:** `show ip bgp summary`, `show ip bgp neighbors <ip>`\n")
        
        # BGP Flaps
        bgp_flaps = device_data.get('bgp_high_flap_neighbors', [])
        if bgp_flaps:
            lines.append(f"⚠ **BGP Stability Issue:**")
            lines.append(f"  - {len(bgp_flaps)} neighbor(s) experiencing high flap count")
            for neighbor in bgp_flaps[:2]:
                lines.append(f"    • {neighbor.get('neighbor')}: {neighbor.get('flaps')} flaps")
            lines.append("  - **Possible Causes:** Link instability, configuration mismatch, route dampening")
            lines.append("  - **Action:** Check BGP logs and neighbor reachability\n")
        
        # OSPF Analysis (NEW)
        ospf_health = device_data.get('ospf_health', 'NOT_CONFIGURED')
        
        if ospf_health == "NOT_CONFIGURED":
            lines.append("ℹ **OSPF:** Not configured\n")
        elif ospf_health == "OK":
            ospf_full = device_data.get('ospf_full_neighbors', 0)
            ospf_total = device_data.get('ospf_total_neighbors', 0)
            ospf_lsas = device_data.get('ospf_lsa_total', 0)
            ospf_areas = device_data.get('ospf_neighbors_by_area', {})
            
            lines.append(f"✓ **OSPF:** {ospf_health}")
            lines.append(f"  - All neighbors in FULL state ({ospf_full}/{ospf_total})")
            
            if ospf_areas:
                lines.append("  - Neighbors by Area:")
                for area, stats in ospf_areas.items():
                    lines.append(f"    • Area {area}: {stats['full']}/{stats['total']} FULL")
            
            lines.append(f"  - LSA database: {ospf_lsas} LSAs\n")
        elif ospf_health == "CRITICAL":
            ospf_full = device_data.get('ospf_full_neighbors', 0)
            ospf_total = device_data.get('ospf_total_neighbors', 0)
            ospf_down = device_data.get('ospf_down_neighbors', [])
            
            lines.append(f"✗ **OSPF:** {ospf_health}")
            lines.append(f"  - **Issue:** {len(ospf_down)} OSPF neighbor(s) NOT in FULL state")
            lines.append(f"  - FULL neighbors: {ospf_full}/{ospf_total}")
            
            for neighbor in ospf_down[:3]:
                lines.append(f"    • Neighbor {neighbor.get('neighbor_id')} "
                            f"on {neighbor.get('interface')}: {neighbor.get('state')} "
                            f"(Area {neighbor.get('area')})")
            
            lines.append("  - **Possible Causes:**")
            lines.append("    • Interface down or unstable")
            lines.append("    • OSPF network type mismatch")
            lines.append("    • Area mismatch configuration")
            lines.append("    • OSPF authentication failure")
            lines.append("    • MTU mismatch between neighbors")
            lines.append("    • Subnet mask mismatch")
            lines.append("  - **Action:** Investigate OSPF neighbor adjacency issues")
            lines.append("  - **Commands:**")
            lines.append("    • `show ip ospf neighbor detail`")
            lines.append("    • `show ip ospf interface <interface>`")
            lines.append("    • `show ip ospf database`")
            lines.append("    • `debug ip ospf adj` (use with caution in production)\n")
        elif ospf_health == "WARNING":
            ospf_lsas = device_data.get('ospf_lsa_total', 0)
            flooding = device_data.get('ospf_flooding_detected', False)
            low_dead_time = device_data.get('ospf_low_dead_time_neighbors', [])
            
            lines.append(f"⚠ **OSPF:** {ospf_health}")
            
            if flooding:
                lines.append(f"  - **Issue:** Potential LSA flooding detected ({ospf_lsas} LSAs)")
                lines.append("  - **Possible Causes:**")
                lines.append("    • Routing loops causing excessive LSA generation")
                lines.append("    • Large network with many external routes redistributed")
                lines.append("    • LSA origination issues or misconfigurations")
                lines.append("  - **Action:** Investigate LSA sources and redistribution")
                lines.append("  - **Commands:**")
                lines.append("    • `show ip ospf database`")
                lines.append("    • `show ip ospf database external`")
                lines.append("    • `show ip ospf database summary`")
            
            if low_dead_time:
                lines.append(f"  - **Issue:** {len(low_dead_time)} neighbor(s) with low dead timer")
                for neighbor in low_dead_time[:2]:
                    lines.append(f"    • {neighbor.get('neighbor_id')} on {neighbor.get('interface')}: "
                                f"{neighbor.get('dead_time')} remaining")
                lines.append("  - **Indicates:** Potential link instability or hello packet loss")
                lines.append("  - **Action:** Monitor for neighbor flapping")
                lines.append("  - **Commands:** `show ip ospf neighbor`, `show interface counters errors`\n")
        
        # Troubleshooting Priority
        lines.append("**Recommended Actions:**\n")
        
        if overall == "HEALTHY":
            lines.append("✓ No immediate actions required")
            lines.append("✓ Continue routine monitoring")
            lines.append("✓ All systems operational")
        else:
            priority = 1
            
            if mem_health == "Unknown":
                lines.append(f"{priority}. **HIGH PRIORITY:** Resolve memory monitoring issue")
                lines.append("   - Verify device accessibility and command execution")
                priority += 1
            
            if cpu_health == "CRITICAL":
                lines.append(f"{priority}. **HIGH PRIORITY:** Investigate high CPU usage")
                lines.append("   - Run `show processes cpu sorted` to identify top consumers")
                priority += 1
            
            if mem_health == "CRITICAL":
                lines.append(f"{priority}. **HIGH PRIORITY:** Address high memory utilization")
                lines.append("   - Run `show processes memory sorted` to identify memory leaks")
                priority += 1
            
            if ospf_health == "CRITICAL":
                lines.append(f"{priority}. **HIGH PRIORITY:** Restore OSPF neighbor adjacencies")
                lines.append("   - Check OSPF configuration and interface states")
                priority += 1
            
            if bgp_health == "CRITICAL":
                lines.append(f"{priority}. **MEDIUM PRIORITY:** Restore BGP neighbor sessions")
                lines.append("   - Check network connectivity to BGP peers")
                priority += 1
            
            if ifaces_down:
                lines.append(f"{priority}. **MEDIUM PRIORITY:** Bring up down interfaces")
                lines.append("   - Verify physical connectivity and interface configuration")
                priority += 1
            
            if ospf_health == "WARNING":
                lines.append(f"{priority}. **LOW PRIORITY:** Monitor OSPF stability")
                lines.append("   - Watch for LSA flooding or dead timer issues")
                priority += 1
        
        lines.append("\n" + "="*50)
        
        return "\n".join(lines)
    
    @staticmethod
    def explain_network_health(device_summaries):
        """Generate network-wide analysis"""
        lines = []
        lines.append("**Network-Wide Health Analysis**")
        lines.append("="*50 + "\n")
        
        device_count = len([d for d in device_summaries if d != 'network_analysis'])
        healthy_count = sum(1 for s in device_summaries.values() 
                           if isinstance(s, dict) and s.get('overall_health') == 'HEALTHY')
        unhealthy_count = device_count - healthy_count
        
        lines.append(f"**Network Summary:**")
        lines.append(f"- Total Devices: {device_count}")
        lines.append(f"- Healthy: {healthy_count} ({healthy_count/device_count*100:.0f}%)")
        lines.append(f"- Unhealthy: {unhealthy_count}\n")
        
        if healthy_count == device_count:
            lines.append("✓ **Network Status: OPTIMAL**")
            lines.append("All devices are operating normally.\n")
        else:
            lines.append(f"⚠ **Network Status: ATTENTION REQUIRED**")
            lines.append(f"{unhealthy_count} device(s) require investigation.\n")
        
        # Routing Protocol Summary
        ospf_count = sum(1 for s in device_summaries.values() 
                        if isinstance(s, dict) and 
                        s.get('ospf_health') not in ['NOT_CONFIGURED', None])
        bgp_count = sum(1 for s in device_summaries.values() 
                       if isinstance(s, dict) and 
                       s.get('bgp_health') not in ['NOT_CONFIGURED', None])
        
        if ospf_count > 0 or bgp_count > 0:
            lines.append("**Routing Protocol Status:**")
            if ospf_count > 0:
                lines.append(f"- OSPF enabled on {ospf_count} device(s)")
            if bgp_count > 0:
                lines.append(f"- BGP enabled on {bgp_count} device(s)")
            lines.append("")
        
        lines.append("**Device-by-Device Status:**\n")
        
        for device, data in device_summaries.items():
            if device == 'network_analysis' or not isinstance(data, dict):
                continue
            
            health = data.get('overall_health', 'Unknown')
            cpu = data.get('cpu_percent', 'N/A')
            mem = data.get('memory_used_percent', 'N/A')
            ospf = data.get('ospf_health', 'N/A')
            
            if health == "HEALTHY":
                lines.append(f"✓ {device}: {health} (CPU: {cpu}%, Mem: {mem}%, OSPF: {ospf})")
            else:
                lines.append(f"✗ {device}: {health} (CPU: {cpu}%, Mem: {mem}%, OSPF: {ospf})")
        
        lines.append("\n**Recommendations:**\n")
        
        if unhealthy_count == 0:
            lines.append("- Continue routine monitoring")
            lines.append("- No immediate actions required")
            lines.append("- All network devices operational")
        else:
            lines.append(f"- Prioritize investigation of {unhealthy_count} unhealthy device(s)")
            lines.append("- Review device-specific explanations above for details")
            lines.append("- Check for network-wide issues if multiple devices affected")
            lines.append("- Verify routing protocol stability across the network")
        
        lines.append("\n" + "="*50)
        
        return "\n".join(lines)