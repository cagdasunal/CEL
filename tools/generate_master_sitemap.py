import sys
import requests
import logging
from lxml import etree
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PRIMARY_SITEMAP = "https://www.englishcollege.com/sitemap.xml"
REGIONAL_SITEMAPS = [
    "https://www.englishcollege.com/es/sitemap.xml",
    "https://www.englishcollege.com/de/sitemap.xml",
    "https://www.englishcollege.com/fr/sitemap.xml",
    "https://www.englishcollege.com/ko/sitemap.xml",
    "https://www.englishcollege.com/pt/sitemap.xml",
    "https://www.englishcollege.com/it/sitemap.xml",
    "https://www.englishcollege.com/ja/sitemap.xml",
    "https://www.englishcollege.com/ar/sitemap.xml"
]

# Category path segments across all languages — these pages are noindex
# and must be excluded from the sitemap to avoid conflicting SEO signals.
CATEGORY_SEGMENTS = ["/category/", "/kategorie/", "/categorie/", "/categoria/"]

# Configure logging for GitHub Actions visibility and persistent 'run_log.txt'
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Console Output
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# File Output — write to logs/ subdirectory (gitignored)
import os
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'sitemap_run.log')

file_handler = logging.FileHandler(LOG_FILE, mode='a')
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# Keep log file size reasonable (truncate if > 1MB)
try:
    if os.path.getsize(LOG_FILE) > 1024 * 1024:
        with open(LOG_FILE, 'w') as f:
            f.write("--- Log Rotated ---\n")
except FileNotFoundError:
    pass

def create_robust_session():
    """Create a requests session with automatic retries for transient network errors"""
    session = requests.Session()
    # Retry 3 times with exponential backoff on common server/network errors
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def fetch_sitemap_urls(session, url):
    logging.info(f"Fetching {url}... ")
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        root = etree.fromstring(response.content)
        
        # Find all <url> elements to preserve metadata (lastmod, changefreq, images, etc.)
        nsmap = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        url_elements = root.xpath('//ns:url', namespaces=nsmap)
        if not url_elements:
            url_elements = root.xpath('//url')
            
        results = []
        for el in url_elements:
            loc_el = el.find('ns:loc', namespaces=nsmap)
            if loc_el is None:
                loc_el = el.find('loc')
                
            if loc_el is not None and loc_el.text:
                results.append({"url": loc_el.text.strip(), "element": el})
                
        logging.info(f"  -> Successfully found {len(results)} URLs in {url}.")
        return results
    except requests.exceptions.RequestException as e:
        logging.error(f"  -> Network error fetching {url} after 3 retries: {e}")
        return []
    except etree.XMLSyntaxError as e:
        logging.error(f"  -> XML Parsing error for {url}: {e}")
        return []
    except Exception as e:
        logging.error(f"  -> Unexpected error fetching {url}: {e}")
        return []

def is_category_url(url):
    """Check if a URL is a noindex category page (any language variant)."""
    path = urlparse(url).path
    return any(seg in path for seg in CATEGORY_SEGMENTS)

def get_slug_from_post_url(url):
    """
    Extracts the slug from a URL containing '/post/'.
    e.g. 'https://www.englishcollege.com/fr/post/san-diego' -> 'san-diego'
    """
    if '/post/' in url:
        parts = url.split('/post/')
        if len(parts) > 1:
            slug_part = parts[-1].strip('/')
            return slug_part.split('/')[0] # Get the immediate segment after /post/
    return None

