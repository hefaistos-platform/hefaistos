import uuid
import yaml
import re
from xml.etree import ElementTree
import posixpath


# Platform rule extraction output structure:
# <repo-root>/<targetFolder?>/{kql|splunk|sigma|wazuh|qradar}/<sanitized_title>.<ext>
PLATFORM_DIR_MAP = {
    'kql': 'kql',
    'elastic': 'elastic',
    'spl': 'splunk',
    'sigma': 'sigma',
    'wazuh': 'wazuh',
    'qradar': 'qradar',
}

PLATFORM_EXT_MAP = {
    'kql': '.kql',
    'elastic': '.eql',
    'spl': '.spl',
    'sigma': '.yml',
    'wazuh': '.xml',
    'qradar': '.aql',
}



def extract_platform_rules_from_opentide(
    mdr_data: dict,
    base_folder: str = '',
    sanitized_title: str = '',
) -> dict:
    """
    Returns {relative_path: content_string} for each platform rule found
    in the platforms/configurations blocks of an OpenTide MDR YAML dict.

    The filename for every platform rule is derived from the MDR's
    ``metadata.title`` field (= the playbook title).  The caller is expected
    to pass an already-sanitized version of that title as ``sanitized_title``.
    If not provided the function falls back to the snake_case ``name`` field.

    Files are placed under <base_folder>/<platform_dir>/<sanitized_title>.<ext>
    Platforms: kql, elastic, spl, sigma, wazuh, qradar
    """
    if not isinstance(mdr_data, dict):
        return {}

    title = (sanitized_title or mdr_data.get('name') or 'detection_rule').strip() or 'detection_rule'
    base = (base_folder or '').strip('/')
    files = {}

    platforms = mdr_data.get('platforms') or {}
    configurations = mdr_data.get('configurations') or {}

    def _rule_file_path(platform_key: str) -> str:
        return posixpath.join(
            *([base] if base else []),
            PLATFORM_DIR_MAP[platform_key],
            f'{title}{PLATFORM_EXT_MAP[platform_key]}',
        )

    def _pick_query(*sources):
        for source in sources:
            if isinstance(source, dict):
                query = (source.get('query') or '').strip()
                if query:
                    return query
        return ''

    kql_content = _pick_query(
        platforms.get('kql'),
        configurations.get('defender_for_endpoint'),
        configurations.get('microsoft_sentinel'),
    )
    if kql_content:
        files[_rule_file_path('kql')] = kql_content

    spl_content = _pick_query(platforms.get('spl'), configurations.get('splunk'))
    if spl_content:
        files[_rule_file_path('spl')] = spl_content

    elastic_content = _pick_query(platforms.get('elastic'), configurations.get('elastic'))
    if elastic_content:
        files[_rule_file_path('elastic')] = elastic_content

    qradar_content = _pick_query(platforms.get('qradar'), configurations.get('qradar'))
    if qradar_content:
        files[_rule_file_path('qradar')] = qradar_content

    for key in ('wazuh',):
        platform_block = platforms.get(key) if isinstance(platforms.get(key), dict) else {}
        config_block = configurations.get(key) if isinstance(configurations.get(key), dict) else {}
        raw_rule = (platform_block.get('rule') or config_block.get('rule') or '').strip()
        if raw_rule:
            files[_rule_file_path(key)] = raw_rule

    sigma_detection = None
    sigma_platform = platforms.get('sigma') if isinstance(platforms.get('sigma'), dict) else {}
    sigma_config = configurations.get('sigma') if isinstance(configurations.get('sigma'), dict) else {}
    sigma_rule = (sigma_platform.get('rule') or sigma_config.get('rule') or '').strip()
    if sigma_rule:
        files[_rule_file_path('sigma')] = sigma_rule
    elif sigma_platform.get('detection') is not None:
        sigma_detection = sigma_platform.get('detection')
    else:
        if sigma_rule:
            try:
                parsed_sigma = yaml.safe_load(sigma_rule)
                if isinstance(parsed_sigma, dict) and parsed_sigma.get('detection') is not None:
                    sigma_detection = parsed_sigma.get('detection')
            except Exception:
                sigma_detection = None

    if sigma_detection is not None:
        files[_rule_file_path('sigma')] = yaml.safe_dump(
            sigma_detection,
            sort_keys=False,
            allow_unicode=True,
        )

    return files


