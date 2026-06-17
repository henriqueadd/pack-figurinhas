import os
import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser

# Target website URL
BASE_URL = "https://trokajotreinamentos.online/pack-figurinhas/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Directory where we save assets
OUTPUT_DIR = r"C:\Users\henri\.gemini\antigravity\scratch\pack-figurinhas"
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets")

# Headers for HTTP requests to prevent 403/406 errors
headers = {"User-Agent": USER_AGENT}

def download_file(url, local_path):
    """Downloads a file from url and saves it to local_path."""
    # Safety checks
    if not url or url.startswith("data:") or url.startswith("javascript:") or url.startswith("mailto:") or url.startswith("tel:"):
        return False
        
    try:
        # Create directories if they do not exist
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # Don't download again if file already exists
        if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
            print(f"Already exists: {local_path}")
            return True

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(local_path, "wb") as f:
                f.write(response.read())
        print(f"Downloaded: {url} -> {local_path}")
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def clean_filename(url_path):
    """Cleans up the path, removing query strings and handling default filenames."""
    # Remove query string
    path = url_path.split("?")[0]
    # Remove fragments
    path = path.split("#")[0]
    # Decode URL percent-encoding
    path = urllib.parse.unquote(path)
    # Ensure it doesn't end with a slash
    if path.endswith("/"):
        path += "index.html"
    return path

class AssetExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = set()

    def is_valid_url(self, url):
        if not url:
            return False
        url = url.strip()
        # Exclude data/javascript/mailto etc
        if any(url.startswith(pfx) for pfx in ["data:", "javascript:", "mailto:", "tel:", "#"]):
            return False
        return True

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # Check script src
        if tag == "script" and "src" in attrs_dict:
            src = attrs_dict["src"]
            if self.is_valid_url(src):
                self.assets.add(src)
            
        # Check link href
        elif tag == "link" and "href" in attrs_dict:
            href = attrs_dict["href"]
            if self.is_valid_url(href):
                rel = attrs_dict.get("rel", "")
                # We want stylesheets, icons, preloads that are styles/scripts/images
                if "stylesheet" in rel or "icon" in rel or attrs_dict.get("as") in ["style", "script", "image", "font"]:
                    self.assets.add(href)
                
        # Check img src and data-src / data-lazy-src
        elif tag == "img":
            for attr in ["src", "data-src", "data-lazy-src", "data-original-src"]:
                if attr in attrs_dict:
                    val = attrs_dict[attr]
                    if self.is_valid_url(val):
                        self.assets.add(val)
                    
        # Check source srcset
        elif tag == "source" and "srcset" in attrs_dict:
            # srcset can be comma-separated list of urls, e.g. "image.png 1x, image2.png 2x"
            srcset = attrs_dict["srcset"]
            for part in srcset.split(","):
                part = part.strip().split(" ")[0]
                if self.is_valid_url(part):
                    self.assets.add(part)
                    
        # Check video src
        elif tag == "video" and "src" in attrs_dict:
            src = attrs_dict["src"]
            if self.is_valid_url(src):
                self.assets.add(src)

def process_css_content(css_url, css_content):
    """Finds all url() references in CSS content, downloads them, and updates CSS."""
    # Simpler, non-backtracking regex to avoid recursion limit errors on large files
    url_pattern = re.compile(r'url\(\s*[\'"]?([^\'"\)]+)[\'"]?\s*\)', re.IGNORECASE)
    
    updated_content = css_content
    matches = url_pattern.findall(css_content)
    
    for url in matches:
        url = url.strip()
        # Skip data URIs or empty links
        if not url or any(url.startswith(pfx) for pfx in ["data:", "javascript:", "mailto:", "tel:", "#"]):
            continue
            
        # Resolve full URL relative to the CSS file's URL
        full_url = urllib.parse.urljoin(css_url, url)
        
        # We only download if it's on the target domain
        parsed_url = urllib.parse.urlparse(full_url)
        
        # Ensure scheme is valid http/https
        if parsed_url.scheme not in ["http", "https"]:
            continue
            
        if parsed_url.netloc == "trokajotreinamentos.online" or not parsed_url.netloc:
            # Map to local path
            clean_path = clean_filename(parsed_url.path)
            if clean_path.startswith("/"):
                clean_path = clean_path[1:]
                
            local_asset_path = os.path.join(ASSETS_DIR, clean_path)
            
            # Download asset
            if download_file(full_url, local_asset_path):
                # Calculate relative path from CSS file to asset file
                parsed_css_url = urllib.parse.urlparse(css_url)
                clean_css_path = clean_filename(parsed_css_url.path)
                if clean_css_path.startswith("/"):
                    clean_css_path = clean_css_path[1:]
                local_css_path = os.path.join(ASSETS_DIR, clean_css_path)
                
                relative_path = os.path.relpath(local_asset_path, os.path.dirname(local_css_path))
                # Normalize path for web (forward slashes)
                relative_path = relative_path.replace("\\", "/")
                
                # Replace in CSS
                # Use standard string replace of the url matched to make it safe
                # Note: we need to handle original matching quotes if any, but replacing the URL string inside quotes is safer
                updated_content = updated_content.replace(url, relative_path)
                
    return updated_content

