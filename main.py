"""Main orchestration script for routing health analyzer with AI explanations"""
import os
import json
import time
import yaml
from dotenv import load_dotenv
from virl2_client import ClientLibrary
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from collectors.cisco_ios import CiscoIOSCollector
from analyzers import (
    InterfaceAnalyzer, CPUAnalyzer, MemoryAnalyzer,
    RoutingAnalyzer, BGPAnalyzer, OSPFAnalyzer
)
from scoring.health_score import HealthScorer
from config.commands import CISCO_IOS_COMMANDS
from config.thresholds import OSPF_LSA_FLOOD_THRESHOLD

load_dotenv()

# Configuration
CML_SERVER = os.getenv("ROUTING_HEALTH_CML_SERVER")
USERNAME = os.getenv("ROUTING_HEALTH_CML_USERNAME")
PASSWORD = os.getenv("ROUTING_HEALTH_CML_PASSWORD")
LAB_NAME = os.getenv("ROUTING_HEALTH_LAB_NAME")

# AI Configuration
ENABLE_AI = os.getenv("ENABLE_AI_EXPLANATIONS", "true").lower() == "true"
USE_GEMINI = os.getenv("USE_GEMINI", "true").lower() == "true"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-pro")

device_summary = {}
summary_lock = threading.Lock()