def main():
    logging.info("========== STEP 1: Process Regional Sitemaps ==========")
    regional_urls = []
    regional_slugs = set()
    session = create_robust_session()
    
    regional_category_count = 0
    for sitemap_url in REGIONAL_SITEMAPS:
        data = fetch_sitemap_urls(session, sitemap_url)
        for item in data:
            if is_category_url(item["url"]):
                regional_category_count += 1
                continue  # Skip noindex category pages
            regional_urls.append(item)
            slug = get_slug_from_post_url(item["url"])
            if slug:
                regional_slugs.add(slug)

    if regional_category_count:
        logging.info(f"\nRemoved {regional_category_count} noindex category URLs from regional sitemaps.")
    logging.info(f"\nTotal Regional URLs: {len(regional_urls)}")
    logging.info(f"Total Unique Regional Slugs from '/post/': {len(regional_slugs)}")
    
    logging.info("\n========== STEP 2: Process Primary Sitemap ==========")
    primary_urls = fetch_sitemap_urls(session, PRIMARY_SITEMAP)
    logging.info(f"Total Primary URLs Before Filtering: {len(primary_urls)}")

    if len(primary_urls) == 0:
        logging.error("CRITICAL FAILURE: Could not fetch the Primary Sitemap or it was empty. Aborting to prevent overriding the live sitemap with an empty file.")
        sys.exit(1)

    # Check for Weglot-injected translated URLs in primary (these duplicate regional sitemaps)
    lang_prefixes = ["/es/", "/de/", "/fr/", "/ko/", "/pt/", "/it/", "/ja/", "/ar/"]
    translated_in_primary = [item for item in primary_urls
                             if any(urlparse(item["url"]).path.startswith(p) for p in lang_prefixes)]
    if translated_in_primary:
        logging.warning(f"Primary sitemap contains {len(translated_in_primary)} translated (non-English) URLs — these will duplicate regional sitemaps.")
        for item in translated_in_primary[:5]:
            logging.warning(f"  Example: {item['url']}")
    else:
        logging.info("Primary sitemap contains only English URLs (no Weglot injection — good).")

    cleaned_primary_urls = []
    removed_urls = []
    primary_category_count = 0
    for item in primary_urls:
        u = item["url"]
        if is_category_url(u):
            primary_category_count += 1
            continue  # Skip noindex category pages
        if '/post/' in u:
            slug = get_slug_from_post_url(u)
            if slug and slug in regional_slugs:
                removed_urls.append((slug, u))
                continue # Skip this URL (remove it)
        cleaned_primary_urls.append(item)

    if primary_category_count:
        logging.info(f"\nRemoved {primary_category_count} noindex category URLs from primary sitemap.")
    logging.info(f"\nRemoved {len(removed_urls)} duplicate English '/post/' URLs.")
    if removed_urls:
        logging.info("Removed English phantom URLs (slug → regional version exists):")
        for slug, url in sorted(removed_urls):
            logging.info(f"  - /post/{slug}  ({url})")
    logging.info(f"Total Primary URLs After Filtering: {len(cleaned_primary_urls)}")
    
    logging.info("\n========== STEP 3: Combine and Generate Master Sitemap ==========")
    all_final_urls = cleaned_primary_urls + regional_urls
    logging.info(f"Total Combined URLs for Master Sitemap: {len(all_final_urls)}")
    
    if len(all_final_urls) == 0:
        logging.error("CRITICAL FAILURE: Generating a sitemap with 0 URLs. Aborting.")
        sys.exit(1)
    
    # Create the root element, collecting custom namespaces if possible
    # A standard sitemap usually has the xml namespace, but xhtml and image are common too.
    nsmap = {
        None: "http://www.sitemaps.org/schemas/sitemap/0.9",
        "xhtml": "http://www.w3.org/1999/xhtml",
        "image": "http://www.google.com/schemas/sitemap-image/1.1"
    }
    urlset = etree.Element("urlset", nsmap=nsmap)
    
    for item in all_final_urls:
        # Deepcopy the original element to avoid moving it between documents weirdly
        new_el = etree.SubElement(urlset, "url")
        # Copy children of original element to new element
        for child in item["element"]:
            new_el.append(etree.fromstring(etree.tostring(child)))
        
    tree = etree.ElementTree(urlset)
    master_file = "sitemap.xml"
    
    # Write to file with pretty formatting and xml declaration
    tree.write(master_file, pretty_print=True, xml_declaration=True, encoding="utf-8")
    logging.info(f"\nSuccess! Standard XML Sitemap generated at '{master_file}'.")

if __name__ == "__main__":
    main()
