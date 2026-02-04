import paramiko
import time
import yaml
import os
from virl2_client import ClientLibrary
from dotenv import load_dotenv
from ntc_templates.parse import parse_output
import json
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re

load_dotenv()

# ------------------------
# Configuration
# ------------------------
CML_SERVER = os.getenv("ROUTING_HEALTH_CML_SERVER")
USERNAME = os.getenv("ROUTING_HEALTH_CML_USERNAME")
PASSWORD = os.getenv("ROUTING_HEALTH_CML_PASSWORD")
LAB_NAME = os.getenv("ROUTING_HEALTH_LAB_NAME")

COMMANDS = [
    "show ip interface brief", 
    "show ip route", 
    "show processes cpu", 
    "show process memory",
    "show ip bgp summary",
    "show ip bgp neighbors"
]

# Device summary for final JSON report (thread-safe)
device_summary = {}
summary_lock = threading.Lock()

# ------------------------
# Helper Functions
# ------------------------

def check_reachability(host, port=22, timeout=5):
    try:
        sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result=sock.connect_ex((host, port))
        sock.close()
        return result==0
    except Exception as e:
        return False


def wait_for_prompt(channel, timeout=10):
    start_time = time.time()
    buffer = ""
    while time.time() - start_time < timeout:
        if channel.recv_ready():
            chunk = channel.recv(65535).decode("utf-8", errors="ignore")
            buffer += chunk
            if ">" in buffer or "#" in buffer:
                return buffer
        time.sleep(0.3)  # Reduced from 0.5
        channel.send("\n")
    return buffer

def robust_read(channel, timeout=3):  # Reduced default timeout from 5 to 3
    time.sleep(1)  # Reduced from 2 to 1
    output = ""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if channel.recv_ready():
            while channel.recv_ready():
                output += channel.recv(65535).decode("utf-8", errors="ignore")
                time.sleep(0.1)  # Reduced from 0.2
            return output
        time.sleep(0.3)  # Reduced from 0.5
    return output


def parse_bgp_summary_manual(raw_output):
    """
    Manual parser for BGP summary output
    Extracts neighbor information from raw text
    """
    bgp_neighbors = []
    
    lines = raw_output.splitlines()
    
    for i, line in enumerate(lines):
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


def parse_bgp_neighbors_manual(raw_output):
    """
    Manual parser for detailed BGP neighbor information
    Extracts flap statistics and detailed neighbor info
    """
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
        
        if current_neighbor and "remote AS" in line_stripped:
            match = re.search(r'remote AS (\d+)', line_stripped)
            if match:
                current_neighbor['remote_as'] = match.group(1)
        
        if current_neighbor and "BGP state =" in line_stripped:
            match = re.search(r'BGP state = (\w+)', line_stripped)
            if match:
                current_neighbor['state'] = match.group(1)
            
            match = re.search(r'up for (\S+)', line_stripped)
            if match:
                current_neighbor['uptime'] = match.group(1)
        
        if current_neighbor and "Connections established" in line_stripped:
            match = re.search(r'Connections established (\d+); dropped (\d+)', line_stripped)
            if match:
                established = int(match.group(1))
                dropped = int(match.group(2))
                current_neighbor['route_flaps'] = dropped
        
        if current_neighbor and "Last reset" in line_stripped:
            current_neighbor['last_reset'] = line_stripped
        
        if current_neighbor and "prefixes" in line_stripped.lower() and "accepted" in line_stripped.lower():
            match = re.search(r'(\d+)\s+prefixes', line_stripped)
            if match:
                current_neighbor['prefixes_received'] = int(match.group(1))
    
    if current_neighbor:
        neighbor_details.append(current_neighbor)
    
    return neighbor_details


