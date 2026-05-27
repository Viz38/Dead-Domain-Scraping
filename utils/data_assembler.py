import json

def assemble_metadata_payload(domain: str, snippets: list[str], company_profile: dict) -> str:
    parts = [
        f"### [FALLBACK METADATA FOR: {domain}]",
        "The primary archival scanning failed. This metadata was gathered via public web search fallbacks.",
        "\n## 1. Organic Search Snippets:",
    ]
    for idx, snip in enumerate(snippets, 1):
        parts.append(f"- Snippet {idx}: {snip}")
        
    parts.append("\n## 2. Public LinkedIn Company Profile:")
    parts.append(f"- Name: {company_profile.get('name', 'Unknown')}")
    parts.append(f"- Industry: {company_profile.get('industry', 'Unknown')}")
    
    specialties = company_profile.get('specialties', [])
    specialties_str = ', '.join(specialties) if isinstance(specialties, list) else str(specialties or 'None')
    parts.append(f"- Specialties: {specialties_str}")
    parts.append(f"- Description/Overview:\n{company_profile.get('description', 'No details available.')}")
    
    return "\n".join(parts)
