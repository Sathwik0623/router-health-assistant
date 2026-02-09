# quick_check.py
import json

with open("device_health_summary_with_ai.json", "r") as f:
    data = json.load(f)

for device, info in data.items():
    if device == "network_analysis":
        print("\n" + "="*60)
        print("NETWORK ANALYSIS")
        print("="*60)
        print(info.get('analysis', 'N/A'))
    elif isinstance(info, dict) and 'ai_explanation' in info:
        print("\n" + "="*60)
        print(f"DEVICE: {device}")
        print("="*60)
        print(info['ai_explanation'])