def process_parsed_data(command, structured_data, device_name, raw_output, local_summary):
    if device_name not in local_summary:
        local_summary[device_name] = {}

    # Interface Health
    if command == "show ip interface brief":
        print(f"\n--- Interface Status for {device_name} ---")
        down_interfaces = []

        if isinstance(structured_data, list):
            for intf in structured_data:
                intf_name = intf.get("interface", "unknown")
                ip_addr = (intf.get("ipaddr") or "unassigned").lower()
                status = (intf.get("status") or "").lower()
                protocol = (intf.get("protocol") or "").lower()

                if ip_addr != "unassigned":
                    if status != "up" or protocol != "up":
                        down_interfaces.append(
                            f"{intf_name} ({status}/{protocol})"
                        )
        else:
            print("  [!] Warning: TextFSM template not found or output could not be parsed.")

        if down_interfaces:
            print(f"  [!] DOWN: {', '.join(down_interfaces)}")
            local_summary[device_name]["interfaces_down"] = down_interfaces
            local_summary[device_name]["interface_health"] = "Warning"
        else:
            print("  [✓] All assigned-IP interfaces are UP.")
            local_summary[device_name]["interfaces_down"] = []
            local_summary[device_name]["interface_health"] = "Good"

    # Routing Table
    elif command == "show ip route":
        print(f"\n--- Routing Table Summary for {device_name} ---")
        if isinstance(structured_data, list):
            print(f"  Total routes found: {len(structured_data)}")
            for route in structured_data[:3]:
                via = route.get("nexthop_ip") or "Direct"
                protocol = route.get("protocol") or "?"
                network = route.get("network") or "?"
                print(f"  -> {protocol} {network} via {via}")
            
            local_summary[device_name]["total_routes"] = len(structured_data)
        else:
            print("  [!] Warning: TextFSM template not found or output could not be parsed.")

    # CPU Health
    elif command == "show processes cpu":
        print(f"\n--- CPU Health for {device_name} ---")
        cpu_percent = 0
        cpu_status = "Unknown"

        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                cpu_str = structured_data[0].get("cpu_utilization", "0%")
                cpu_percent = int(cpu_str.strip("%"))
                cpu_status = "OK" if cpu_percent < 70 else "CRITICAL"
            else:
                raise ValueError("No structured data from TextFSM")
        except Exception:
            for line in raw_output.splitlines():
                line = line.strip()
                if "CPU utilization" in line:
                    try:
                        cpu_val = line.split(":")[1].split("%")[0].strip()
                        if "/" in cpu_val:
                            cpu_val = cpu_val.split("/")[0].strip()
                        cpu_percent = int(cpu_val)
                        cpu_status = "OK" if cpu_percent < 70 else "CRITICAL"
                        break
                    except Exception:
                        cpu_percent = 0
                        cpu_status = "Unknown"

        print(f"  Status: {cpu_status} ({cpu_percent}%)")
        local_summary[device_name]["cpu_percent"] = cpu_percent
        local_summary[device_name]["cpu_health"] = cpu_status

    # Memory Health - Enhanced parsing
    elif command == "show process memory":
        print(f"\n--- Memory Health for {device_name} ---")
        memory_used_percent=0
        memory_status="Unknown"
        total_memory=0
        used_memory=0
        free_memory=0

        try:
            if isinstance(structured_data,list) and len(structured_data)>0:
                for entry in structured_data:
                    if "processor" in entry.get("pool","").lower():
                        total_memory=int(entry.get("total",0))
                        used_memory=int(entry.get("used",0))
                        free_memory=int(entry.get("free",0))
                        if total_memory>0:
                            memory_used_percent=int((used_memory/total_memory)*100)
                            memory_status="OK" if memory_used_percent<80 else "CRITICAL"
                        break
            else:
                raise ValueError("No Structured data from TextFSM")
        
        except Exception:
            # Enhanced manual parsing with multiple patterns
            for line in raw_output.splitlines():
                line=line.strip()
                
                # Pattern 1: "Processor Pool Total:  1859096064 Used:   340603232 Free:  1518492832"
                if "Processor" in line and "Total:" in line:
                    try:
                        parts= line.split()
                        for i,part in enumerate(parts):
                            if part=="Total:":
                                total_memory=int(parts[i+1])
                            elif part=="Used:":
                                used_memory=int(parts[i+1])
                            elif part=="Free:":
                                free_memory=int(parts[i+1])
                        
                        if total_memory>0:
                            memory_used_percent=int((used_memory/total_memory)*100)
                            memory_status="OK" if memory_used_percent<80 else "CRITICAL"
                        break
                    except Exception as e:
                        pass
                
                # Pattern 2: Look for lines like "Processor    1859096064   340603232  1518492832"
                if "Processor" in line and not "Pool" in line:
                    try:
                        parts = line.split()
                        if len(parts) >= 4:
                            total_memory = int(parts[1])
                            used_memory = int(parts[2])
                            free_memory = int(parts[3])
                            
                            if total_memory > 0:
                                memory_used_percent = int((used_memory / total_memory) * 100)
                                memory_status = "OK" if memory_used_percent < 80 else "CRITICAL"
                            break
                    except Exception as e:
                        pass

        total_mb=total_memory//(1024*1024) if total_memory >0 else 0
        used_mb=used_memory//(1024*1024) if used_memory>0 else 0
        free_mb=free_memory//(1024*1024) if free_memory>0 else 0

        print(f"  Total: {total_mb} MB, Used: {used_mb} MB ({memory_used_percent}%), Free: {free_mb} MB")
        print(f"  Status: {memory_status}")

        local_summary[device_name]["memory_total_mb"]=total_mb
        local_summary[device_name]["memory_used_mb"]=used_mb
        local_summary[device_name]["memory_free_mb"]=free_mb
        local_summary[device_name]["memory_used_percent"]=memory_used_percent
        local_summary[device_name]["memory_health"]=memory_status

    # BGP Summary Health
    elif command == "show ip bgp summary":
        print(f"\n--- BGP Summary for {device_name} ---")
        
        bgp_neighbors = []
        bgp_status = "Unknown"
        total_neighbors = 0
        established_neighbors = 0
        down_neighbors = []
        
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                bgp_neighbors = structured_data
            else:
                bgp_neighbors = parse_bgp_summary_manual(raw_output)
        except Exception:
            bgp_neighbors = parse_bgp_summary_manual(raw_output)
        
        if bgp_neighbors:
            total_neighbors = len(bgp_neighbors)
            
            for neighbor in bgp_neighbors:
                neighbor_ip = neighbor.get('neighbor', 'Unknown')
                state = neighbor.get('state', neighbor.get('state_pfxrcd', 'Unknown'))
                
                if state == 'Established' or str(state).isdigit():
                    established_neighbors += 1
                    prefixes = neighbor.get('prefixes_received', state if str(state).isdigit() else 0)
                    print(f"  ✓ {neighbor_ip} - AS {neighbor.get('as', '?')} - Established - Prefixes: {prefixes}")
                else:
                    down_neighbors.append({
                        'neighbor': neighbor_ip,
                        'as': neighbor.get('as', 'Unknown'),
                        'state': state
                    })
                    print(f"  ✗ {neighbor_ip} - AS {neighbor.get('as', '?')} - {state}")
            
            if established_neighbors == total_neighbors:
                bgp_status = "OK"
                print(f"\n  [✓] All BGP neighbors are Established ({established_neighbors}/{total_neighbors})")
            else:
                bgp_status = "CRITICAL"
                print(f"\n  [!] BGP neighbors down: {len(down_neighbors)}/{total_neighbors}")
            
            local_summary[device_name]["bgp_total_neighbors"] = total_neighbors
            local_summary[device_name]["bgp_established_neighbors"] = established_neighbors
            local_summary[device_name]["bgp_down_neighbors"] = down_neighbors
            local_summary[device_name]["bgp_health"] = bgp_status
            local_summary[device_name]["bgp_neighbors_summary"] = bgp_neighbors
        else:
            print("  [i] BGP not configured or no neighbors found")
            local_summary[device_name]["bgp_health"] = "NOT_CONFIGURED"

    # BGP Neighbors Detailed Health
    elif command == "show ip bgp neighbors":
        print(f"\n--- BGP Neighbors Detailed Analysis for {device_name} ---")
        
        neighbor_details = []
        high_flap_neighbors = []
        
        try:
            if isinstance(structured_data, list) and len(structured_data) > 0:
                neighbor_details = structured_data
            else:
                neighbor_details = parse_bgp_neighbors_manual(raw_output)
        except Exception:
            neighbor_details = parse_bgp_neighbors_manual(raw_output)
        
        if neighbor_details:
            for neighbor in neighbor_details:
                neighbor_ip = neighbor.get('neighbor', 'Unknown')
                state = neighbor.get('state', 'Unknown')
                flaps = neighbor.get('route_flaps', 0)
                prefixes = neighbor.get('prefixes_received', 0)
                last_reset = neighbor.get('last_reset', 'N/A')
                
                print(f"\n  Neighbor: {neighbor_ip}")
                print(f"    State: {state}")
                print(f"    Remote AS: {neighbor.get('remote_as', 'Unknown')}")
                print(f"    Uptime: {neighbor.get('uptime', 'N/A')}")
                print(f"    Prefixes Received: {prefixes}")
                print(f"    Connection Flaps: {flaps}")
                
                if flaps > 5:
                    high_flap_neighbors.append({
                        'neighbor': neighbor_ip,
                        'flaps': flaps,
                        'last_reset': last_reset
                    })
                    print(f"    ⚠️  HIGH FLAP COUNT DETECTED!")
                
                if last_reset and last_reset != 'N/A':
                    print(f"    Last Reset: {last_reset}")
            
            local_summary[device_name]["bgp_neighbor_details"] = neighbor_details
            local_summary[device_name]["bgp_high_flap_neighbors"] = high_flap_neighbors
            
            if high_flap_neighbors:
                print(f"\n  [!] {len(high_flap_neighbors)} neighbor(s) with high flap count detected")
        else:
            print("  [i] No detailed BGP neighbor information found")


