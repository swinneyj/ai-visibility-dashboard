"""
AI Visibility Scanner - Technical & AI Engine Audit Module
Combines features from BeFound.ai, LLMScout, Evertune, Peec, and AEO Authority Checker
"""

import re
import json
import socket
import ssl
import requests
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from typing import Dict, List, Any, Optional, Tuple

# Known AI crawler user agents for robots.txt checking
AI_CRAWLERS = {
    "GPTBot": {"type": "training", "description": "OpenAI training bot"},
    "OAI-SearchBot": {"type": "search", "description": "OpenAI search/retrieval bot"},
    "ClaudeBot": {"type": "training", "description": "Anthropic training bot"},
    "Claude-SearchBot": {"type": "search", "description": "Anthropic search/retrieval bot"},
    "PerplexityBot": {"type": "search", "description": "Perplexity search bot"},
    "Google-Extended": {"type": "training", "description": "Google AI training bot"},
    "Applebot-Extended": {"type": "training", "description": "Apple AI training bot"},
    "CCBot": {"type": "search", "description": "Common Crawl bot (used by some LLMs)"},
}

# Schema types relevant for AI visibility
RELEVANT_SCHEMA_TYPES = [
    "Organization", "LocalBusiness", "Product", "Service",
    "FAQPage", "BreadcrumbList", "Article", "BlogPosting",
    "Person", "Event", "Review", "HowTo", "MedicalBusiness",
    "Dentist", "Physician", "Attorney", "RealEstateAgent",
    "Hotel", "Restaurant", "AutomotiveBusiness", "HomeAndConstructionBusiness",
]