def _parse_uuid(value: str):
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _extract_comment_metadata(text: str, comment_prefixes=('#', '//')):
    """
    Scan comment lines for metadata fields: Rule name/title, Description, Author.
    Returns a dict with any found values (keys: title, description, author).
    """
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        for prefix in comment_prefixes:
            if stripped.startswith(prefix):
                inner = stripped[len(prefix):].strip()
                # Rule name: ... or title: ...
                m = re.match(r'^(?:rule\s*name|title)\s*[:=]\s*(.+)$', inner, re.IGNORECASE)
                if m and 'title' not in result:
                    result['title'] = m.group(1).strip()
                # Description: ...
                m = re.match(r'^description\s*[:=]\s*(.+)$', inner, re.IGNORECASE)
                if m and 'description' not in result:
                    result['description'] = m.group(1).strip()
                # Author: ...
                m = re.match(r'^author\s*[:=]\s*(.+)$', inner, re.IGNORECASE)
                if m and 'author' not in result:
                    result['author'] = m.group(1).strip()
                break
    return result


def parse_rule_by_format(content: str, fmt: str, fallback_author: str = ''):
    """
    Parse rule fields based on provided format.
    For KQL, extract a reasonable title and return content as-is.
    For WAZUH, parse XML to derive a title from <description> or <rule id=>.
    Returns a dict with keys: title, status, description, author, raw_content.
    Raises ValueError on fatal parse errors (e.g., malformed XML for Wazuh).
    """
    fmt = (fmt or 'KQL').upper()

    if fmt == 'SPL':
        text = content.strip()
        if not text:
            raise ValueError("Empty SPL content")
        # Extract metadata from comment lines (# prefix)
        meta = _extract_comment_metadata(text, comment_prefixes=('#',))
        title = meta.get('title')
        if not title:
            # Fallback: first non-comment line up to a pipe as a name seed
            seed_line = next(
                (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith('#')),
                '',
            )
            seed = re.split(r'\|', seed_line)[0].strip()
            title = seed[:80] or 'Untitled SPL Rule'
        return {
            'title': title,
            'status': 'experimental',
            'description': meta.get('description', ''),
            'author': meta.get('author', fallback_author or ''),
            'raw_content': content,
        }

    if fmt == 'KQL':
        text = content.strip()
        if not text:
            raise ValueError("Empty KQL content")
        # Extract metadata from comment lines (// and # prefixes)
        meta = _extract_comment_metadata(text, comment_prefixes=('//', '#'))
        title = meta.get('title')
        if not title:
            # Fallback: first non-comment line up to first pipe or semicolon
            seed_line = next(
                (ln.strip() for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith('//') and not ln.strip().startswith('#')),
                '',
            )
            seed = re.split(r"[|;]", seed_line)[0].strip()
            title = seed[:80] or 'Untitled KQL Rule'
        return {
            'title': title,
            'status': 'experimental',
            'description': meta.get('description', ''),
            'author': meta.get('author', fallback_author or ''),
            'raw_content': content,
        }

    if fmt == 'EQL':
        text = content.strip()
        if not text:
            raise ValueError("Empty EQL content")
        meta = _extract_comment_metadata(text, comment_prefixes=('//', '#'))
        title = meta.get('title')
        if not title:
            seed_line = next(
                (ln.strip() for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith('//') and not ln.strip().startswith('#')),
                '',
            )
            seed = re.split(r"[|;]", seed_line)[0].strip()
            title = seed[:80] or 'Untitled EQL Rule'
        return {
            'title': title,
            'status': 'experimental',
            'description': meta.get('description', ''),
            'author': meta.get('author', fallback_author or ''),
            'raw_content': content,
        }

    if fmt == 'AQL':
        text = content.strip()
        if not text:
            raise ValueError("Empty AQL content")
        meta = _extract_comment_metadata(text, comment_prefixes=('--', '#'))
        title = meta.get('title')
        if not title:
            seed_line = next(
                (ln.strip() for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith('--') and not ln.strip().startswith('#')),
                '',
            )
            seed = re.split(r"[|;]", seed_line)[0].strip()
            title = seed[:80] or 'Untitled AQL Rule'
        return {
            'title': title,
            'status': 'experimental',
            'description': meta.get('description', ''),
            'author': meta.get('author', fallback_author or ''),
            'raw_content': content,
        }

    if fmt == 'WAZUH':
        text = content.strip()
        if not text:
            raise ValueError("Empty Wazuh XML content")
        # Wazuh rules may have an XML comment metadata block before the <rule> element
        meta = _extract_comment_metadata(text, comment_prefixes=('#',))
        try:
            # Strip XML comments before parsing to find <rule>
            xml_text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL).strip()
            root = ElementTree.fromstring(xml_text)
            # Expect <rule> as root or within
            rule_el = root if root.tag.lower() == 'rule' else root.find('.//rule')
            if rule_el is None:
                raise ValueError("No <rule> element found in Wazuh XML")
            desc_el = rule_el.find('description')
            title = meta.get('title')
            description = meta.get('description', '')
            if not title:
                title = (desc_el.text.strip() if desc_el is not None and desc_el.text else None)
            if not description and desc_el is not None and desc_el.text:
                description = desc_el.text.strip()
            if not title:
                title = f"Wazuh Rule {rule_el.get('id') or ''}".strip()
                if not title:
                    title = 'Untitled Wazuh Rule'
            return {
                'title': title[:255],
                'status': 'experimental',
                'description': description,
                'author': meta.get('author', fallback_author or ''),
                'raw_content': content,
            }
        except ElementTree.ParseError as e:
            raise ValueError(f"Invalid Wazuh XML: {e}")

    # OTHER or unknown: accept as-is
    text = (content or '').strip()
    if not text:
        raise ValueError("Empty rule content")
    # Extract metadata from comment lines
    meta = _extract_comment_metadata(text, comment_prefixes=('#', '//'))
    title = meta.get('title')
    if not title:
        # Fallback: first non-comment, non-separator line
        title_line = next(
            (ln.strip() for ln in text.splitlines()
             if ln.strip()
             and not ln.strip().startswith('#')
             and not ln.strip().startswith('//')
             and not ln.strip().startswith('<!--')),
            '',
        )
        title = title_line[:80] or 'Untitled Rule'
    return {
        'title': title,
        'status': 'experimental',
        'description': meta.get('description', ''),
        'author': meta.get('author', fallback_author or ''),
        'raw_content': content,
    }


