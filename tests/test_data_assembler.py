import pytest
from utils.data_assembler import assemble_metadata_payload

def test_assemble_metadata_payload():
    snippets = [
        "Acme Electric Overview: Founded in 2012...",
        "Crunchbase: Acme Electric is a leading manufacturer..."
    ]
    company_profile = {
        "name": "Acme Electric",
        "description": "Custom B2B SaaS industrial toolmaker.",
        "industry": "Electrical Equipment",
        "specialties": ["IoT Tools", "Anvils"]
    }
    
    payload = assemble_metadata_payload("acmeelectric.com", snippets, company_profile)
    
    assert "### [FALLBACK METADATA FOR: acmeelectric.com]" in payload
    assert "Acme Electric Overview:" in payload
    assert "Custom B2B SaaS" in payload
    assert "IoT Tools" in payload