def safe_fetch(url: str, timeout: int = 15) -> Tuple[Optional[requests.Response], Optional[str]]:
    """Fetch a URL safely with error handling."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        return resp, None
    except requests.exceptions.SSLError as e:
        return None, f"SSL Error: {str(e)[:100]}"
    except requests.exceptions.ConnectionError as e:
        return None, f"Connection Error: {str(e)[:100]}"
    except requests.exceptions.Timeout:
        return None, "Request timed out"
    except requests.exceptions.RequestException as e:
        return None, f"Request Error: {str(e)[:100]}"


class AIVisibilityScanner:
    """Comprehensive AI visibility scanner for any website."""

    def __init__(self, domain: str, business_name: str = "", city: str = ""):
        # Normalize domain
        if not domain.startswith(("http://", "https://")):
            domain = "https://" + domain
        self.base_url = domain.rstrip("/")
        parsed = urlparse(self.base_url)
        self.domain = parsed.netloc or parsed.path
        self.business_name = business_name or self.domain
        self.city = city
        self.results: Dict[str, Any] = {}
        self.issues: List[Dict] = []
        self.passes: List[Dict] = []
        self.warnings: List[Dict] = []

    CHECK_CATEGORIES = {
        "llms.txt": "geo",
        "robots.txt": "geo",
        "sitemap.xml": "geo",
        "markdown_negotiation": "geo",
        "schema": "geo",
        "open_graph": "geo",
        "twitter_cards": "geo",
        "title_tag": "technical",
        "meta_description": "technical",
        "canonical": "technical",
        "viewport": "technical",
        "language": "technical",
        "headings": "technical",
        "page_access": "technical",
        "ssl": "technical",
        "http2": "technical",
        "page_size": "technical",
        "content_length": "content",
        "content_structure": "content",
        "content_paragraphs": "content",
        "image_alt": "content",
        "contact_info": "content",
        "internal_links": "content",
        "citations": "authority",
        "backlinks": "authority",
        "reviews": "authority",
    }

    def _add_pass(self, check: str, message: str, details: str = ""):
        category = self.CHECK_CATEGORIES.get(check, "technical")
        self.passes.append({"check": check, "message": message, "details": details, "category": category})

    def _add_warn(self, check: str, message: str, details: str = "", fix: str = ""):
        category = self.CHECK_CATEGORIES.get(check, "technical")
        self.warnings.append({"check": check, "message": message, "details": details, "fix": fix, "category": category})

    def _add_issue(self, check: str, message: str, details: str = "", fix: str = ""):
        category = self.CHECK_CATEGORIES.get(check, "technical")
        self.issues.append({"check": check, "message": message, "details": details, "fix": fix, "category": category})

    def to_json_safe(self) -> Dict:
        """Return scan results without non-serializable objects."""
        def clean(obj):
            if isinstance(obj, dict):
                return {k: clean(v) for k, v in obj.items()
                        if k not in ('html', 'raw_html', 'soup', 'all_items')}
            elif isinstance(obj, list):
                return [clean(i) for i in obj
                        if not hasattr(i, '__dict__') or not hasattr(i, 'name')]
            elif isinstance(obj, (str, int, float, bool, type(None))):
                return obj
            else:
                try:
                    json.dumps(obj)
                    return obj
                except (TypeError, ValueError):
                    return str(obj)
        return clean(self.results)

    def run_full_scan(self) -> Dict[str, Any]:
        """Run all checks and return full report."""
        self.results = {}
        self.issues = []
        self.passes = []
        self.warnings = []
        
        # Technical SEO / AI Readiness checks
        self.results["technical"] = self._check_technical()
        
        # Content quality signals
        self.results["content"] = self._check_content()
        
        # Schema / Structured data
        self.results["schema"] = self._check_schema()
        
        # AI crawler access
        self.results["crawlers"] = self._check_ai_crawlers()
        
        # Social & metadata
        self.results["social"] = self._check_social_meta()
        
        # Performance signals
        self.results["performance"] = self._check_performance()
        
        # Calculate scores
        self.results["scores"] = self._calculate_scores()
        
        # Summary
        self.results["summary"] = {
            "pass_count": len(self.passes),
            "warn_count": len(self.warnings),
            "issue_count": len(self.issues),
            "total_checks": len(self.passes) + len(self.warnings) + len(self.issues),
            "domain": self.domain,
            "business_name": self.business_name,
            "city": self.city,
            "scan_timestamp": datetime.utcnow().isoformat(),
        }
        self.results["passes"] = self.passes
        self.results["warnings"] = self.warnings
        self.results["issues"] = self.issues
        
        return self.results

    def _check_technical(self) -> Dict:
        """Technical SEO checks for AI visibility."""
        tech = {}
        
        # 1. llms.txt check
        llms_url = urljoin(self.base_url, "/llms.txt")
        resp, err = safe_fetch(llms_url, timeout=10)
        if resp and resp.status_code == 200:
            content = resp.text[:2000]
            self._add_pass("llms.txt", "llms.txt file found", 
                          f"Located at {llms_url}, {len(content)} chars")
            tech["llms_txt"] = {
                "status": "pass", "url": llms_url,
                "content_preview": content[:500],
                "has_sections": bool(re.search(r'^#+\s', content, re.MULTILINE)),
                "has_links": bool(re.findall(r'https?://', content)),
            }
        else:
            self._add_warn("llms.txt", "No llms.txt file found",
                          "llms.txt helps AI engines understand what pages to cite",
                          "Create an llms.txt at your domain root following the llmstxt.org spec")
            tech["llms_txt"] = {"status": "not_found", "url": llms_url}

        # 2. robots.txt check
        robots_url = urljoin(self.base_url, "/robots.txt")
        resp, err = safe_fetch(robots_url, timeout=10)
        tech["robots_txt"] = {"url": robots_url, "ai_crawlers": {}}
        if resp and resp.status_code == 200:
            robots_text = resp.text
            tech["robots_txt"]["found"] = True
            tech["robots_txt"]["content_preview"] = robots_text[:1000]
            
            # Check each AI crawler
            blocked_crawlers = []
            allowed_crawlers = []
            for bot_name, bot_info in AI_CRAWLERS.items():
                # Simple pattern: find User-agent: botname and check Disallow
                pattern = re.compile(
                    rf'User-agent:\s*{re.escape(bot_name)}\s*\n(.*?)(?:\nUser-agent:|\n$|$)',
                    re.DOTALL | re.IGNORECASE
                )
                match = pattern.search(robots_text)
                status = "not_specified"
                if match:
                    section = match.group(1)
                    disallows = re.findall(r'Disallow:\s*(\S*)', section)
                    if disallows and any(d != '' for d in disallows):
                        status = "blocked"
                        blocked_crawlers.append(bot_name)
                    else:
                        status = "allowed"
                        allowed_crawlers.append(bot_name)
                
                tech["robots_txt"]["ai_crawlers"][bot_name] = {
                    "status": status,
                    "type": bot_info["type"],
                    "description": bot_info["description"],
                }
            
            if blocked_crawlers:
                crawler_list = ", ".join(blocked_crawlers)
                self._add_warn("robots.txt", f"AI crawlers blocked: {crawler_list}",
                              f"These bots are blocked from crawling your site",
                              f"Consider allowing search/retrieval bots while blocking training bots: "
                              f"Set Allow for OAI-SearchBot, Claude-SearchBot, PerplexityBot")
            else:
                self._add_pass("robots.txt", "AI crawlers not blocked",
                              "No critical AI crawler restrictions found")
        else:
            tech["robots_txt"]["found"] = False
            self._add_warn("robots.txt", "No robots.txt found",
                          "AI crawlers may still crawl your site",
                          "Create a robots.txt to explicitly control AI crawler access")

        # 3. Sitemap check
        sitemap_url = urljoin(self.base_url, "/sitemap.xml")
        resp, err = safe_fetch(sitemap_url, timeout=10)
        if resp and resp.status_code == 200:
            sitemap_content = resp.text
            urls_found = len(re.findall(r'<loc>', sitemap_content))
            tech["sitemap"] = {"status": "pass", "url": sitemap_url, "urls_count": urls_found}
            self._add_pass("sitemap.xml", f"Sitemap found with {urls_found} URLs", sitemap_url)
        else:
            # Try /sitemap_index.xml or /sitemap/
            alt_sitemap = urljoin(self.base_url, "/sitemap_index.xml")
            resp2, _ = safe_fetch(alt_sitemap, timeout=10)
            if resp2 and resp2.status_code == 200:
                tech["sitemap"] = {"status": "pass", "url": alt_sitemap}
                self._add_pass("sitemap.xml", "Sitemap index found", alt_sitemap)
            else:
                tech["sitemap"] = {"status": "not_found", "url": sitemap_url}
                self._add_warn("sitemap.xml", "No sitemap.xml found",
                              "Sitemaps help AI crawlers discover your content",
                              "Create a sitemap.xml listing your important pages")

        # 4. Fetch main page for HTML analysis
        resp, err = safe_fetch(self.base_url, timeout=15)
        tech["page_fetchable"] = True
        if err:
            tech["page_fetchable"] = False
            tech["fetch_error"] = err
            self._add_issue("page_access", f"Cannot access page: {err}", "",
                          "Ensure your site is accessible over HTTPS")
            return tech
        
        tech["status_code"] = resp.status_code
        tech["content_type"] = resp.headers.get("Content-Type", "unknown")
        
        # Parse HTML
        soup = BeautifulSoup(resp.text, "lxml")
        tech["html"] = soup
        tech["raw_html"] = resp.text
        
        # 5. Title tag
        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)
            title_len = len(title)
            tech["title"] = {"text": title, "length": title_len}
            if 10 <= title_len <= 60:
                self._add_pass("title_tag", f"Title tag found ({title_len} chars)", title)
            elif title_len < 10:
                self._add_warn("title_tag", f"Title too short ({title_len} chars)", title,
                              "Aim for 10-60 characters with your primary keyword")
            else:
                self._add_warn("title_tag", f"Title too long ({title_len} chars)", title,
                              "Aim for 10-60 characters to avoid truncation")
        else:
            tech["title"] = {"text": "", "length": 0}
            self._add_issue("title_tag", "No title tag found", "",
                          "Add an <title> tag within 10-60 characters")

        # 6. Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content", "").strip():
            desc = meta_desc["content"].strip()
            desc_len = len(desc)
            tech["meta_description"] = {"text": desc, "length": desc_len}
            if 50 <= desc_len <= 160:
                self._add_pass("meta_description", f"Meta description found ({desc_len} chars)", desc[:100])
            else:
                self._add_warn("meta_description", f"Meta description length ({desc_len})",
                              desc[:100], "Aim for 50-160 characters for optimal visibility")
        else:
            tech["meta_description"] = {"text": "", "length": 0}
            self._add_issue("meta_description", "No meta description found", "",
                          "Add a meta description with your value proposition and keywords")

        # 7. Heading structure
        h1_tags = soup.find_all("h1")
        h2_tags = soup.find_all("h2")
        tech["headings"] = {
            "h1_count": len(h1_tags),
            "h2_count": len(h2_tags),
            "h1_texts": [h.get_text(strip=True)[:80] for h in h1_tags],
            "h2_texts": [h.get_text(strip=True)[:80] for h in h2_tags[:10]],
        }
        if len(h1_tags) == 0:
            self._add_issue("headings", "No H1 tag found", "",
                          "Add one H1 tag describing the page")
        elif len(h1_tags) > 2:
            self._add_warn("headings", f"Multiple H1 tags ({len(h1_tags)})",
                          "Multiple H1s can confuse crawlers about page structure",
                          "Use only one H1 per page")
        else:
            h1_text = h1_tags[0].get_text(strip=True)[:60]
            self._add_pass("headings", f"Good heading structure (1 H1, {len(h2_tags)} H2s)", h1_text)

        # 8. Content length
        body_text = soup.get_text(strip=True)
        word_count = len(body_text.split())
        tech["content"] = {"word_count": word_count, "char_count": len(body_text)}
        if word_count < 200:
            self._add_warn("content_length", f"Very thin content ({word_count} words)",
                          "AI engines favor substantive pages with detailed information",
                          "Add more comprehensive content (aim for 500+ words)")
        elif word_count < 500:
            self._add_warn("content_length", f"Light content ({word_count} words)",
                          "Consider expanding content for better AI citation",
                          "Aim for 500+ words with detailed, structured information")
        else:
            self._add_pass("content_length", f"Good content volume ({word_count} words)", "")

        # 9. Canonical tag
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            tech["canonical"] = canonical["href"]
            self._add_pass("canonical", "Canonical tag found", canonical["href"])
        else:
            tech["canonical"] = ""
            self._add_warn("canonical", "No canonical tag", "",
                          "Canonical tags prevent duplicate content issues with crawlers")

        # 10. Viewport / mobile
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if viewport:
            tech["viewport"] = viewport.get("content", "")
            self._add_pass("viewport", "Viewport meta tag found", "Mobile-friendly signals present")
        else:
            tech["viewport"] = ""
            self._add_warn("viewport", "No viewport meta tag",
                          "AI engines and crawlers prioritize mobile-friendly sites",
                          "Add <meta name='viewport' content='width=device-width, initial-scale=1'>")

        # 11. Language declaration
        html_tag = soup.find("html")
        lang = html_tag.get("lang", "") if html_tag else ""
        tech["language"] = lang if lang else "not set"
        if lang:
            self._add_pass("language", f"Language declared: {lang}", "")
        else:
            self._add_warn("language", "No language declaration on <html> tag",
                          "Helps AI engines understand your content context",
                          "Add lang='en' or appropriate language to <html> tag")

        # 12. Internal linking density
        links = soup.find_all("a", href=True)
        internal_links = [l for l in links if self.domain in l["href"] or l["href"].startswith("/")]
        external_links = [l for l in links if l["href"].startswith("http") and self.domain not in l["href"]]
        tech["links"] = {
            "total": len(links),
            "internal": len(internal_links),
            "external": len(external_links),
        }
        if len(internal_links) < 3:
            self._add_warn("internal_links", f"Very few internal links ({len(internal_links)})",
                          "Internal links help crawlers discover more of your content",
                          "Add contextual internal links to your important pages")
        else:
            self._add_pass("internal_links", f"Good internal linking ({len(internal_links)} links)", "")

        # 13. Markdown content negotiation check
        try:
            md_headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/markdown, text/html",
            }
            md_resp = requests.get(self.base_url, headers=md_headers, timeout=10)
            content_type = md_resp.headers.get("Content-Type", "")
            tech["markdown_negotiation"] = {
                "accept_markdown_sent": True,
                "response_content_type": content_type,
                "returns_markdown": "text/markdown" in content_type,
            }
            if "text/markdown" in content_type:
                self._add_pass("markdown_negotiation", "Server supports Markdown content negotiation",
                              "AI crawlers can receive optimized, token-efficient content")
            else:
                self._add_pass("markdown_negotiation", "Standard HTML response (no Markdown negotiation)",
                              "Most sites don't offer this yet; not a blocker")
        except Exception:
            tech["markdown_negotiation"] = {"error": "Could not test"}

        return tech

    def _check_schema(self) -> Dict:
        """Structured data / Schema.org analysis."""
        schema = {}
        page = self.results.get("technical", {})
        soup = page.get("html")
        if not soup:
            resp, _ = safe_fetch(self.base_url, timeout=15)
            if not resp:
                return {"error": "Cannot fetch page"}
            soup = BeautifulSoup(resp.text, "lxml")
        
        # Find all JSON-LD scripts
        jsonld_scripts = soup.find_all("script", type="application/ld+json")
        schema["jsonld_count"] = len(jsonld_scripts)
        
        all_schemas = []
        schema_types_found = []
        
        for script in jsonld_scripts:
            try:
                data = json.loads(script.string) if script.string else {}
                # Handle @graph (multiple schemas in one script)
                if "@graph" in data:
                    items = data["@graph"]
                else:
                    items = [data]
                
                for item in items:
                    stype = item.get("@type", "Unknown")
                    if isinstance(stype, list):
                        stype = stype[0]
                    schema_types_found.append(stype)
                    all_schemas.append(item)
            except (json.JSONDecodeError, AttributeError):
                continue
        
        schema["types_found"] = schema_types_found
        schema["all_items"] = all_schemas
        
        # Check for relevant schema types
        found_relevant = [t for t in schema_types_found if t in RELEVANT_SCHEMA_TYPES]
        schema["relevant_types"] = found_relevant
        
        if len(found_relevant) >= 3:
            self._add_pass("schema", f"Good structured data ({len(found_relevant)} relevant types)",
                          f"Types: {', '.join(found_relevant[:5])}")
        elif len(found_relevant) > 0:
            self._add_warn("schema", f"Limited structured data ({len(found_relevant)} types)",
                          f"Found: {', '.join(found_relevant)}",
                          "Add Organization, LocalBusiness, FAQPage, and BreadcrumbList schema")
        else:
            self._add_issue("schema", "No relevant schema.org structured data found",
                          "AI engines heavily rely on structured data for understanding businesses",
                          "Add JSON-LD structured data: Organization, LocalBusiness, FAQPage, BreadcrumbList")
        
        # Check for specific critical schemas
        schema["has_organization"] = "Organization" in schema_types_found
        schema["has_local_business"] = any(t in schema_types_found for t in 
                                          ["LocalBusiness", "MedicalBusiness", "Dentist", 
                                           "Physician", "Attorney", "Restaurant"])
        schema["has_faq"] = "FAQPage" in schema_types_found
        schema["has_breadcrumbs"] = "BreadcrumbList" in schema_types_found
        schema["has_product"] = "Product" in schema_types_found
        
        return schema

    def _check_ai_crawlers(self) -> Dict:
        """Check AI crawler access patterns."""
        crawler_info = {}
        
        # Test direct crawler headers / behavior
        for bot_name in ["GPTBot", "OAI-SearchBot", "ClaudeBot"]:
            try:
                headers = {
                    "User-Agent": f"{botName}/1.0",
                    "Accept": "text/html,*/*",
                }
                resp = requests.get(self.base_url, headers=headers, timeout=10)
                crawler_info[bot_name] = {
                    "status_code": resp.status_code,
                    "accessible": resp.status_code == 200,
                }
            except Exception:
                crawler_info[bot_name] = {"status_code": 0, "accessible": False}
        
        return crawler_info

    def _check_content(self) -> Dict:
        """Content quality signals for AI visibility."""
        content = {}
        page = self.results.get("technical", {})
        soup = page.get("html")
        if not soup:
            return {"error": "No HTML parsed"}
        
        raw_html = page.get("raw_html", "")
        body = soup.find("body")
        body_text = body.get_text(strip=True) if body else soup.get_text(strip=True)
        
        # Keyword analysis from title and content
        title = page.get("title", {}).get("text", "")
        h1s = page.get("headings", {}).get("h1_texts", [])
        primary_terms = (title + " " + " ".join(h1s)).lower().split()
        
        # Check for structured content elements
        lists = soup.find_all(["ul", "ol"])
        tables = soup.find_all("table")
        bold_texts = soup.find_all(["strong", "b"])
        
        content["has_lists"] = len(lists) > 0
        content["has_tables"] = len(tables) > 0
        content["has_formatted_text"] = len(bold_texts) > 0
        content["lists_count"] = len(lists)
        content["tables_count"] = len(tables)
        
        if len(lists) > 0:
            self._add_pass("content_structure", f"Content includes {len(lists)} lists",
                          "Lists improve AI parseability")
        else:
            self._add_warn("content_structure", "No lists found in content",
                          "AI engines prefer structured, scannable content",
                          "Add bullet/numbered lists to break up text")
        
        # Image alt text analysis
        images = soup.find_all("img")
        images_with_alt_list = [img for img in images if img.get("alt")]
        content["images_total"] = len(images)
        content["images_with_alt"] = len(images_with_alt_list)
        
        if len(images_with_alt_list) < len(images) and len(images) > 0:
            self._add_warn("image_alt", f"{len(images) - len(images_with_alt_list)} images missing alt text",
                          "AI crawlers read alt text to understand images",
                          "Add descriptive alt text to all images")
        elif len(images) > 0:
            self._add_pass("image_alt", f"All {len(images)} images have alt text", "")
        
        # Content freshness signals
        import re as regex
        dates_found = regex.findall(
            r'\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b', raw_html
        )
        content["dates_in_content"] = len(dates_found) > 0
        
        # Paragraph count
        paras = soup.find_all("p")
        para_texts = [p.get_text(strip=True) for p in paras if len(p.get_text(strip=True)) > 20]
        content["substantial_paragraphs"] = len(para_texts)
        
        if len(para_texts) < 3:
            self._add_warn("content_paragraphs", f"Only {len(para_texts)} substantial paragraphs",
                          "AI engines need enough text to understand your business",
                          "Add 3+ descriptive paragraphs about your business")
        else:
            self._add_pass("content_paragraphs", f"{len(para_texts)} substantial paragraphs found", "")
        
        # Address / contact info (important for local AI visibility)
        has_email = bool(re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', body_text))
        has_phone = bool(re.search(r'[\+\d][\d\s\-\(\)]{7,20}', body_text))
        has_address = bool(re.search(r'\d+\s+[\w\s]+,?\s*(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way)', body_text, re.IGNORECASE))
        
        content["contact_info"] = {
            "has_email": has_email,
            "has_phone": has_phone,
            "has_address": has_address,
        }
        
        contact_signals = sum([has_email, has_phone, has_address])
        if contact_signals >= 2:
            self._add_pass("contact_info", f"Good contact info ({contact_signals}/3 signals found)",
                          "Contact info boosts local AI visibility")
        else:
            self._add_warn("contact_info", f"Limited contact info ({contact_signals}/3 signals)",
                          "AI engines need contact info to recommend local businesses",
                          "Add phone, address, and email to your site")
        
        return content

    def _check_social_meta(self) -> Dict:
        """Social media metadata / Open Graph / Twitter Cards."""
        social = {}
        page = self.results.get("technical", {})
        soup = page.get("html")
        if not soup:
            return {"error": "No HTML parsed"}
        
        # Open Graph tags
        og_tags = {}
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            content = meta.get("content", "")
            if prop.startswith("og:"):
                og_tags[prop] = content
        
        social["og_tags"] = og_tags
        social["has_og_title"] = "og:title" in og_tags
        social["has_og_description"] = "og:description" in og_tags
        social["has_og_image"] = "og:image" in og_tags
        
        og_found = sum([social["has_og_title"], social["has_og_description"], social["has_og_image"]])
        if og_found >= 2:
            self._add_pass("open_graph", f"Open Graph tags found ({og_found}/3)", 
                          f"og:title={og_tags.get('og:title', 'N/A')[:60]}")
        else:
            self._add_warn("open_graph", f"Incomplete Open Graph tags ({og_found}/3)",
                          "Open Graph tags control how your site appears when shared on social/AI",
                          "Add og:title, og:description, and og:image meta tags")
        
        # Twitter Cards
        twitter_tags = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name", "")
            content = meta.get("content", "")
            if name.startswith("twitter:"):
                twitter_tags[name] = content
        
        social["twitter_cards"] = twitter_tags
        social["has_twitter_card"] = "twitter:card" in twitter_tags
        
        if twitter_tags:
            self._add_pass("twitter_cards", "Twitter Card tags found", "")
        else:
            self._add_warn("twitter_cards", "No Twitter Card tags",
                          "Twitter Cards improve sharing appearance",
                          "Add twitter:card, twitter:title, twitter:description, twitter:image")
        
        return social

    def _check_performance(self) -> Dict:
        """Basic performance and security signals."""
        perf = {}
        
        # SSL check
        try:
            parsed = urlparse(self.base_url)
            hostname = parsed.hostname or self.domain
            ctx = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    issuer = "Unknown"
                    if cert:
                        issuer_raw = cert.get("issuer", [])
                        for item in issuer_raw:
                            if isinstance(item, tuple) and len(item) >= 2:
                                k, v = item[0], item[1]
                                if "organizationName" in str(k):
                                    issuer = str(v)
                                    break
                    perf["ssl"] = {
                        "valid": True,
                        "issuer": issuer,
                        "expiry": cert.get("notAfter", "Unknown") if cert else "Unknown",
                    }
            self._add_pass("ssl", "Valid SSL certificate", f"Issuer: {perf['ssl']['issuer']}")
        except Exception as e:
            perf["ssl"] = {"valid": False, "error": str(e)[:100]}
            self._add_issue("ssl", "SSL certificate issue", str(e)[:200],
                          "Ensure your site has a valid SSL certificate (HTTPS)")
        
        # HTTP/2 support check
        try:
            h2_resp = requests.get(self.base_url, timeout=10)
            perf["http_version"] = "HTTP/2" if h2_resp.raw.version == 2 else f"HTTP/{h2_resp.raw.version}"
            if h2_resp.raw.version >= 2:
                self._add_pass("http2", f"Using {perf['http_version']}", "Faster, modern protocol")
            else:
                self._add_pass("http2", f"Using {perf['http_version']}", "Upgrade to HTTP/2 for better performance")
        except Exception:
            perf["http_version"] = "unknown"
        
        # Page size
        page = self.results.get("technical", {})
        raw_html = page.get("raw_html", "")
        perf["html_size_kb"] = round(len(raw_html) / 1024, 1)
        if perf["html_size_kb"] > 500:
            self._add_warn("page_size", f"Large page ({perf['html_size_kb']} KB HTML)",
                          "Large pages are slower to load and parse",
                          "Optimize HTML size, defer non-critical resources")
        else:
            self._add_pass("page_size", f"Reasonable page size ({perf['html_size_kb']} KB)", "")
        
        return perf

    def _calculate_scores(self) -> Dict:
        """Calculate visibility scores based on check results."""
        scores = {}
        
        # Technical Readiness Score (0-100)
        tech_checks = {
            "llms.txt": 15,
            "robots.txt_proper": 10,
            "sitemap": 10,
            "title_tag": 10,
            "meta_description": 10,
            "headings": 8,
            "canonical": 5,
            "language": 3,
            "viewport": 4,
            "content_length": 10,
            "internal_links": 5,
            "ssl": 10,
        }
        
        tech_score = 0
        for check in self.passes:
            if check["check"] in tech_checks:
                tech_score += tech_checks[check["check"]]
        for check in self.warnings:
            if check["check"] in tech_checks:
                tech_score += tech_checks[check["check"]] * 0.5
        
        scores["technical_readiness"] = min(100, int(tech_score))
        
        # Schema Score (0-100)
        schema = self.results.get("schema", {})
        schema_score = 0
        if schema.get("has_organization"): schema_score += 25
        if schema.get("has_local_business"): schema_score += 25
        if schema.get("has_faq"): schema_score += 20
        if schema.get("has_breadcrumbs"): schema_score += 15
        if schema.get("has_product"): schema_score += 15
        if schema.get("jsonld_count", 0) > 0: schema_score += 10
        schema_score = min(100, schema_score + len(schema.get("types_found", [])) * 5)
        scores["schema_readiness"] = schema_score
        
        # Content Quality Score (0-100)
        content = self.results.get("content", {})
        content_score = 0
        word_count = self.results.get("technical", {}).get("content", {}).get("word_count", 0)
        if word_count >= 2000: content_score += 30
        elif word_count >= 1000: content_score += 20
        elif word_count >= 500: content_score += 10
        else: content_score += 0
        
        if content.get("has_lists"): content_score += 15
        if content.get("has_tables"): content_score += 10
        if content.get("substantial_paragraphs", 0) >= 3: content_score += 15
        if content.get("dates_in_content"): content_score += 5
        contact = content.get("contact_info", {})
        content_score += sum([contact.get("has_email", False),
                              contact.get("has_phone", False),
                              contact.get("has_address", False)]) * 5
        scores["content_quality"] = min(100, content_score if content_score > 0 else 10)
        
        # Social Meta Score
        social = self.results.get("social", {})
        social_score = 0
        if social.get("has_og_title"): social_score += 25
        if social.get("has_og_description"): social_score += 25
        if social.get("has_og_image"): social_score += 20
        if social.get("has_twitter_card"): social_score += 15
        if len(social.get("og_tags", {})) >= 3: social_score += 15
        scores["social_meta"] = min(100, social_score)
        
        # Performance Score
        perf = self.results.get("performance", {})
        perf_score = 50
        if perf.get("ssl", {}).get("valid"): perf_score += 20
        if perf.get("http_version", "") == "HTTP/2": perf_score += 15
        if perf.get("html_size_kb", 0) < 200: perf_score += 15
        elif perf.get("html_size_kb", 0) < 500: perf_score += 10
        scores["performance"] = min(100, perf_score)
        
        # Overall AI Visibility Score (weighted composite)
        overall = (
            scores["technical_readiness"] * 0.30 +
            scores["schema_readiness"] * 0.25 +
            scores["content_quality"] * 0.25 +
            scores["social_meta"] * 0.10 +
            scores["performance"] * 0.10
        )
        scores["overall"] = int(overall)
        
        # Grade
        if scores["overall"] >= 90:
            scores["grade"] = "A+"
        elif scores["overall"] >= 80:
            scores["grade"] = "A"
        elif scores["overall"] >= 70:
            scores["grade"] = "B"
        elif scores["overall"] >= 60:
            scores["grade"] = "C"
        elif scores["overall"] >= 40:
            scores["grade"] = "D"
        else:
            scores["grade"] = "F"
        
        return scores

    def generate_recommendations(self) -> List[Dict]:
        """Generate prioritized fix recommendations."""
        recs = []
        for issue in self.issues:
            recs.append({
                "priority": "high",
                "type": "fix",
                "check": issue["check"],
                "message": issue["message"],
                "fix": issue.get("fix", ""),
            })
        for warn in self.warnings:
            recs.append({
                "priority": "medium",
                "type": "improve",
                "check": warn["check"],
                "message": warn["message"],
                "fix": warn.get("fix", ""),
            })
        return recs


def scan_domain(domain: str, business_name: str = "", city: str = "") -> Dict:
    """Convenience function to run a full scan."""
    scanner = AIVisibilityScanner(domain, business_name, city)
    scanner.run_full_scan()
    scanner.results["recommendations"] = scanner.generate_recommendations()
    return scanner.to_json_safe()