def process_device(device_name, device_info, collector):
    """Process a single device: collect → analyze → score"""
    print(f"\n>>> Connecting to {device_name}...")
    
    # Get proxy connection info
    proxy_conn = next(
        (c for c in device_info.get("connections", {}).values() 
         if c.get("proxy") == "terminal_server"), None
    )
    
    if not proxy_conn:
        return {
            device_name: {
                "reachable": False,
                "overall_health": "UNREACHABLE",
                "error": "No proxy connection configured"
            }
        }
    
    # Step 1: Collect raw outputs
    collection_result = collector.collect_from_device(
        device_name, 
        proxy_conn.get("command"), 
        CISCO_IOS_COMMANDS
    )
    
    if not collection_result["reachable"]:
        return {
            device_name: {
                "reachable": False,
                "overall_health": "UNREACHABLE",
                "error": collection_result.get("error", "Unknown")
            }
        }
    
    print(f"  [✓] Device {device_name} is reachable.")
    
    device_data = {"reachable": True}
    outputs = collection_result["outputs"]
    component_statuses = {}
    
    # Step 2: Analyze each component
    
    # Interface Health
    if "show ip interface brief" in outputs:
        print(f"  Running: show ip interface brief")
        output = outputs["show ip interface brief"]
        result = InterfaceAnalyzer.analyze(output["structured"], output["raw"])
        device_data["interface_health"] = result["status"]
        device_data["interfaces_down"] = result["interfaces_down"]
        component_statuses["interface_health"] = result["status"]
        
        print(f"\n--- Interface Status for {device_name} ---")
        if result["status"] == "Good":
            print("  [✓] All assigned-IP interfaces are UP.")
        else:
            print(f"  [!] DOWN: {len(result['interfaces_down'])} interface(s)")
    
    # Routing Table
    if "show ip route" in outputs:
        print(f"  Running: show ip route")
        output = outputs["show ip route"]
        result = RoutingAnalyzer.analyze(output["structured"], output["raw"])
        device_data["total_routes"] = result["total_routes"]
        
        print(f"\n--- Routing Table Summary for {device_name} ---")
        print(f"  Total routes found: {result['total_routes']}")
    
    # CPU Health
    if "show processes cpu" in outputs:
        print(f"  Running: show processes cpu")
        output = outputs["show processes cpu"]
        result = CPUAnalyzer.analyze(output["structured"], output["raw"])
        device_data["cpu_health"] = result["status"]
        device_data["cpu_percent"] = result["cpu_percent"]
        component_statuses["cpu_health"] = result["status"]
        
        print(f"\n--- CPU Health for {device_name} ---")
        print(f"  Status: {result['status']} ({result['cpu_percent']}%)")
    
    # Memory Health
    if "show memory statistics" in outputs:
        print(f"  Running: show memory statistics")
        output = outputs["show memory statistics"]
        result = MemoryAnalyzer.analyze(output["structured"], output["raw"])
        device_data["memory_health"] = result["status"]
        device_data["memory_used_percent"] = result["memory_used_percent"]
        device_data["memory_total_mb"] = result["memory_total_mb"]
        device_data["memory_used_mb"] = result["memory_used_mb"]
        device_data["memory_free_mb"] = result["memory_free_mb"]
        component_statuses["memory_health"] = result["status"]
        
        print(f"\n--- Memory Health for {device_name} ---")
        print(f"  Total: {result['memory_total_mb']} MB, "
              f"Used: {result['memory_used_mb']} MB ({result['memory_used_percent']}%), "
              f"Free: {result['memory_free_mb']} MB")
        print(f"  Status: {result['status']}")
    
    # BGP Summary
    if "show ip bgp summary" in outputs:
        print(f"  Running: show ip bgp summary")
        output = outputs["show ip bgp summary"]
        result = BGPAnalyzer.analyze_summary(output["structured"], output["raw"])
        device_data["bgp_health"] = result["status"]
        device_data["bgp_total_neighbors"] = result["total_neighbors"]
        device_data["bgp_established_neighbors"] = result["established_neighbors"]
        device_data["bgp_down_neighbors"] = result["down_neighbors"]
        device_data["bgp_neighbors_summary"] = result["details"].get("neighbors_summary", [])
        component_statuses["bgp_health"] = result["status"]
        
        print(f"\n--- BGP Summary for {device_name} ---")
        if result["status"] == "NOT_CONFIGURED":
            print("  [i] BGP not configured")
        else:
            print(f"  Neighbors: {result['established_neighbors']}/{result['total_neighbors']} Established")
    
    # BGP Neighbors Detail
    if "show ip bgp neighbors" in outputs:
        print(f"  Running: show ip bgp neighbors")
        output = outputs["show ip bgp neighbors"]
        result = BGPAnalyzer.analyze_neighbors(output["structured"], output["raw"])
        device_data["bgp_neighbor_details"] = result["neighbor_details"]
        device_data["bgp_high_flap_neighbors"] = result["high_flap_neighbors"]
        
        if result["high_flap_neighbors"]:
            print(f"\n--- BGP Flap Warning for {device_name} ---")
            print(f"  [!] {len(result['high_flap_neighbors'])} neighbor(s) with high flap count")
    
    # OSPF Neighbor Health (NEW)
    if "show ip ospf neighbor" in outputs:
        print(f"  Running: show ip ospf neighbor")
        output = outputs["show ip ospf neighbor"]
        result = OSPFAnalyzer.analyze_neighbors(output["structured"], output["raw"])
        
        device_data["ospf_health"] = result["status"]
        device_data["ospf_total_neighbors"] = result["total_neighbors"]
        device_data["ospf_full_neighbors"] = result["full_neighbors"]
        device_data["ospf_down_neighbors"] = result["down_neighbors"]
        device_data["ospf_neighbors_by_area"] = result["neighbors_by_area"]
        device_data["ospf_low_dead_time_neighbors"] = result["low_dead_time_neighbors"]
        component_statuses["ospf_health"] = result["status"]
        
        print(f"\n--- OSPF Neighbor Status for {device_name} ---")
        if result["status"] == "NOT_CONFIGURED":
            print("  [i] OSPF not configured")
        elif result["status"] == "OK":
            print(f"  [✓] All OSPF neighbors FULL ({result['full_neighbors']}/{result['total_neighbors']})")
            
            # Show neighbors by area
            for area, stats in result["neighbors_by_area"].items():
                print(f"    Area {area}: {stats['full']}/{stats['total']} FULL")
        elif result["status"] == "CRITICAL":
            print(f"  [!] CRITICAL: {len(result['down_neighbors'])} OSPF neighbor(s) NOT in FULL state")
            print(f"    FULL neighbors: {result['full_neighbors']}/{result['total_neighbors']}")
            
            # Show down neighbors
            for neighbor in result["down_neighbors"][:5]:
                print(f"    ✗ {neighbor['neighbor_id']} on {neighbor['interface']} - "
                      f"State: {neighbor['state']} (Area {neighbor['area']})")
        elif result["status"] == "WARNING":
            print(f"  [⚠] WARNING: OSPF instability detected")
            if result["low_dead_time_neighbors"]:
                print(f"    {len(result['low_dead_time_neighbors'])} neighbor(s) with low dead timer")
                for neighbor in result["low_dead_time_neighbors"][:3]:
                    print(f"    ⚠ {neighbor['neighbor_id']} on {neighbor['interface']}: "
                          f"{neighbor['dead_time']} remaining")
    
    # OSPF Database Health (NEW)
    if "show ip ospf database" in outputs:
        print(f"  Running: show ip ospf database")
        output = outputs["show ip ospf database"]
        result = OSPFAnalyzer.analyze_database(output["structured"], output["raw"])
        
        device_data["ospf_lsa_total"] = result["total_lsas"]
        device_data["ospf_lsa_by_type"] = result["lsa_by_type"]
        device_data["ospf_lsa_by_area"] = result["lsa_by_area"]
        device_data["ospf_flooding_detected"] = result["flooding_detected"]
        device_data["ospf_database_health"] = result["status"]
        
        print(f"\n--- OSPF Database for {device_name} ---")
        print(f"  Total LSAs: {result['total_lsas']}")
        
        if result["lsa_by_type"]:
            print(f"  LSA Types:")
            for lsa_type, count in result["lsa_by_type"].items():
                print(f"    - {lsa_type}: {count}")
        
        if result["lsa_by_area"]:
            print(f"  LSAs by Area:")
            for area, count in result["lsa_by_area"].items():
                print(f"    - Area {area}: {count} LSAs")
        
        if result["flooding_detected"]:
            print(f"  [⚠] WARNING: Potential LSA flooding detected (>{OSPF_LSA_FLOOD_THRESHOLD} LSAs)")
            print(f"    → {result['details']['recommendation']}")
        else:
            print(f"  Status: {result['status']}")
    
    # OSPF Interface Status (NEW - Optional)
    if "show ip ospf interface brief" in outputs:
        print(f"  Running: show ip ospf interface brief")
        output = outputs["show ip ospf interface brief"]
        result = OSPFAnalyzer.analyze_interfaces(output["structured"], output["raw"])
        device_data["ospf_interface_count"] = result["total_interfaces"]
        device_data["ospf_interface_issues"] = result["issues"]
        
        if result["issues"]:
            print(f"\n--- OSPF Interface Issues for {device_name} ---")
            for issue in result["issues"]:
                print(f"  ⚠ {issue['interface']}: {issue['issue']} (Area {issue['area']})")
    
    # Step 3: Calculate overall health score
    overall_health = HealthScorer.calculate_overall_health(component_statuses)
    
    device_data["overall_health"] = overall_health
    print(f"\n--- Overall Health for {device_name}: {overall_health} ---")
    
    return {device_name: device_data}


