"""
MISP integration utilities for ADVOPS hunts.
Handles event creation and attribute pushing to MISP using PyMISP.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from django.conf import settings
from pymisp import PyMISP, MISPEvent, MISPAttribute, MISPGalaxyCluster

logger = logging.getLogger(__name__)


class MISPIntegrationError(Exception):
    """Base exception for MISP integration errors."""
    pass


class MISPClient:
    """Client for interacting with MISP API using PyMISP."""

    def __init__(self, url: Optional[str] = None, auth_key: Optional[str] = None, verify_ssl: Optional[bool] = None):
        # Allow per-instance credentials; fall back to global settings for backwards compat
        misp_url = url or getattr(settings, 'MISP_URL', '')
        misp_api_key = auth_key or getattr(settings, 'MISP_API_KEY', '')
        misp_verify_ssl = verify_ssl if verify_ssl is not None else getattr(settings, 'MISP_VERIFY_SSL', True)

        if not misp_url or not misp_api_key:
            raise MISPIntegrationError("MISP is not configured. Provide url and auth_key or set MISP_URL and MISP_API_KEY.")

        self.url = misp_url.rstrip('/')
        self.api_key = misp_api_key
        self.verify_ssl = misp_verify_ssl

        if not self.url or not self.api_key:
            raise MISPIntegrationError(f"MISP configuration incomplete: url={bool(self.url)}, api_key={bool(self.api_key)}")

        logger.info(f"Initializing PyMISP client: url={self.url}, verify_ssl={self.verify_ssl}")

        try:
            self.misp = PyMISP(self.url, self.api_key, ssl=self.verify_ssl)
            logger.info("PyMISP client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PyMISP client: {str(e)}")
            raise MISPIntegrationError(f"Failed to initialize MISP client: {str(e)}")

    def test_connection(self) -> bool:
        """Test connection to MISP server."""
        try:
            logger.info(f"Testing MISP connection to {self.url}")
            server_info = self.misp.server_settings()
            
            if isinstance(server_info, dict) and 'organisation' in server_info.get('response', {}):
                logger.info("MISP connection successful!")
                return True
            else:
                logger.warning(f"Unexpected MISP response: {server_info}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to MISP: {str(e)}", exc_info=True)
            raise MISPIntegrationError(f"Failed to connect to MISP: {str(e)}")

    def create_event(
        self,
        event_name: str,
        mitre_patterns: Optional[List[str]] = None,
        attributes: Optional[List[Dict[str, str]]] = None,
        pivot_summary: Optional[str] = None,
        verification_summary: Optional[str] = None,
        false_positive_analysis: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new event in MISP with optional attributes and galaxy clusters.
        """
        try:
            logger.info(f"Creating MISP event: {event_name}")
            
            # Use MISPEvent object to construct the event
            event = MISPEvent()
            event.info = event_name
            event.distribution = 3  # Community
            event.threat_level_id = 3  # Medium
            event.analysis = 0  # Initial
            event.published = False
            
            # Add attributes one by one using event.add_attribute
            if attributes:
                logger.info(f"Adding {len(attributes)} attributes to event")
                for attr in attributes:
                    event.add_attribute(
                        type=attr.get('type'),
                        value=attr.get('value'),
                        distribution=5
                    )
            
            if pivot_summary:
                event.add_attribute('comment', pivot_summary, comment='Pivot Summary', distribution=5)
            
            if verification_summary:
                event.add_attribute('comment', verification_summary, comment='Verification Summary', distribution=5)
            
            if false_positive_analysis:
                event.add_attribute('comment', false_positive_analysis, comment='False Positive Analysis', distribution=5)
            
            # Now push the fully constructed event object
            logger.info(f"Sending event creation request to MISP using add_event")
            
            # Use fallback serialization immediately to avoid "API Description" GET response
            try:
                # Force serialization to JSON string and back to dict
                raw_event_str = event.to_json() 
                raw_dict = json.loads(raw_event_str)
                
                # IMPORTANT: PyMISP/MISP API requires the 'Event' wrapper key.
                if 'Event' not in raw_dict:
                    raw_dict = {'Event': raw_dict}

                # CRITICAL FIX: Sanitize types and remove UUIDs to ensure cleaner creation
                if 'Event' in raw_dict:
                    evt = raw_dict['Event']
                    # Ensure integers for fields that might be stringified by PyMISP
                    for field in ['distribution', 'threat_level_id', 'analysis']:
                        if field in evt:
                            try:
                                evt[field] = int(evt[field])
                            except (ValueError, TypeError):
                                pass
                    
                    # Remove UUID to avoid potential conflicts; let MISP generate fresh ones
                    if 'uuid' in evt:
                        del evt['uuid']
                    
                    # Clean attributes
                    if 'Attribute' in evt:
                        for attr in evt['Attribute']:
                            # Remove UUIDs from attributes
                            if 'uuid' in attr:
                                del attr['uuid']
                            # Ensure distribution is int
                            if 'distribution' in attr:
                                try:
                                    attr['distribution'] = int(attr['distribution'])
                                except (ValueError, TypeError):
                                    pass

                logger.info(f"Payload prepared for MISP add_event (wrapped & sanitized): {list(raw_dict.keys())}")

                # PyMISP add_event can take the dict
                response = self.misp.add_event(raw_dict)
                
            except Exception as e:
                logger.error(f"Event serialization or send failed: {e}")
                raise MISPIntegrationError(f"Event serialization/send failed: {e}")
            
            # Check response
            if isinstance(response, dict):
                if 'Event' in response:
                    event_id = response['Event'].get('id')
                    if event_id:
                        logger.info(f"Successfully created MISP event with ID: {event_id}")
                        
                        # Add MITRE galaxies if provided
                        if mitre_patterns:
                            logger.info(f"Adding {len(mitre_patterns)} MITRE patterns to event {event_id}")
                            self._add_mitre_galaxies(event_id, mitre_patterns)
                        
                        return {
                            'success': True,
                            'event_id': event_id,
                            'message': f'Event {event_id} created successfully',
                        }
                elif 'name' in response and 'API description' in response.get('name', ''):
                    # Should be unreachable now if we serialize correctly, but keep safe
                    error_msg = f"MISP returned API documentation. Raw payload was: {raw_dict}"
                    logger.error(error_msg)
                    raise MISPIntegrationError(error_msg)
                elif 'errors' in response:
                    error_msg = f"MISP API error: {response['errors']}"
                    logger.error(error_msg)
                    raise MISPIntegrationError(error_msg)
            
            # If we get here, something went wrong
            error_msg = f"Failed to create event. Unexpected response: {response}"
            logger.error(error_msg)
            raise MISPIntegrationError(error_msg)
            
        except MISPIntegrationError:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error creating MISP event: {str(e)}")
            raise MISPIntegrationError(f"MISP integration failed: {str(e)}")

    def _add_mitre_galaxies(self, event_id: int, mitre_patterns: List[str]) -> None:
        """
        Add MITRE ATT&CK galaxy clusters to an event.
        
        Args:
            event_id: Event ID
            mitre_patterns: List of MITRE technique IDs (e.g., ["T1234"])
        """
        try:
            # Attempt to check if MITRE galaxy is available for debugging purposes, but do not block
            try:
                logger.info(f"Fetching MITRE galaxies from MISP (debug check)")
                galaxies = self.misp.galaxies()
                
                mitre_found = False
                if isinstance(galaxies, dict) and 'Galaxy' in galaxies:
                    for galaxy in galaxies.get('Galaxy', []):
                        if 'mitre' in galaxy.get('name', '').lower():
                            mitre_found = True
                            logger.info(f"Found MITRE galaxy: {galaxy.get('name', 'Unknown')} (ID: {galaxy.get('id')})")
                            break
                if not mitre_found:
                    logger.warning("Could not find a galaxy named '*mitre*' in MISP enabled galaxies. "
                                   "Will proceed to add clusters anyway, but they might fail if the galaxy is disabled.")
            except Exception as e:
                logger.warning(f"Galaxy check failed (non-fatal): {e}")

            # Add galaxy clusters for each MITRE pattern
            for pattern in mitre_patterns:
                try:
                    logger.info(f"Adding MITRE pattern {pattern} to event {event_id}")
                    # PyMISP galaxy cluster attachment
                    # Note: We rely on MISP resolving the value (T-code) to the correct galaxy cluster
                    cluster = MISPGalaxyCluster()
                    cluster.value = pattern
                    response = self.misp.add_galaxy_cluster(event_id, cluster)
                    
                    # Log response to help debug if it fails silently
                    if isinstance(response, dict) and 'errors' in response:
                        logger.error(f"Failed to add galaxy cluster {pattern}: {response['errors']}")
                    else:
                        logger.info(f"Add galaxy cluster response: {json.dumps(response) if isinstance(response, dict) else str(response)}")
                        
                except Exception as e:
                    logger.warning(f"Failed to add MITRE pattern {pattern}: {str(e)}")
                    
        except Exception as e:
            logger.exception(f"Failed to add MITRE galaxies to event {event_id}: {str(e)}")