def process_single_device(device_name, device_info, proxy_ip, username, password):
    """
    Process a single device - this function will run in parallel for each device
    """
    local_summary = {device_name: {"reachable": False}}
    
    proxy_conn = next(
        (c for c in device_info.get("connections", {}).values() if c.get("proxy") == "terminal_server"),
        None
    )
    
    if not proxy_conn:
        print(f"[X] No proxy connection for {device_name}. Skipping.")
        local_summary[device_name] = {
            "reachable": False,
            "overall_health": "UNREACHABLE",
            "error": "No proxy connection configured"
        }
        return local_summary

    print(f"\n>>> Connecting to {device_name}...")

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(proxy_ip, username=username, password=password, timeout=10)
        
        channel = ssh.invoke_shell()
        channel.send(proxy_conn.get("command") + "\n")

        console_output = wait_for_prompt(channel, timeout=15)
        if ">" not in console_output and "#" not in console_output:
            print(f"  [X] Could not find prompt for {device_name}. Device may be unreachable.")
            local_summary[device_name]["overall_health"] = "UNREACHABLE"
            local_summary[device_name]["error"] = "No prompt detected"
            channel.close()
            ssh.close()
            return local_summary

        local_summary[device_name]["reachable"] = True
        print(f"  [✓] Device {device_name} is reachable.")

        channel.send("terminal length 0\n")
        time.sleep(0.5)  # Reduced from 1
        channel.recv(65535)

        for cmd in COMMANDS:
            print(f"  Running: {cmd}")
            channel.send(cmd + "\n")
            
            # Adaptive timeout based on command
            if "bgp" in cmd.lower():
                raw_output = robust_read(channel, timeout=4)
            else:
                raw_output = robust_read(channel, timeout=3)
            
            if raw_output:
                structured = None
                try:
                    structured = parse_output(platform="cisco_ios", command=cmd, data=raw_output)
                except Exception as e:
                    if cmd not in ["show processes cpu", "show process memory", "show ip bgp summary", "show ip bgp neighbors"]:
                        print(f"  [X] Parse Error: {e}")
                
                process_parsed_data(cmd, structured, device_name, raw_output, local_summary)
            else:
                print(f"  [X] No output received for {cmd}")

        # Calculate overall health
        iface_health = local_summary[device_name].get("interface_health", "Unknown")
        cpu_health = local_summary[device_name].get("cpu_health", "Unknown")
        memory_health = local_summary[device_name].get("memory_health", "Unknown")
        bgp_health = local_summary[device_name].get("bgp_health", "NOT_CONFIGURED")
        
        if bgp_health == "NOT_CONFIGURED":
            if iface_health == "Good" and cpu_health == "OK" and memory_health == "OK":
                overall = "HEALTHY"
            else:
                overall = "UNHEALTHY"
        else:
            if iface_health == "Good" and cpu_health == "OK" and memory_health == "OK" and bgp_health == "OK":
                overall = "HEALTHY"
            else:
                overall = "UNHEALTHY"
        
        local_summary[device_name]["overall_health"] = overall
        print(f"\n--- Overall Health for {device_name}: {overall} ---")

        channel.send("exit\n")
        channel.close()
        ssh.close()

    except Exception as e:
        print(f"  [X] Error connecting to {device_name}: {e}")
        local_summary[device_name]["overall_health"] = "UNREACHABLE"
        local_summary[device_name]["error"] = str(e)

    return local_summary


