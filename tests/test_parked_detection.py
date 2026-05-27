import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Import the functions we'll be adding/updating
from utils.scraper import is_parked_content, scrape_url

def test_is_parked_content_positive_cases():
    """Verify that is_parked_content returns a truthy value (or BLOCK: PARKED) for genuine parked/expired domain contents."""
    
    godaddy_parked = "angitia.com coming soon! This page is parked FREE at GoDaddy.com! Domain Names & Transfers"
    assert is_parked_content(godaddy_parked) is True or is_parked_content(godaddy_parked) == "BLOCK: PARKED"
    
    for_sale_form = "agileelectric.com is available for sale! Get a price in less than 24 hours. Fill out the form below."
    assert is_parked_content(for_sale_form) is True or is_parked_content(for_sale_form) == "BLOCK: PARKED"
    
    expired_domain = "NOTICE: This domain name expired on 12/28/2010 and is pending renewal or deletion. Today's offers at GoDaddy."
    assert is_parked_content(expired_domain) is True or is_parked_content(expired_domain) == "BLOCK: PARKED"
    
    namecheap_parked = "Welcome to digiwaves.com. Namebargain.com :: DIGIWAVES.COM :: Parked Domain"
    assert is_parked_content(namecheap_parked) is True or is_parked_content(namecheap_parked) == "BLOCK: PARKED"
    
    simple_parking = "This domain is parked. Buy domain, purchase this domain, renew this domain."
    assert is_parked_content(simple_parking) is True or is_parked_content(simple_parking) == "BLOCK: PARKED"

    # Free-standing placeholders (no registrar name mentioned)
    coming_soon = "Coming Soon! Our new website is currently under development. Check back later for updates."
    assert is_parked_content(coming_soon) is True

    under_construction = "This website is under construction. We will launch soon with amazing new features. Please stay tuned."
    assert is_parked_content(under_construction) is True

    maintenance_mode = "Website is down for temporary maintenance. Down for maintenance, we will be back soon."
    assert is_parked_content(maintenance_mode) is True

def test_is_parked_content_negative_cases():
    """Verify that is_parked_content returns False for genuine business website content."""
    
    genuine_business = (
        "Welcome to Acme Electric! We provide high-quality electrical engineering services to local communities. "
        "Contact our support or view our portfolio of active installations. All rights reserved 2026."
    )
    assert is_parked_content(genuine_business) is False
    
    blog_post = (
        "In this blog post we will discuss domain names and how GoDaddy or Namecheap operates, but we "
        "are actually a tech review company writing about registrar services."
    )
    # The word "GoDaddy" or "Namecheap" by itself without registrar context shouldn't trigger a hard block
    # unless it's a typical parked phrase. We verify we don't overblock just because 'godaddy' is mentioned.
    assert is_parked_content(blog_post) is False

@pytest.mark.asyncio
async def test_scrape_url_httpx_parked_bypass_fix():
    """Verify that scrape_url identifies and blocks a parked page on the HTTPX (fast) path, rather than returning SUCCESS."""
    
    parked_html = "<html><head><title>Domain Parked</title></head><body><h1>This domain is for sale!</h1><p>Buy this domain today.</p></body></html>"
    
    # Mock httpx.AsyncClient to return the parked page
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = parked_html
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_resp
        
        # Call scrape_url. Since it's a parked page, it should return BLOCK: PARKED instead of SUCCESS text
        result = await scrape_url("http://nonexistent-parked-domain-xyz.com")
        assert result == "BLOCK: PARKED"

@pytest.mark.asyncio
async def test_scrape_url_genuine_httpx_passes():
    """Verify that scrape_url returns parsed markdown for a genuine site on the HTTPX pathway."""
    
    genuine_html = (
        "<html><head><title>Acme Corporation - Global Industrial Solutions</title></head><body>"
        "<h1>Welcome to Acme Corp</h1>"
        "<p>We make great things and deliver cutting-edge industrial machinery and consumer goods to "
        "clients worldwide. Founded in 1948, Acme Corporation has been a leader in high-performance "
        "manufacturing, precision engineering, and innovative technology solutions.</p>"
        "<p>Our extensive catalog includes heavy anvil production, specialized jet-powered engines, "
        "and automated manufacturing lines. We specialize in custom integrations for large-scale operations. "
        "Contact our sales department today to request a quote or scheduling a site consultation with "
        "our senior design architects. All products are backed by our global 10-year warranty.</p>"
        "</body></html>"
    )
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = genuine_html
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = mock_resp
        
        result = await scrape_url("http://nonexistent-genuine-domain-xyz.com")
        assert "Welcome to Acme Corp" in result
        assert result != "BLOCK: PARKED"

