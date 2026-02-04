"""Cisco IOS device collector - handles SSH connections and command execution"""
import paramiko
import time
import socket
from ntc_templates.parse import parse_output


class CiscoIOSCollector:
    """Collects raw command output from Cisco IOS devices via SSH"""
    
    def __init__(self, proxy_ip, username, password):
        self.proxy_ip = proxy_ip
        self.username = username
        self.password = password
    
    @staticmethod
    def check_reachability(host, port=22, timeout=5):
        """Check if device is reachable via TCP"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def _wait_for_prompt(self, channel, timeout=10):
        """Wait for CLI prompt"""
        start_time = time.time()
        buffer = ""
        while time.time() - start_time < timeout:
            if channel.recv_ready():
                chunk = channel.recv(65535).decode("utf-8", errors="ignore")
                buffer += chunk
                if ">" in buffer or "#" in buffer:
                    return buffer
            time.sleep(0.3)
            channel.send("\n")
        return buffer
    
    def _robust_read(self, channel, timeout=3):
        """Read command output with timeout"""
        time.sleep(1)
        output = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if channel.recv_ready():
                while channel.recv_ready():
                    output += channel.recv(65535).decode("utf-8", errors="ignore")
                    time.sleep(0.1)
                return output
            time.sleep(0.3)
        return output
    
    def collect_from_device(self, device_name, proxy_command, commands):
        """
        Collect command outputs from a single device
        
        Returns:
            dict: {
                "reachable": bool,
                "outputs": {"command": {"raw": str, "structured": list/dict}},
                "error": str (if any)
            }
        """
        result = {
            "reachable": False,
            "outputs": {},
            "error": None
        }
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.proxy_ip, username=self.username, 
                       password=self.password, timeout=10)
            
            channel = ssh.invoke_shell()
            channel.send(proxy_command + "\n")
            
            console_output = self._wait_for_prompt(channel, timeout=15)
            if ">" not in console_output and "#" not in console_output:
                result["error"] = "No prompt detected"
                channel.close()
                ssh.close()
                return result
            
            result["reachable"] = True
            
            # Prepare terminal
            channel.send("terminal length 0\n")
            time.sleep(0.5)
            channel.recv(65535)
            
            # Execute commands
            for cmd in commands:
                timeout = 4 if "bgp" in cmd.lower() else 3
                channel.send(cmd + "\n")
                raw_output = self._robust_read(channel, timeout=timeout)
                
                structured = None
                if raw_output:
                    try:
                        structured = parse_output(platform="cisco_ios", 
                                                 command=cmd, data=raw_output)
                    except Exception:
                        pass  # Manual parsing will be done by analyzers
                
                result["outputs"][cmd] = {
                    "raw": raw_output,
                    "structured": structured
                }
            
            channel.send("exit\n")
            channel.close()
            ssh.close()
            
        except Exception as e:
            result["error"] = str(e)
        
        return result