# ------------------------
# Connect to CML and Load Lab Testbed
# ------------------------
print("Connecting to CML server...")
client = ClientLibrary(CML_SERVER, USERNAME, PASSWORD, ssl_verify=False)
labs = client.find_labs_by_title(LAB_NAME)
if not labs:
    print(f"[X] Lab '{LAB_NAME}' not found")
    exit(1)

lab = labs[0]
testbed_yaml = lab.get_pyats_testbed()
testbed = yaml.safe_load(testbed_yaml)

proxy_ip = testbed["devices"]["terminal_server"]["connections"]["cli"]["ip"]

print(f"\nChecking terminal server reachability at {proxy_ip}...")
if not check_reachability(proxy_ip, port=22, timeout=5):
    print(f"[X] Terminal server at {proxy_ip} is not reachable. Exiting.")
    exit(1)
else:
    print(f"[✓] Terminal server is reachable.")

# ------------------------
# Process Devices in Parallel
# ------------------------
start_time = time.time()

devices_to_process = {k: v for k, v in testbed["devices"].items() if k != "terminal_server"}

with ThreadPoolExecutor(max_workers=5) as executor:
    future_to_device = {
        executor.submit(process_single_device, device_name, device_info, proxy_ip, USERNAME, PASSWORD): device_name
        for device_name, device_info in devices_to_process.items()
    }
    
    for future in as_completed(future_to_device):
        device_name = future_to_device[future]
        try:
            result = future.result()
            with summary_lock:
                device_summary.update(result)
        except Exception as exc:
            print(f"[X] {device_name} generated an exception: {exc}")
            with summary_lock:
                device_summary[device_name] = {
                    "reachable": False,
                    "overall_health": "ERROR",
                    "error": str(exc)
                }

