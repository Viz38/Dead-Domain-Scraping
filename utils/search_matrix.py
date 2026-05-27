import re

def extract_company_name(domain: str) -> str:
    domain = domain.lower().strip()
    domain = re.sub(r"^(https?://)?(www\.)?", "", domain)
    core = domain.split(".")[0]
    core = re.sub(r"[^a-z0-9]", " ", core)
    return core.title()

def generate_company_queries(domain: str, company_name: str) -> list[str]:
    clean_name = company_name.strip()
    return [
        f'"{domain}" site:linkedin.com/company/',
        f'"{domain}"',
        f'site:linkedin.com/company/ "{clean_name}"',
        f'"{clean_name}" (crunchbase OR zoominfo OR pitchbook)'
    ]
