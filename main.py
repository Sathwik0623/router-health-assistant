import os
import json
import time
import yaml
from dotenv import load_dotenv
from virl2_client import ClientLibrary
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from collectors.cisco_ios import CiscoIOSCollector
from analyzers import (InterfaceAnalyzer, CPUAnalyzer, MemoryAnalyzer,
                      RoutingAnalyzer, BGPAnalyzer)
from scoring.health_score import HealthScorer
from config.commands import CISCO_IOS_COMMANDS

load_dotenv()

# Configuration
CML_SERVER = os.getenv("ROUTING_HEALTH_CML_SERVER")
USERNAME = os.getenv("ROUTING_HEALTH_CML_USERNAME")
PASSWORD = os.getenv("ROUTING_HEALTH_CML_PASSWORD")
LAB_NAME = os.getenv("ROUTING_HEALTH_LAB_NAME")

device_summary = {}
summary_lock = threading.Lock()


def process_device(device_name, device_info, collector):
   
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
    
    # Step 2: Analyze each component
    
    # Interface Health
    if "show ip interface brief" in outputs:
        print(f"  Running: show ip interface brief")
        output = outputs["show ip interface brief"]
        result = InterfaceAnalyzer.analyze(output["structured"], output["raw"])
        device_data["interface_health"] = result["status"]
        device_data["interfaces_down"] = result["interfaces_down"]
        
        if result["status"] == "Good":
            print(f"\n--- Interface Status for {device_name} ---")
            print("  [✓] All assigned-IP interfaces are UP.")
        else:
            print(f"\n--- Interface Status for {device_name} ---")
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
        
        print(f"\n--- CPU Health for {device_name} ---")
        print(f"  Status: {result['status']} ({result['cpu_percent']}%)")
    
    # Memory Health
    if "show process memory" in outputs:
        print(f"  Running: show process memory")
        output = outputs["show process memory"]
        result = MemoryAnalyzer.analyze(output["structured"], output["raw"])
        device_data["memory_health"] = result["status"]
        device_data["memory_used_percent"] = result["memory_used_percent"]
        device_data["memory_total_mb"] = result["memory_total_mb"]
        device_data["memory_used_mb"] = result["memory_used_mb"]
        device_data["memory_free_mb"] = result["memory_free_mb"]
        
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
    
    # Step 3: Calculate overall health score
    overall_health = HealthScorer.calculate_overall_health(
        device_data.get("interface_health", "Unknown"),
        device_data.get("cpu_health", "Unknown"),
        device_data.get("memory_health", "Unknown"),
        device_data.get("bgp_health", "NOT_CONFIGURED")
    )
    
    device_data["overall_health"] = overall_health
    print(f"\n--- Overall Health for {device_name}: {overall_health} ---")
    
    return {device_name: device_data}


def main():
    
    print("Connecting to CML server...")
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
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    # Save JSON summary
    with open("device_health_summary.json", "w") as f:
        json.dump(device_summary, f, indent=4)
    
    # Print BGP summary
    print("\n" + "="*60)
    print("BGP HEALTH SUMMARY")
    print("="*60)
    
    bgp_configured = sum(1 for s in device_summary.values() 
                        if s.get("bgp_health") not in ["NOT_CONFIGURED", None])
    
    if bgp_configured == 0:
        print("\n[i] No devices with BGP configuration found")
    else:
        for device, status in device_summary.items():
            bgp_health = status.get("bgp_health")
            if bgp_health and bgp_health != "NOT_CONFIGURED":
                total = status.get("bgp_total_neighbors", 0)
                established = status.get("bgp_established_neighbors", 0)
                print(f"\n{device}:")
                print(f"  Status: {bgp_health}")
                print(f"  Neighbors: {established}/{total} Established")
                
                if status.get("bgp_down_neighbors"):
                    print(f"  ✗ Down Neighbors:")
                    for neighbor in status["bgp_down_neighbors"]:
                        print(f"    - {neighbor['neighbor']} (AS {neighbor['as']}) - "
                              f"State: {neighbor['state']}")
                
                if status.get("bgp_high_flap_neighbors"):
                    print(f"  ⚠️  High Flap Neighbors:")
                    for neighbor in status["bgp_high_flap_neighbors"]:
                        print(f"    - {neighbor['neighbor']} - Flaps: {neighbor['flaps']}")
    
    # Print overall summary
    print("\n" + "="*60)
    print("OVERALL DEVICE SUMMARY")
    print("="*60)
    
    healthy_count = sum(1 for s in device_summary.values() 
                       if s.get("overall_health") == "HEALTHY")
    
    for device, status in device_summary.items():
        reachable = "✓ Reachable" if status.get("reachable") else "✗ Unreachable"
        health = status.get("overall_health", "Unknown")
        bgp_status = status.get("bgp_health", "N/A")
        print(f"{device:20} {reachable:20} Health: {health:12} BGP: {bgp_status}")
    
    print("\n" + "="*60)
    print(f"Healthy Devices: {healthy_count}/{len(device_summary)}")
    print(f"Total execution time: {elapsed_time:.2f} seconds")
    print("="*60)
    print("\nSummary saved to device_health_summary.json")


if __name__ == "__main__":
    main()