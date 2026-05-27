import pytest
from utils.target_selector import evaluate_candidate, select_best_candidate

def test_evaluate_candidate():
    domain = "acmeelectric.com"
    company_name = "Acme Electric"
    
    # 1. Perfect Match (Explicit domain and token overlap)
    good_cand = {"title": "Acme Electric: Overview | LinkedIn", "link": "https://www.linkedin.com/company/acme-electric", "snippet": "Acme Electric (acmeelectric.com) manufactures machinery."}
    score_good = evaluate_candidate(good_cand, domain, company_name)
    assert score_good >= 80
    
    # 2. Collision Match (Same name, wrong company/domain)
    bad_cand = {"title": "Acme Clothing: Overview | LinkedIn", "link": "https://www.linkedin.com/company/acme-clothing", "snippet": "Acme Clothing is a custom retail shirt shop."}
    score_bad = evaluate_candidate(bad_cand, domain, company_name)
    assert score_bad < 50

def test_select_best_candidate():
    domain = "acmeelectric.com"
    company_name = "Acme Electric"
    candidates = [
        {"title": "Acme Clothing", "link": "https://www.linkedin.com/company/acme-clothing", "snippet": "Clothing retail."},
        {"title": "Acme Electric: Overview", "link": "https://www.linkedin.com/company/acme-electric", "snippet": "Acme Electric (acmeelectric.com) tools."}
    ]
    
    best = select_best_candidate(candidates, domain, company_name)
    assert best["link"] == "https://www.linkedin.com/company/acme-electric"
