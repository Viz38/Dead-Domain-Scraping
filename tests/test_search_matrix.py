import pytest
from utils.search_matrix import generate_company_queries, extract_company_name

def test_extract_company_name():
    assert extract_company_name("https://www.acmeelectric.com") == "Acmeelectric"
    assert extract_company_name("acme-electric.co.uk") == "Acme Electric"

def test_generate_company_queries():
    domain = "acmeelectric.com"
    company_name = "Acme Electric"
    
    queries = generate_company_queries(domain, company_name)
    
    assert len(queries) >= 3
    assert '"acmeelectric.com" site:linkedin.com/company/' in queries[0]
    assert '"acmeelectric.com"' in queries[1]
    assert 'site:linkedin.com/company/ "Acme Electric"' in queries[2]
