# Router Health Assistant (PoC)

A lightweight, engineer-side automation tool designed to help **network support and troubleshooting workflows** by performing **on-demand health checks on individual network devices** and explaining issues in a human-readable way.

This project is intentionally **not a monitoring or dashboard platform**.  
It focuses on **per-device, on-demand troubleshooting** to reduce manual effort and context switching.

---

## 🚀 Key Features

- On-demand **per-router health checks**
- Rule-based detection of common routing issues
- Modular **device adapter architecture**
- Human-readable explanations of detected problems
- CLI and structured JSON output
- Secure handling of credentials (no secrets in code)

---

## 🧠 Design Philosophy

- **Engineer-first**: Built for support engineers troubleshooting individual devices or cases
- **Explainable**: Deterministic rules determine health; explanations are layered on top
- **Non-autonomous**: No auto-remediation or configuration changes
- **Extensible**: Easy to add support for additional device operating systems

---

## 🏗️ Architecture Overview

router-health-assistant/
├── main.py # Entry point
├── inventory.yaml # Device inventory (no credentials)
├── adapters/ # Device-specific command adapters
│ ├── base.py
│ └── cisco_ios_xe.py
├── parsers/ # Output parsers
│ └── bgp.py
├── logs/ # Local logs (gitignored)
├── README.md
└── .gitignore


---

## 🔌 Supported Devices (PoC Scope)

- Cisco IOS-XE (initial focus)

> The design supports multi-vendor and multi-OS devices via adapters.  
> The current proof-of-concept intentionally starts with a limited scope.

---

## ▶️ How It Works

1. Engineer selects a device from `inventory.yaml`
2. The tool connects to the device on demand
3. Device-specific adapters execute required commands
4. Outputs are normalized and evaluated using rule-based logic
5. Results are displayed via CLI and JSON output

---

## 📦 Inventory Example

```yaml
devices:
  - name: R1
    host: 10.10.10.1
    device_type: cisco_ios_xe
🔐 Security Considerations
No credentials are stored in the repository

Authentication is handled via environment variables

Logs and sensitive outputs are excluded using .gitignore

🛠️ Tech Stack
Python

Netmiko (planned / optional)

YAML for inventory

CLI / JSON output

📌 Project Status
Work in Progress (Proof of Concept)

Planned enhancements:

Additional routing protocols (OSPF, interface health)

AI-assisted explanation layer

Long-running case and troubleshooting context summarization

Support for additional network operating systems

🎯 Intended Use
This project is intended as:

A learning-focused automation proof-of-concept

A support engineer productivity aid

An example of modular, explainable network automation design

Not intended as:

A centralized monitoring solution

A real-time observability platform

An autonomous remediation system

👤 Author
Sathwik
