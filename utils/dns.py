import dns.resolver
import asyncio
import socket
import ipaddress

# Professional-grade dictionary of parking IP subnets and individual terminal IPs
PARKING_SUBNETS = [
    "64.70.19.0/24",    # Sedo
    "217.160.0.0/16",   # 1&1 / Sedo
    "184.168.0.0/16",   # GoDaddy
    "34.102.136.0/24",  # GoDaddy/Google Cloud
    "198.54.117.0/24",  # Namecheap
    "192.124.249.0/24", # Dan.com / Sucuri
    "199.59.243.0/24",  # Bodis
    "69.172.201.0/24",  # Afternic
    "185.53.177.0/24",  # ParkingCrew
    "185.53.178.0/24",  # ParkingCrew
    "185.53.179.0/24",  # ParkingCrew
]

PARKING_IPS = {
    "204.11.56.48", "198.71.232.3", "192.64.119.190", 
    "66.96.162.140", "66.96.162.141", "216.58.194.174",
    "172.217.1.14", "23.236.62.147", "103.224.182.245",
}

# Nameserver keywords are the MOST reliable indicator of parking
PARKING_NS_KEYWORDS = [
    "sedoparking", "afternic", "parkingcrew", "uniregistry", 
    "domaincontrol", "registrar-servers", "bodis", "parked", 
    "seller", "dan.com", "buydomains", "hugedomains", "above.com"
]

def _is_ip_in_parking_subnets(ip_str):
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for subnet in PARKING_SUBNETS:
            if ip_obj in ipaddress.ip_network(subnet):
                return True
        return False
    except:
        return False

async def check_dns_parking(domain: str) -> str:
    """
    Advanced Multi-Layer DNS Fingerprinting.
    1. Checks NS Records (Most Reliable)
    2. Checks A Record IP Dictionary
    3. Checks CIDR Subnet Matches
    """
    try:
        # Layer 1: Nameserver Check
        try:
            ns_answers = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: dns.resolver.resolve(domain, 'NS', lifetime=5)
            )
            for ns in ns_answers:
                ns_str = str(ns.target).lower()
                if any(kw in ns_str for kw in PARKING_NS_KEYWORDS):
                    return "PARKED"
        except:
            pass # Continue to IP check if NS fails

        # Layer 2: A Record Check
        test_domains = [domain, f"www.{domain}"]
        resolved_ips = []
        
        for d in test_domains:
            try:
                answers = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: dns.resolver.resolve(d, 'A', lifetime=5)
                )
                for rdata in answers:
                    resolved_ips.append(str(rdata))
            except:
                continue
                
        if not resolved_ips:
            return "DEAD"
            
        for ip in resolved_ips:
            # Direct IP Match
            if ip in PARKING_IPS:
                return "PARKED"
            
            # Subnet/CIDR Match
            if _is_ip_in_parking_subnets(ip):
                return "PARKED"
                
            # Loopback/Private Filter
            if ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
                return "PARKED"
                
        return "ALIVE"
        
    except Exception:
        return "DEAD"