def generate_ai_explanations(device_summaries):
    """Generate explanations for all devices using Gemini (with manual fallback)"""
    print("\n" + "="*60)
    print("GENERATING HEALTH EXPLANATIONS")
    print("="*60)
    
    explainer = None
    explainer_type = "Manual (Rule-Based)"
    use_manual = False
    
    # Try Gemini
    if USE_GEMINI:
        try:
            from ai_explainer import GeminiExplainer
            explainer = GeminiExplainer(model=GEMINI_MODEL)
            explainer_type = f"Google Gemini ({GEMINI_MODEL})"
        except Exception as e:
            print(f"✗ Gemini initialization failed: {e}")
            print("  → Falling back to manual rule-based explainer...")
            use_manual = True
    else:
        print("Gemini disabled in configuration")
        use_manual = True
    
    # Use manual explainer if Gemini failed
    if use_manual or explainer is None:
        from utils.manual_explainer import ManualExplainer
        explainer = ManualExplainer()
        explainer_type = "Manual (Rule-Based)"
    
    print(f"✓ Using {explainer_type}\n")
    
    # Generate per-device explanations
    for device_name, device_data in device_summaries.items():
        if device_name == 'network_analysis':
            continue
            
        if not isinstance(device_data, dict):
            continue
            
        if not device_data.get('reachable', False):
            print(f"[{device_name}] Skipped - device unreachable")
            continue
        
        print(f"[{device_name}] Generating explanation...")
        
        try:
            explanation = explainer.explain_device_health(device_name, device_data)
            device_data['ai_explanation'] = explanation
            device_data['explanation_type'] = explainer_type
            
            print(f"\n{'='*60}")
            print(f"EXPLANATION FOR {device_name} ({explainer_type})")
            print(f"{'='*60}")
            print(explanation)
            print("="*60)
            
        except Exception as e:
            print(f"✗ Failed to generate explanation for {device_name}: {e}")
            
            # Try manual explainer as fallback for this device
            try:
                from utils.manual_explainer import ManualExplainer
                manual = ManualExplainer()
                explanation = manual.explain_device_health(device_name, device_data)
                device_data['ai_explanation'] = explanation
                device_data['explanation_type'] = "Manual (Fallback)"
                
                print(f"\n{'='*60}")
                print(f"EXPLANATION FOR {device_name} (Manual Fallback)")
                print(f"{'='*60}")
                print(explanation)
                print("="*60)
            except Exception as fallback_error:
                device_data['ai_explanation'] = f"[Error: {str(e)}]"
                print(f"✗ Fallback also failed: {fallback_error}")
    
    # Generate network-wide analysis
    print("\n" + "="*60)
    print(f"NETWORK-WIDE ANALYSIS ({explainer_type})")
    print("="*60)
    
    try:
        network_analysis = explainer.explain_network_health(device_summaries)
        
        print(network_analysis)
        print("="*60)
        
        device_summaries['network_analysis'] = {
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
            'analysis': network_analysis,
            'explainer_type': explainer_type
        }
        
    except Exception as e:
        print(f"✗ Failed to generate network analysis: {e}")
        
        # Try manual fallback
        try:
            from utils.manual_explainer import ManualExplainer
            manual = ManualExplainer()
            network_analysis = manual.explain_network_health(device_summaries)
            
            print(network_analysis)
            print("="*60)
            
            device_summaries['network_analysis'] = {
                'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'analysis': network_analysis,
                'explainer_type': "Manual (Fallback)"
            }
        except Exception as fallback_error:
            print(f"✗ Fallback also failed: {fallback_error}")
    
    return device_summaries