def detect_rule_format(content: str) -> str:
    """
    Best-effort heuristic to detect rule format from content.
    Returns one of: KQL, EQL, WAZUH, SPL, AQL, OTHER.
    """
    text = (content or '').strip()
    if not text:
        return 'OTHER'
    # Wazuh XML: starts with <rule> or contains <rule ...>
    if text.lower().startswith('<rule') or '<rule' in text.lower():
        try:
            ElementTree.fromstring(text)
            return 'WAZUH'
        except ElementTree.ParseError:
            # Still looks like XML; treat as WAZUH to surface XML errors upstream
            return 'WAZUH'
    # KQL heuristic: presence of operators like '| project' or 'datatable'
    lowered = text.lower()
    # EQL heuristic: sequence/where event-category syntax
    if (
        lowered.startswith('sequence')
        or lowered.startswith('any where')
        or lowered.startswith('process where')
        or lowered.startswith('file where')
        or '\nsequence ' in lowered
    ):
        return 'EQL'
    if '| project' in lowered or '| where' in lowered or 'datatable' in lowered:
        return 'KQL'
    # AQL heuristic: SQL-like query style used by QRadar
    if 'select ' in lowered and ' from ' in lowered:
        return 'AQL'
    # SPL heuristic: typical Splunk search keywords
    if 'index=' in lowered or 'sourcetype=' in lowered or '| stats ' in lowered or '| eval ' in lowered or '| table ' in lowered:
        return 'SPL'
    return 'OTHER'
