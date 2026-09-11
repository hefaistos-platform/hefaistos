import os
import time
import logging
import json
import requests
from pymisp import PyMISP
from datetime import datetime

# --- Import the SDK Client ---
from hefaistos_sdk.client import HefaistosApiClient, get_secret

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Read Configuration from Environment ---
MISP_URL = os.environ.get('MISP_URL')
MISP_API_KEY = get_secret('misp_key', 'MISP_API_KEY')
# SSL verification for MISP requests (defaults to False if not set)
_verify_str = os.environ.get('MISP_VERIFY_SSL', 'false').strip().lower()
MISP_VERIFY_SSL = _verify_str in ('1', 'true', 'yes', 'y')
PULL_INTERVAL_SECONDS = int(os.environ.get('PULL_INTERVAL_SECONDS', 3600))

PROCESSED_EVENTS_CACHE_FILE = 'processed_events.txt'


def convert_event_to_stix(event: dict):
    """Optional: convert a MISP event dict to a minimal STIX 2.1-like structure.
    Placeholder for Phase 2; returns a dict suitable for future normalization.
    """
    try:
        obj = {
            "type": "bundle",
            "spec_version": "2.1",
            "id": f"bundle--{event.get('uuid', 'unknown')}",
            "objects": []
        }
        # Example indicator extraction from attributes
        for attr in (event.get('Attribute') or []):
            ind_type = attr.get('type')
            value = attr.get('value')
            if not value:
                continue
            indicator = {
                "type": "indicator",
                "id": f"indicator--{attr.get('uuid', event.get('uuid', 'unknown'))}",
                "pattern": f"[{ind_type} = '{value}']",
                "valid_from": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            obj["objects"].append(indicator)
        return obj
    except Exception:
        return None


def load_processed_events():
    """Loads the set of processed event UUIDs from a file."""
    if not os.path.exists(PROCESSED_EVENTS_CACHE_FILE):
        return set()
    try:
        with open(PROCESSED_EVENTS_CACHE_FILE, 'r') as f:
            return set(line.strip() for line in f)
    except Exception as e:
        logging.error(f"Could not load cache file: {e}")
        return set()

def save_processed_event(event_uuid):
    """Appends a new event UUID to the cache file."""
    try:
        with open(PROCESSED_EVENTS_CACHE_FILE, 'a') as f:
            f.write(f"{event_uuid}\n")
    except Exception as e:
        logging.error(f"Could not write to cache file: {e}")


# --- REMOVED THE call_hefaistos_api FUNCTION ---
# The SDK's HefaistosApiClient (self.api_client) replaces this.


def process_misp_event(event, api_client, attack_map):
    """
    Parses a MISP event and creates a new v2 PLAYBOOK GRAPH.
    """
    try:
        event_id = event.get('id')
        event_uuid = event.get('uuid')
        event_info = event.get('info')

        # --- 1. Create the new PlaybookGraph (the canvas) ---
        graph_title = f"[MISP-{event_id}] {event_info}"
        logger.info(f"Creating new graph: '{graph_title}'")

        graph_response = api_client.create_playbook_graph(title=graph_title)

        if graph_response is None:
            logging.error(f"Failed to create graph for MISP event {event_id}.")
            return False

        new_graph_id = graph_response.get('createPlaybookGraph', {}).get('playbookGraph', {}).get('id')
        if not new_graph_id:
            logging.error("API call succeeded but no graph ID was returned.")
            return False

        logger.info(f"Successfully created graph {new_graph_id}")

        # --- 2. Create the first Node on the graph ---
        node_response = api_client.create_playbook_node(new_graph_id, "MISP Event Details")
        if node_response is None:
            logging.error(f"Failed to create node for graph {new_graph_id}.")
            return False

        new_node_id = node_response.get('createPlaybookNode', {}).get('node', {}).get('id')
        if not new_node_id:
            logging.error("API call succeeded but no node ID was returned.")
            return False

        logger.info(f"Successfully created node {new_node_id} on graph {new_graph_id}")

        # --- 3. Find and map TTPs ---
        # A) Attributes of type 'mitre-attack-pattern'
        misp_ttps = {attr.get("value") for attr in event.get("Attribute", []) if attr.get("type") == "mitre-attack-pattern" and attr.get("value")}
        # B) Galaxy clusters (prefer external_id which holds 'Txxxx')
        for g in (event.get("Galaxy") or []):
            typ = (g.get('type') or '') + ' ' + (g.get('namespace') or '')
            if 'mitre-attack' in typ.lower():
                for cl in (g.get("GalaxyCluster") or []):
                    meta = cl.get('meta') or {}
                    ext_id = meta.get('external_id')
                    if ext_id and isinstance(ext_id, str) and ext_id.startswith('T'):
                        misp_ttps.add(ext_id)
        hefaistos_ttp_ids = [attack_map[ttp] for ttp in misp_ttps if ttp in attack_map]

        # --- 4. Build the dcg420 Template JSON ---
        template_data = {
            "goal": f"Hunt for activity related to MISP Event {event_id}: {event_info}",
            "categorization": {
                "mitreAttackTechnique": ", ".join(misp_ttps) or "See Mappings"
            },
            "technicalContext": f"This hunt was generated from threat intelligence. See the MISP event for full details and IoCs.\n\n**MISP UUID:** {event_uuid}\n**MISP Link:** {MISP_URL}/events/view/{event_id}",
            "priority": "Medium",
            "v1_hypothesis": f"An adversary is leveraging TTPs from MISP event {event_id}."
        }

        # --- 5. Update the Node with the Template Data ---
        logger.info(f"Updating node {new_node_id} with template data and {len(hefaistos_ttp_ids)} TTPs.")
        update_response = api_client.update_node_template(
            node_id=new_node_id,
            template_data_dict=template_data,
            attack_ids=hefaistos_ttp_ids
        )

        if update_response is None:
            logging.error(f"Failed to update node template for {new_node_id}.")
            return False

        # --- 6. Populate the Workbench sections (Strategy, Context, Testing, SOAR) ---
        # Extract IoCs from attributes
        attrs = event.get("Attribute") or []
        iocs = {
            "ips": [a.get("value") for a in attrs if a.get("type") in ("ip-src","ip-dst","ip-src|port","ip-dst|port") and a.get("value")],
            "domains": [a.get("value") for a in attrs if a.get("type") in ("domain","hostname","fqdn") and a.get("value")],
            "urls": [a.get("value") for a in attrs if a.get("type") in ("url","uri") and a.get("value")],
            "hashes": [a.get("value") for a in attrs if a.get("type") in ("md5","sha1","sha256") and a.get("value")],
            "emails": [a.get("value") for a in attrs if a.get("type") in ("email-src","email-dst") and a.get("value")],
        }

        # Build selectedStrategy payload
        selected_strategy = {
            "source": "MISP",
            "eventId": event_id,
            "eventUuid": event_uuid,
            "iocs": iocs,
            "linkedRuleIds": []
        }

        # Context text including IoCs
        ioc_summary_lines = []
        for k, v in iocs.items():
            if v:
                ioc_summary_lines.append(f"- {k}: {', '.join(v[:10])}{' ...' if len(v) > 10 else ''}")
        ioc_summary = "\n".join(ioc_summary_lines) if ioc_summary_lines else "(no IoCs extracted)"

        technical_context = (
            f"Event Source: MISP\nEvent UUID: {event_uuid}\nEvent Link: {MISP_URL}/events/view/{event_id}\n\n"
            f"IoC Summary:\n{ioc_summary}"
        )

        triage_guidance = (
            "1) Correlate IoCs across last 24h in SIEM.\n"
            "2) Pivot on processes, parent-child, and network connections.\n"
            "3) Confirm ATT&CK technique behavior via telemetry."
        )

        test_scenario = "Inject a benign sample event with matching IoCs to validate detection pipeline triggers without causing containment."
        test_expected_output = "Detection rule flags test events; SOAR enrichment retrieves context; no automated containment triggered."

        # SOAR default steps
        enrichment_steps = [
            {"action": "ip-reputation", "input": {"ips": iocs["ips"][:5]}, "description": "Query threat intel for IPs"},
            {"action": "dns-resolve", "input": {"domains": iocs["domains"][:5]}, "description": "Resolve domains and fetch WHOIS"}
        ]
        containment_steps = []
        notification_steps = [
            {"channel": "SOC", "recipient": "tier1", "template": f"New MISP-derived hunt: {event_info}"}
        ]

        # Choose a primary technique if available
        primary_tech = next(iter(misp_ttps), None)

        api_client.update_playbook_details(
            graphId=new_graph_id,
            mitreTechniqueId=primary_tech,
            selectedStrategy=selected_strategy,
            goal=template_data["goal"],
            technicalContext=technical_context,
            triageGuidance=triage_guidance,
            falsePositives="",
            responsePlaybook="",
            alertTrigger="Triggered by matching IoCs / technique behavior",
            defaultSeverity="MEDIUM",
            enrichmentSteps=enrichment_steps,
            containmentSteps=containment_steps,
            notificationSteps=notification_steps,
            testScenario=test_scenario,
            testExpectedOutput=test_expected_output,
            tags=["MISP","ThreatIntel"]
        )

        logging.info(f"Successfully processed MISP event {event_id}.")
        return True

    except Exception as e:
        logging.error(f"Error processing MISP event {event_id}: {e}", exc_info=True)
        return False


def _has_mitre_attack_galaxy(ev: dict) -> bool:
    """Returns True if the event contains any Galaxy clusters from MITRE ATT&CK."""
    galaxies = ev.get('Galaxy') or []
    for g in galaxies:
        typ = (g.get('type') or '') + ' ' + (g.get('namespace') or '')
        if 'mitre-attack' in typ.lower():
            clusters = g.get('GalaxyCluster') or []
            if clusters:
                return True
    return False

def fetch_threat_intel(api_client, processed_events_cache, attack_map):
    """
    Fetches new published events from MISP using PyMISP and filters to those
    that contain MITRE ATT&CK galaxy clusters.
    """
    logging.info("Checking for new threat intel...")

    try:
        misp = PyMISP(MISP_URL, MISP_API_KEY, MISP_VERIFY_SSL)
    except Exception as e:
        logging.error(f"PyMISP initialization failed: {e}")
        return 0

    # Use search_index first (lightweight), then fetch full events
    events = []
    try:
        # Compute publish timestamp cutoff (now - interval - small cushion)
        cutoff = int(time.time() - (PULL_INTERVAL_SECONDS + 60))
        # search() with pythonify=False returns raw JSON
        res = misp.search(
            controller='events',
            return_format='json',
            published=True,
            publish_timestamp=cutoff,
            limit=100,
            pythonify=False
        )
        # Extract events from response
        if isinstance(res, dict) and 'response' in res:
            events_raw = res['response']
        elif isinstance(res, list):
            events_raw = res
        else:
            events_raw = []
        # Normalize: each item might be {'Event': {...}} or direct event dict
        events = [e.get('Event', e) if isinstance(e, dict) else e for e in events_raw]
    except Exception as e:
        logging.warning(f"Publish-timestamp search failed ({e}); falling back to published-only")
        try:
            res = misp.search(
                controller='events',
                return_format='json',
                published=True,
                limit=100,
                pythonify=False
            )
            if isinstance(res, dict) and 'response' in res:
                events_raw = res['response']
            elif isinstance(res, list):
                events_raw = res
            else:
                events_raw = []
            events = [e.get('Event', e) if isinstance(e, dict) else e for e in events_raw]
        except Exception as e2:
            logging.error(f"Failed to query MISP via PyMISP: {e2}")
            return 0

    if not events:
        logging.info("No new events found.")
        return 0

    # Filter: only published and with MITRE ATT&CK galaxies
    filtered = []
    for ev in events:
        # Ensure we have a dict for the event body
        evt = ev.get('Event') if isinstance(ev, dict) and 'Event' in ev else ev
        if not isinstance(evt, dict):
            continue
        # Published flag can be int/bool/string
        pub = evt.get('published')
        is_published = bool(pub) and str(pub) not in ('0', 'False', 'false', '')
        if not is_published:
            continue
        if not _has_mitre_attack_galaxy(evt):
            continue
        filtered.append(evt)

    if not filtered:
        logging.info("No events matched: published + MITRE ATT&CK galaxy.")
        return 0

    logging.info(f"Found {len(filtered)} eligible events from MISP (published + ATT&CK galaxy).")
    new_event_count = 0

    for event in filtered:
        event_uuid = event.get('uuid')
        if not event_uuid:
            continue

        if event_uuid in processed_events_cache:
            continue

        logging.info(f"Found new unprocessed event: '{event.get('info')}'")

        # --- Pass api_client and attack_map to the processor ---
        success = process_misp_event(event, api_client, attack_map)

        if success:
            new_event_count += 1
            processed_events_cache.add(event_uuid)
            save_processed_event(event_uuid)

    logging.info("Intel check complete.")
    return new_event_count


def main():
    logging.info("--- HEFAISTOS Threat Intel Connector (SDK v1.0) ---")

    api_url = os.environ.get('HEFAISTOS_API_URL')
    direct_token = os.environ.get('HEFAISTOS_API_TOKEN')
    token_file = os.environ.get('HEFAISTOS_API_TOKEN_FILE')
    token_file_exists = token_file and os.path.isfile(token_file)

    if not MISP_URL:
        logging.critical("CRITICAL: MISP_URL is not set. Connector will not run.")
        return
    if not api_url:
        logging.critical("CRITICAL: HEFAISTOS_API_URL is not set. Connector will not run.")
        return
    if not direct_token:
        # Poll for token file if direct token absent
        if token_file:
            logging.info(f"No direct token; waiting for token file '{token_file}'...")
            for attempt in range(30):  # ~60s total (30 * 2s)
                if os.path.isfile(token_file) and os.path.getsize(token_file) > 0:
                    logging.info(f"Token file detected on attempt {attempt+1}.")
                    token_file_exists = True
                    break
                time.sleep(2)
            if not token_file_exists:
                logging.critical("CRITICAL: Token file never appeared; aborting startup.")
                logging.error(f"Checked token file path: {token_file or 'None'} (exists=False)")
                return
        else:
            logging.critical("CRITICAL: No HEFAISTOS_API_TOKEN and no HEFAISTOS_API_TOKEN_FILE path provided.")
            return

    logging.info(f"--- Polling {MISP_URL} every {PULL_INTERVAL_SECONDS} seconds ---")

    try:
        # --- Initialize the SDK Client ---
        api_client = HefaistosApiClient()

        # Retry loop for initial connection
        for i in range(10):
            try:
                # Fetch the ATT&CK Map using the SDK
                logging.info(f"Fetching HEFAISTOS ATT&CK TTP map (Attempt {i+1}/10)...")
                attack_data = api_client.get_attack_map()
                if attack_data is not None:
                    break # Success
            except Exception as e:
                logging.warning(f"Connection attempt {i+1} failed: {e}")
            
            time.sleep(5)
        else:
            logging.critical("Could not fetch ATT&CK map from HEFAISTOS API after 10 attempts. Exiting.")
            return

        attack_map = {tech['techniqueId']: tech['id'] for tech in attack_data.get('allAttackTechniques', [])}
        logging.info(f"Successfully loaded {len(attack_map)} ATT&CK techniques.")

    except Exception as e:
        logging.critical(f"Failed to initialize SDK or ATT&CK map: {e}")
        return

    processed_events = load_processed_events()
    logging.info(f"Loaded {len(processed_events)} processed events from cache.")

    try:
        while True:
            new_event_count = fetch_threat_intel(api_client, processed_events, attack_map)

            if new_event_count > 0:
                logging.info(f"Successfully processed {new_event_count} new events.")

            logging.info(f"Sleeping for {PULL_INTERVAL_SECONDS} seconds...")
            time.sleep(PULL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logging.info("Connector shutting down.")


if __name__ == '__main__':
    main()