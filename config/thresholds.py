"""Health check thresholds"""

# CPU & Memory
CPU_THRESHOLD = 70  # Percentage
MEMORY_THRESHOLD = 80  # Percentage

# BGP
BGP_FLAP_THRESHOLD = 5  # Number of flaps

# OSPF
OSPF_NEIGHBOR_DOWN_CRITICAL = 1  # Any neighbor down is critical
OSPF_LSA_FLOOD_THRESHOLD = 10000  # Total LSAs indicating potential flooding
OSPF_DEAD_TIME_WARNING_SECONDS = 10  # Dead timer close to expiring
OSPF_RETRANSMIT_THRESHOLD = 100  # High retransmit count indicates issues