end_time = time.time()
elapsed_time = end_time - start_time

# ------------------------
# Save Summary JSON
# ------------------------
with open("device_health_summary.json", "w") as f:
    json.dump(device_summary, f, indent=4)

# ------------------------
# Generate BGP Health Report
# ------------------------
print("\n" + "="*60)
print("BGP HEALTH SUMMARY")
print("="*60)

bgp_configured_devices = 0
bgp_healthy_devices = 0
bgp_unhealthy_devices = 0

for device, status in device_summary.items():
    bgp_health = status.get("bgp_health", "NOT_CONFIGURED")
    
    if bgp_health != "NOT_CONFIGURED":
        bgp_configured_devices += 1
        
        total_neighbors = status.get("bgp_total_neighbors", 0)
        established = status.get("bgp_established_neighbors", 0)
        down_neighbors = status.get("bgp_down_neighbors", [])
        high_flap = status.get("bgp_high_flap_neighbors", [])
        
        print(f"\n{device}:")
        print(f"  Status: {bgp_health}")
        print(f"  Neighbors: {established}/{total_neighbors} Established")
        
        if bgp_health == "OK":
            bgp_healthy_devices += 1
            print(f"  ✓ All BGP neighbors healthy")
        else:
            bgp_unhealthy_devices += 1
            
        if down_neighbors:
            print(f"  ✗ Down Neighbors:")
            for neighbor in down_neighbors:
                print(f"    - {neighbor['neighbor']} (AS {neighbor['as']}) - State: {neighbor['state']}")
        
        if high_flap:
            print(f"  ⚠️  High Flap Neighbors:")
            for neighbor in high_flap:
                print(f"    - {neighbor['neighbor']} - Flaps: {neighbor['flaps']}")

if bgp_configured_devices == 0:
    print("\n[i] No devices with BGP configuration found")
else:
    print(f"\n{'='*60}")
    print(f"Total BGP Devices: {bgp_configured_devices}")
    print(f"Healthy: {bgp_healthy_devices}")
    print(f"Unhealthy: {bgp_unhealthy_devices}")

# ------------------------
# Overall Summary
# ------------------------
print("\n" + "="*60)
print("OVERALL DEVICE SUMMARY")
print("="*60)

for device, status in device_summary.items():
    reachable = "✓ Reachable" if status.get("reachable") else "✗ Unreachable"
    health = status.get("overall_health", "Unknown")
    bgp_status = status.get("bgp_health", "N/A")
    
    print(f"{device:20} {reachable:20} Health: {health:12} BGP: {bgp_status}")

print("\n" + "="*60)
print(f"Total execution time: {elapsed_time:.2f} seconds")
print("="*60)
print("\nAll devices processed. Summary saved to device_health_summary.json")