# --- QUALITY FILTERING & SANITIZATION TDD TESTS ---

def test_html_to_markdown_wayback_navigation_strip():
    """Verify that html_to_markdown decomposes the massive Archive.org navigation footer/sitemap."""
    from utils.scraper import html_to_markdown
    
    html_with_ia_footer = (
        "<html><body>"
        "<h1>My Genuine Business Site</h1>"
        "<p>This is the real content of the website.</p>"
        "<div class=\"archive-footer\">"
        "  <h3>Internet Archive Audio</h3>"
        "  <p>Grateful Dead, Librivox Free Audio, Netlabels, Old Time Radio</p>"
        "</div>"
        "<div class=\"footer-sitemap\" id=\"sitemap-content\">"
        "  <a href=\"/details/audio\">All Audio</a>"
        "  <a href=\"/details/texts\">American Libraries</a>"
        "</div>"
        "</body></html>"
    )
    
    cleaned_markdown = html_to_markdown(html_with_ia_footer)
    
    # The real content must remain, but all IA footer text should be completely stripped
    assert "My Genuine Business Site" in cleaned_markdown
    assert "Internet Archive Audio" not in cleaned_markdown
    assert "Grateful Dead" not in cleaned_markdown
    assert "American Libraries" not in cleaned_markdown

def test_html_to_markdown_safeframe_ad_strip():
    """Verify that html_to_markdown decomposes frames with ad providers or excessively long query strings."""
    from utils.scraper import html_to_markdown
    
    html_with_ad_frames = (
        "<html><body>"
        "<h1>Parked Ad Page</h1>"
        "<iframe src=\"https://findresultsquick.com/sr/754870121/SAFEFRAME.html?ule=864&token=obfuscated_token_here_extra_long_" + ("a" * 200) + "\"></iframe>"
        "<iframe src=\"https://widget.trustpilot.com/trustboxes/index.html\"></iframe>"
        "<iframe src=\"https://legit-business-widget.com/normal\"></iframe>"
        "</body></html>"
    )
    
    cleaned_markdown = html_to_markdown(html_with_ad_frames)
    
    # Obvious ads and extra-long iframe strings must be stripped
    assert "findresultsquick.com" not in cleaned_markdown
    assert "widget.trustpilot.com" not in cleaned_markdown
    # Normal frame placeholder should still exist
    assert "[FRAME: https://legit-business-widget.com/normal]" in cleaned_markdown

def test_is_parked_content_plesk_cpanel_and_cloudflare():
    """Verify that Plesk, cPanel, and Cloudflare challenge templates are blocked regardless of word count."""
    
    plesk_page = (
        "Default page\n"
        "Parallels Plesk Panel\n"
        "Welcome to Parallels! If you are seeing this message, the website for this domain is not available at this time."
        + " " * 500  # Pad with spaces to test length-resiliency
    )
    assert is_parked_content(plesk_page) is True or is_parked_content(plesk_page) == "BLOCK: PARKED"
    
    cpanel_page = "cPanel Holding Page - Welcome! Your site is ready to go." + " " * 500
    assert is_parked_content(cpanel_page) is True or is_parked_content(cpanel_page) == "BLOCK: PARKED"
    
    cloudflare_page = "Attention Required! | Cloudflare. Please enable cookies. Sorry, you have been blocked."
    assert is_parked_content(cloudflare_page) is True or is_parked_content(cloudflare_page) == "BLOCK: PARKED"

def test_html_to_markdown_hard_signature_block():
    """Verify that a page containing the exact signature of the Archive.org sitemap returns empty content."""
    from utils.scraper import html_to_markdown
    
    ia_sitemap_html = (
        "<html><body>"
        "Ask the publishers to restore access to 500,000+ books. "
        "Internet Archive Audio Live Music Archive Librivox Free Audio Featured "
        "Grateful Dead Netlabels Old Time Radio 78 RPMs"
        "</body></html>"
    )
    
    cleaned_markdown = html_to_markdown(ia_sitemap_html)
    assert cleaned_markdown == ""