def parse_infrastructure_summary(infrastructure_text: str) -> List[Dict[str, str]]:
    """
    Parse infrastructure summary text to extract structured attributes.
    
    Attempts to identify:
    - IP addresses (v4 and v6)
    - Domains
    - MD5, SHA1, SHA256 hashes
    - Email addresses
    
    Args:
        infrastructure_text: Raw text containing infrastructure details
        
    Returns:
        List of attribute dicts with 'type' and 'value' keys
    """
    attributes = []

    if not infrastructure_text:
        return attributes

    # Refang the text to handle common defanging techniques
    # Replace [.] and (.) with .
    cleaned_text = infrastructure_text.replace("[.]", ".").replace("(.)", ".")
    # Replace [:] with :
    cleaned_text = cleaned_text.replace("[:]", ":")
    # Replace hxxp with http
    cleaned_text = re.sub(r'\bhxxp', 'http', cleaned_text, flags=re.IGNORECASE)
    # Replace [dot] with .
    cleaned_text = cleaned_text.replace("[dot]", ".").replace("(dot)", ".")
    # Replace [at] with @
    cleaned_text = cleaned_text.replace("[at]", "@").replace("(at)", "@")

    # IP address patterns
    ipv4_pattern = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    ipv6_pattern = r'(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}'

    # Hash patterns
    md5_pattern = r'\b[a-fA-F0-9]{32}\b'
    sha1_pattern = r'\b[a-fA-F0-9]{40}\b'
    sha256_pattern = r'\b[a-fA-F0-9]{64}\b'

    # Domain pattern (simple)
    domain_pattern = r'\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b'

    # Email pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    # Extract IPs
    for match in re.finditer(ipv4_pattern, cleaned_text):
        ip = match.group()
        if ip not in [a['value'] for a in attributes]:
            attributes.append({'type': 'ip-dst', 'value': ip})

    # Extract hashes (SHA256 first to avoid partial matches)
    for match in re.finditer(sha256_pattern, cleaned_text):
        hash_val = match.group()
        if hash_val not in [a['value'] for a in attributes]:
            attributes.append({'type': 'sha256', 'value': hash_val})

    for match in re.finditer(sha1_pattern, cleaned_text):
        hash_val = match.group()
        if hash_val not in [a['value'] for a in attributes]:
            attributes.append({'type': 'sha1', 'value': hash_val})

    for match in re.finditer(md5_pattern, cleaned_text):
        hash_val = match.group()
        if hash_val not in [a['value'] for a in attributes]:
            attributes.append({'type': 'md5', 'value': hash_val})

    # Extract domains
    for match in re.finditer(domain_pattern, cleaned_text):
        domain = match.group().lower()
        if domain not in [a['value'] for a in attributes]:
            attributes.append({'type': 'domain', 'value': domain})

    # Extract emails
    for match in re.finditer(email_pattern, cleaned_text):
        email = match.group()
        if email not in [a['value'] for a in attributes]:
            attributes.append({'type': 'email-src', 'value': email})

    return attributes


def extract_mitre_techniques(mitre_text: str) -> List[str]:
    """
    Extract MITRE ATT&CK technique IDs from text.
    
    Looks for patterns like T1234, T12.345, etc.
    
    Args:
        mitre_text: Raw text containing MITRE mappings
        
    Returns:
        List of MITRE technique IDs
    """
    pattern = r'\b(T\d{4}(?:\.\d{3})?)\b'
    matches = re.findall(pattern, mitre_text)
    return list(set(matches))  # Remove duplicates