def main():
    print(f"Starting cloning of {BASE_URL}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)
    
    # 1. Fetch index page
    print("Fetching index page...")
    req = urllib.request.Request(BASE_URL, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            html_content = response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"Failed to fetch base URL: {e}")
        # Try local backup
        backup_path = r"C:\Users\henri\.gemini\antigravity\brain\d1b5e115-3f3b-41d2-a828-a11b804e2e7d\.system_generated\steps\3\content.md"
        if os.path.exists(backup_path):
            print("Reading from local step backup...")
            with open(backup_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Extract HTML part from the markdown step content
                html_start = content.find("<!DOCTYPE html>")
                if html_start != -1:
                    html_content = content[html_start:]
                else:
                    html_content = content
        else:
            print("No backup found, exiting.")
            return

    # 2. Extract assets
    extractor = AssetExtractor()
    extractor.feed(html_content)
    
    print(f"Found {len(extractor.assets)} assets in HTML.")
    
    # Map of original URL -> local relative path
    url_mapping = {}
    
    # Process assets
    for asset_url in extractor.assets:
        asset_url = asset_url.strip()
        if not asset_url:
            continue
            
        # Resolve to absolute URL
        full_url = urllib.parse.urljoin(BASE_URL, asset_url)
        parsed_url = urllib.parse.urlparse(full_url)
        
        # Ensure scheme is valid http/https
        if parsed_url.scheme not in ["http", "https"]:
            continue
            
        is_target_domain = (parsed_url.netloc == "trokajotreinamentos.online" or not parsed_url.netloc)
        is_static_asset = any(parsed_url.path.lower().endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".woff", ".woff2", ".ttf"])
        
        if is_target_domain or is_static_asset:
            # Generate clean path inside assets/
            netloc_dir = parsed_url.netloc.replace(":", "_")
            clean_path = clean_filename(parsed_url.path)
            if clean_path.startswith("/"):
                clean_path = clean_path[1:]
                
            # If it's external, put it under a separate subfolder of assets/ to avoid conflicts
            if not is_target_domain:
                local_asset_path = os.path.join(ASSETS_DIR, "external", netloc_dir, clean_path)
            else:
                local_asset_path = os.path.join(ASSETS_DIR, clean_path)
                
            # Download file
            if download_file(full_url, local_asset_path):
                # Calculate relative path from root directory (where index.html is)
                relative_path = os.path.relpath(local_asset_path, OUTPUT_DIR)
                relative_path = relative_path.replace("\\", "/") # Normalize for web
                url_mapping[asset_url] = relative_path
                
                # Special handling for CSS: parse and download internal assets (like fonts, bg images)
                if clean_path.lower().endswith(".css"):
                    try:
                        with open(local_asset_path, "r", encoding="utf-8", errors="ignore") as f:
                            css_content = f.read()
                        
                        updated_css = process_css_content(full_url, css_content)
                        
                        with open(local_asset_path, "w", encoding="utf-8") as f:
                            f.write(updated_css)
                        print(f"Processed CSS: {local_asset_path}")
                    except Exception as e:
                        print(f"Error processing CSS {local_asset_path}: {e}")

    # 3. Rewrite HTML content
    print("Rewriting HTML content with local links...")
    updated_html = html_content
    
    # Sort keys by length in descending order to avoid replacing substrings first
    for orig_url in sorted(url_mapping.keys(), key=len, reverse=True):
        local_ref = url_mapping[orig_url]
        
        # Replace simple occurrences
        # We need to escape any regex characters in original URL
        escaped_url = re.escape(orig_url)
        # Match URL surrounded by quotes or attributes
        pattern = re.compile(rf'([\'"]){escaped_url}([\'"])')
        updated_html = pattern.sub(rf'\1{local_ref}\2', updated_html)
        
        # Fallback raw replacement for cases where it might not be in quotes
        updated_html = updated_html.replace(orig_url, local_ref)

    # Save index.html
    index_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(updated_html)
    print(f"Successfully created index.html at {index_path}")

if __name__ == "__main__":
    main()
