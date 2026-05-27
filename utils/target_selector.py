import re

def evaluate_candidate(candidate: dict, domain: str, company_name: str) -> int:
    score = 0
    title_lower = candidate.get("title", "").lower()
    link_lower = candidate.get("link", "").lower()
    snippet_lower = candidate.get("snippet", "").lower()
    
    domain_clean = domain.lower().strip()
    core_domain = domain_clean.split(".")[0]
    
    # Factor 1: Explicit domain string match (+50 pts)
    if domain_clean in link_lower or domain_clean in title_lower or domain_clean in snippet_lower:
        score += 50
    elif len(core_domain) > 3 and (core_domain in link_lower or core_domain in snippet_lower):
        score += 20
        
    # Factor 2: Token match (cleansing company/domain extensions) (+30 pts max)
    name_clean = re.sub(r"\b(inc|llc|corp|co|ltd|limited)\b", "", company_name.lower()).strip()
    name_tokens = set(re.findall(r"\w+", name_clean))
    
    combined_text = title_lower + " " + snippet_lower
    snippet_tokens = set(re.findall(r"\w+", combined_text))
    overlap = name_tokens.intersection(snippet_tokens)
    
    if name_tokens:
        overlap_ratio = len(overlap) / len(name_tokens)
        score += int(overlap_ratio * 30)
        
    return score

def select_best_candidate(candidates: list[dict], domain: str, company_name: str, threshold: int = 50) -> dict | None:
    scored_candidates = []
    for cand in candidates:
        score = evaluate_candidate(cand, domain, company_name)
        if score >= threshold:
            scored_candidates.append((score, cand))
            
    if not scored_candidates:
        return None
        
    # Return candidate with the highest score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    return scored_candidates[0][1]
