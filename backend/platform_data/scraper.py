import requests
from bs4 import BeautifulSoup

def scrape_mitre_analytic_details(strategy_url, analytic_id):
    """
    Scrapes the MITRE Strategy page. Handles cases where tables are siblings 
    (following the ID) rather than children.
    """
    try:
        # 1. Fetch Page
        base_url = strategy_url.split('#')[0]
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; HEFAISTOS/1.0)'}
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # 2. Find the Anchor Element
        start_elem = soup.find(id=analytic_id)
        if not start_elem:
            # Fallback: Sometimes IDs have inconsistent casing or prefixes
            return f"# [ERROR] Could not find anchor #{analytic_id} on MITRE page."

        # 3. Gather Candidate Tables
        # Strategy: 
        # A) Check inside the element (if it's a container div)
        # B) Check following siblings (if it's a header) until next header
        
        tables = list(start_elem.find_all('table')) # Check children first
        
        # Check siblings
        for sibling in start_elem.find_next_siblings():
            # Stop if we hit the next Analytic section (usually starts with a Header or an ID)
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'hr']:
                if sibling.get('id') and sibling['id'] != analytic_id:
                    break
            
            if sibling.name == 'table':
                tables.append(sibling)
            
            # Sometimes tables are wrapped in a div/responsive-table container
            if sibling.name == 'div':
                tables.extend(sibling.find_all('table'))

        if not tables:
            return "# [WARN] Found section but no tables following it."

        output = []

        # 4. Parse Tables
        # Look for the specific headers we need
        
        log_source_table = None
        mutable_table = None
        
        for t in tables:
            # Get all headers in lowercase for loose matching
            headers = [th.get_text(strip=True).lower() for th in t.find_all('th')]
            
            # Identify Log Source Table
            if "data component" in headers and "channel" in headers:
                log_source_table = t
            
            # Identify Mutable Elements Table
            if "field" in headers and "description" in headers:
                mutable_table = t

        # --- FORMAT OUTPUT ---
        
        if log_source_table:
            output.append("\n# [LIVE DATA: LOG SOURCES]")
            # Build a pretty text table
            output.append(f"# {'Data Component':<35} | {'Log Provider':<25} | {'Channel / Event ID'}")
            output.append(f"# {'-'*35} | {'-'*25} | {'-'*30}")
            
            rows = log_source_table.find_all('tr')
            for tr in rows:
                cols = tr.find_all('td')
                if len(cols) >= 3:
                    dc = cols[0].get_text(strip=True)
                    prov = cols[1].get_text(strip=True)
                    chan = cols[2].get_text(strip=True)
                    output.append(f"# {dc:<35} | {prov:<25} | {chan}")

        if mutable_table:
            output.append("\n# [LIVE DATA: MUTABLE ELEMENTS]")
            rows = mutable_table.find_all('tr')
            for tr in rows:
                cols = tr.find_all('td')
                if len(cols) >= 2:
                    field = cols[0].get_text(strip=True)
                    desc = cols[1].get_text(strip=True)
                    output.append(f"# - {field}: {desc}")

        if not output:
            return "# [INFO] Tables found but headers did not match expected 'Data Component' or 'Field'."

        return "\n".join(output)

    except Exception as e:
        return f"# [ERROR] Scraper failed: {str(e)}"


def scrape_mitre_analytic_log_sources(strategy_url, analytic_id):
    """
    Scrape the MITRE Strategy page and return a JSON-friendly list of
    { data_component, log_provider, channel } rows for the selected analytic.
    """
    try:
        base_url = strategy_url.split('#')[0]
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; HEFAISTOS/1.0)'}
        response = requests.get(base_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the section anchor
        start_elem = soup.find(id=analytic_id)
        if not start_elem:
            return []

        # Collect tables under or after the anchor until next header
        tables = list(start_elem.find_all('table'))
        for sibling in start_elem.find_next_siblings():
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'hr']:
                if sibling.get('id') and sibling['id'] != analytic_id:
                    break
            if sibling.name == 'table':
                tables.append(sibling)
            if sibling.name == 'div':
                tables.extend(sibling.find_all('table'))

        if not tables:
            return []

        log_source_table = None
        for t in tables:
            headers = [th.get_text(strip=True).lower() for th in t.find_all('th')]
            if "data component" in headers and "channel" in headers:
                log_source_table = t
                break

        if not log_source_table:
            return []

        out = []
        rows = log_source_table.find_all('tr')
        for tr in rows:
            cols = tr.find_all('td')
            if len(cols) >= 3:
                dc = cols[0].get_text(strip=True)
                prov = cols[1].get_text(strip=True)
                chan_raw = cols[2].get_text(strip=True)

                # Expand multi-value channels like "EventCode=4663, 4670, 4656"
                # Preserve prefix (e.g., "EventCode=") when splitting tokens
                tokens = [t.strip() for t in chan_raw.split(',')]
                if len(tokens) > 1:
                    prefix = None
                    if '=' in chan_raw:
                        prefix = chan_raw.split('=')[0] + '='
                    for tok in tokens:
                        if not tok:
                            continue
                        if '=' not in tok and prefix and tok.replace(' ', '').replace('-', '').isdigit():
                            chan_val = f"{prefix}{tok}"
                        else:
                            chan_val = tok
                        out.append({
                            'data_component': dc,
                            'log_provider': prov,
                            'channel': chan_val,
                        })
                else:
                    out.append({
                        'data_component': dc,
                        'log_provider': prov,
                        'channel': chan_raw,
                    })

        return out

    except Exception:
        return []


# Compatibility wrapper matching developer proposal/name
def scrape_mitre_log_sources_json(strategy_url, analytic_id):
    return scrape_mitre_analytic_log_sources(strategy_url, analytic_id)