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
    
    def _clear_buffer(self, channel):
        """Completely clear the SSH channel buffer"""
        attempts = 0
        max_attempts = 10
        
        while attempts < max_attempts:
            if channel.recv_ready():
                channel.recv(65535)
                time.sleep(0.2)
                attempts = 0  # Reset if we got data
            else:
                attempts += 1
                time.sleep(0.1)
    
    def _robust_read_until_prompt(self, channel, timeout=8):
        """
        Read output until we see the prompt again
        
        Args:
            channel: SSH channel
            timeout: Maximum time to wait
        
        Returns:
            str: Command output (without the command echo and prompt)
        """
        output = ""
        start_time = time.time()
        prompt_seen = False
        
        # Initial delay to let command start executing
        time.sleep(0.5)
        
        while time.time() - start_time < timeout:
            if channel.recv_ready():
                chunk = channel.recv(65535).decode("utf-8", errors="ignore")
                output += chunk
                
                # Check if we've received the prompt (indicating command is done)
                if "#" in chunk or ">" in chunk:
                    prompt_seen = True
                    time.sleep(0.2)  # Small delay to catch any trailing data
                    
                    # Read any remaining data
                    while channel.recv_ready():
                        output += channel.recv(65535).decode("utf-8", errors="ignore")
                        time.sleep(0.1)
                    break
                
                time.sleep(0.1)
            else:
                time.sleep(0.2)
        
        # Clean up the output
        # Remove the command echo (first line)
        lines = output.splitlines()
        if len(lines) > 0:
            # Remove first line (command echo)
            lines = lines[1:]
        
        # Remove the prompt line (last line with # or >)
        if len(lines) > 0:
            last_line = lines[-1].strip()
            if "#" in last_line or ">" in last_line:
                lines = lines[:-1]
        
        cleaned_output = "\n".join(lines)
        return cleaned_output
    
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
            channel.transport.set_keepalive(30)
            
            # Connect via terminal server
            channel.send(proxy_command + "\n")
            
            console_output = self._wait_for_prompt(channel, timeout=15)
            if ">" not in console_output and "#" not in console_output:
                result["error"] = "No prompt detected"
                channel.close()
                ssh.close()
                return result
            
            result["reachable"] = True
            
            # Disable paging
            channel.send("terminal length 0\n")
            time.sleep(0.5)
            self._clear_buffer(channel)
            
            # Execute commands with proper buffer management
            for cmd in commands:
                # Clear buffer before sending command
                self._clear_buffer(channel)
                
                # Send command
                channel.send(cmd + "\n")
                
                # Read output until prompt returns
                timeout = 8 if "bgp" in cmd.lower() else 6
                raw_output = self._robust_read_until_prompt(channel, timeout=timeout)
                
                # Parse with TextFSM
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
            
            # Graceful disconnect
            channel.send("exit\n")
            time.sleep(0.5)
            channel.close()
            ssh.close()
            
        except Exception as e:
            result["error"] = str(e)
        
        return result