def main():
    """Main orchestration"""
    global device_summary
    
    print("="*60)
    print("CISCO ROUTING HEALTH ANALYZER WITH AI EXPLANATIONS")
    print("="*60)
    
    print("\nConnecting to CML server...")
    client = ClientLibrary(CML_SERVER, USERNAME, PASSWORD, ssl_verify=False)
    labs = client.find_labs_by_title(LAB_NAME)
    
    if not labs:
        print(f"[X] Lab '{LAB_NAME}' not found")
        return
    
    lab = labs[0]
    testbed_yaml = lab.get_pyats_testbed()
    testbed = yaml.safe_load(testbed_yaml)
    proxy_ip = testbed["devices"]["terminal_server"]["connections"]["cli"]["ip"]
    
    # Check terminal server reachability
    print(f"\nChecking terminal server reachability at {proxy_ip}...")
    if not CiscoIOSCollector.check_reachability(proxy_ip, port=22, timeout=5):
        print(f"[X] Terminal server not reachable. Exiting.")
        return
    print(f"[✓] Terminal server is reachable.")
    
    # Create collector
    collector = CiscoIOSCollector(proxy_ip, USERNAME, PASSWORD)
    
    # Process devices in parallel
    print("\n" + "="*60)
    print("COLLECTING DEVICE HEALTH DATA")
    print("="*60)
    
    start_time = time.time()
    devices_to_process = {k: v for k, v in testbed["devices"].items() 
                         if k != "terminal_server"}
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_device = {
            executor.submit(process_device, device_name, device_info, collector): device_name
            for device_name, device_info in devices_to_process.items()
        }
        
        for future in as_completed(future_to_device):
            device_name = future_to_device[future]
            try:
                result = future.result()
                with summary_lock:
                    device_summary.update(result)
            except Exception as exc:
                print(f"[X] {device_name} exception: {exc}")
                with summary_lock:
                    device_summary[device_name] = {
                        "reachable": False,
                        "overall_health": "ERROR",
                        "error": str(exc)
                    }
    
    collection_time = time.time() - start_time
    
    # Generate AI explanations if enabled
    ai_time = 0
    if ENABLE_AI:
        ai_start_time = time.time()
        device_summary = generate_ai_explanations(device_summary)
        ai_time = time.time() - ai_start_time
    else:
        print("\n[i] AI explanations disabled (set ENABLE_AI_EXPLANATIONS=true to enable)")
    
    # Save JSON summaries
    with open("device_health_summary.json", "w") as f:
        json.dump(device_summary, f, indent=4)
    
    if ENABLE_AI:
        with open("device_health_summary_with_ai.json", "w") as f:
            json.dump(device_summary, f, indent=4)
    
    # Print OSPF Summary
    print("\n" + "="*60)
    print("OSPF HEALTH SUMMARY")
    print("="*60)
    
    ospf_configured_devices = 0
    ospf_healthy_devices = 0
    ospf_unhealthy_devices = 0
    
    for device, status in device_summary.items():
        if device == 'network_analysis' or not isinstance(status, dict):
            continue
        
        ospf_health = status.get("ospf_health", "NOT_CONFIGURED")
        
        if ospf_health != "NOT_CONFIGURED":
            ospf_configured_devices += 1
            
            total_neighbors = status.get("ospf_total_neighbors", 0)
            full_neighbors = status.get("ospf_full_neighbors", 0)
            down_neighbors = status.get("ospf_down_neighbors", [])
            areas = status.get("ospf_neighbors_by_area", {})
            lsa_count = status.get("ospf_lsa_total", 0)
            flooding = status.get("ospf_flooding_detected", False)
            
            print(f"\n{device}:")
            print(f"  Status: {ospf_health}")
            print(f"  Neighbors: {full_neighbors}/{total_neighbors} FULL")
            
            if areas:
                print(f"  Areas:")
                for area, stats in areas.items():
                    print(f"    - Area {area}: {stats['full']}/{stats['total']}")
            
            print(f"  LSAs: {lsa_count}")
            
            if ospf_health == "OK":
                ospf_healthy_devices += 1
            else:
                ospf_unhealthy_devices += 1
            
            if down_neighbors:
                print(f"  ✗ Down Neighbors:")
                for neighbor in down_neighbors[:3]:
                    print(f"    - {neighbor['neighbor_id']} ({neighbor['interface']}): {neighbor['state']}")
            
            if flooding:
                print(f"  ⚠ LSA flooding warning")
    
    if ospf_configured_devices == 0:
        print("\n[i] No devices with OSPF configuration found")
    else:
        print(f"\n{'='*60}")
        print(f"Total OSPF Devices: {ospf_configured_devices}")
        print(f"Healthy: {ospf_healthy_devices}")
        print(f"Unhealthy: {ospf_unhealthy_devices}")
    
    # Print BGP Summary
    print("\n" + "="*60)
    print("BGP HEALTH SUMMARY")
    print("="*60)
    
    bgp_configured_devices = sum(1 for s in device_summary.values() 
                                 if isinstance(s, dict) and 
                                 s.get("bgp_health") not in ["NOT_CONFIGURED", None])
    
    if bgp_configured_devices == 0:
        print("\n[i] No devices with BGP configuration found")
    else:
        for device, status in device_summary.items():
            if device == 'network_analysis' or not isinstance(status, dict):
                continue
            
            bgp_health = status.get("bgp_health")
            if bgp_health and bgp_health != "NOT_CONFIGURED":
                total = status.get("bgp_total_neighbors", 0)
                established = status.get("bgp_established_neighbors", 0)
                print(f"\n{device}:")
                print(f"  Status: {bgp_health}")
                print(f"  Neighbors: {established}/{total} Established")
    
    # Print final summary
    print("\n" + "="*60)
    print("OVERALL DEVICE SUMMARY")
    print("="*60)
    
    healthy_count = sum(1 for s in device_summary.values() 
                       if isinstance(s, dict) and s.get("overall_health") == "HEALTHY")
    device_count = len([d for d in device_summary if d != 'network_analysis'])
    
    for device, status in device_summary.items():
        if device == "network_analysis":
            continue
        
        if not isinstance(status, dict):
            continue
            
        reachable = "✓" if status.get("reachable") else "✗"
        health = status.get("overall_health", "Unknown")
        cpu_health = status.get("cpu_health", "N/A")
        mem_health = status.get("memory_health", "N/A")
        bgp_status = status.get("bgp_health", "N/A")
        ospf_status = status.get("ospf_health", "N/A")
        ai_available = "✓" if status.get("ai_explanation") else "✗"
        
        print(f"{device:12} {reachable} Reach  Health: {health:10} "
              f"CPU: {cpu_health:8} Mem: {mem_health:8} "
              f"BGP: {bgp_status:12} OSPF: {ospf_status:12} AI: {ai_available}")
    
    print("\n" + "="*60)
    print(f"Healthy Devices: {healthy_count}/{device_count}")
    print(f"Data collection time: {collection_time:.2f} seconds")
    if ENABLE_AI:
        print(f"AI analysis time: {ai_time:.2f} seconds")
    print(f"Total execution time: {collection_time + ai_time:.2f} seconds")
    print("="*60)
    
    if ENABLE_AI:
        print("\n✓ Enhanced summary with AI explanations saved to device_health_summary_with_ai.json")
    print("✓ Standard summary saved to device_health_summary.json")


if __name__ == "__main__":
    main()