import requests
import csv
import io
import re

import rdflib
from rdflib.namespace import RDF, RDFS, OWL

from django.core.management.base import BaseCommand
from django.db import transaction
from platform_data.models import (
    D3fendDefensiveTechnique,
    D3fendDigitalArtifact,
    D3fendAttackMapping,
    MitreAttackTechnique,
    PlatformDataVersion,
)

D3FEND_ONTOLOGY_URL = "https://d3fend.mitre.org/ontologies/d3fend.owl"
D3FEND_MAPPINGS_CSV_URL = "https://d3fend.mitre.org/api/ontology/inference/d3fend-full-mappings.csv"

# Complete D3FEND technique to tactic mappings
# Based on official D3FEND taxonomy: https://d3fend.mitre.org/
D3FEND_TACTIC_MAPPINGS = {
    # ===== DETECT (81+ techniques) =====
    'D3-DA': 'Detect',      # Detection Analytics
    'D3-NTA': 'Detect',     # Network Traffic Analysis
    'D3-PA': 'Detect',      # Process Analysis
    'D3-PSA': 'Detect',     # Process Spawn Analysis
    'D3-PLA': 'Detect',     # Process Lineage Analysis
    'D3-FA': 'Detect',      # File Analysis
    'D3-FCA': 'Detect',     # File Content Analysis
    'D3-FHA': 'Detect',     # File Hash Analysis
    'D3-UBA': 'Detect',     # User Behavior Analysis
    'D3-PM': 'Detect',      # Platform Monitoring
    'D3-APM': 'Detect',     # Application Performance Monitoring
    'D3-MA': 'Detect',      # Message Analysis
    'D3-IAA': 'Detect',     # Identifier Analysis
    'D3-CA': 'Detect',      # Certificate Analysis
    'D3-DNA': 'Detect',     # Domain Name Analysis
    'D3-UA': 'Detect',      # URL Analysis
    'D3-SDA': 'Detect',     # System Daemon Analysis
    'D3-DNSA': 'Detect',    # DNS Analysis
    'D3-PHDURA': 'Detect',  # Per Host Download-Upload Ratio Analysis
    'D3-NTPM': 'Detect',    # Network Traffic Policy Mapping
    'D3-RTSD': 'Detect',    # Remote Terminal Session Detection
    'D3-CSPP': 'Detect',    # Client-server Payload Profiling
    'D3-UGLPA': 'Detect',   # User Geolocation Logon Pattern Analysis
    'D3-ISVA': 'Detect',    # Inbound Session Volume Analysis
    'D3-PSSA': 'Detect',    # Protocol State Signature Analysis
    'D3-RPA': 'Detect',     # Relay Pattern Analysis
    'D3-SMRA': 'Detect',    # Sender MTA Reputation Analysis
    'D3-SRA': 'Detect',     # Sender Reputation Analysis
    'D3-FAPA': 'Detect',    # File Access Pattern Analysis
    'D3-FCOA': 'Detect',    # File Content Analysis
    'D3-LFP': 'Detect',     # Local File Permissions
    'D3-WSAA': 'Detect',    # Web Session Activity Analysis
    'D3-JFAPA': 'Detect',   # Job Function Access Pattern Analysis
    'D3-RAPA': 'Detect',    # Resource Access Pattern Analysis
    'D3-SAPA': 'Detect',    # Session Activity Pattern Analysis
    'D3-UDTA': 'Detect',    # User Data Transfer Analysis
    'D3-AEM': 'Detect',     # Application Exception Monitoring
    'D3-SDM': 'Detect',     # System Daemon Monitoring
    'D3-FIM': 'Detect',     # File Integrity Monitoring
    'D3-DQSA': 'Detect',    # Database Query String Analysis
    'D3-ANAA': 'Detect',    # Administrative Network Activity Analysis
    'D3-ANET': 'Detect',    # Authentication Event Thresholding
    'D3-APCA': 'Detect',    # Application Protocol Command Analysis
    'D3-IPCTA': 'Detect',   # IPC Traffic Analysis
    'D3-NTCD': 'Detect',    # Network Traffic Community Deviation
    'D3-PMAD': 'Detect',    # Protocol Metadata Anomaly Detection
    'D3-RTA': 'Detect',     # RPC Traffic Analysis
    'D3-CIA': 'Detect',     # Container Image Analysis
    'D3-DNRA': 'Detect',    # Domain Name Reputation Analysis
    'D3-DLV': 'Detect',     # Domain Logic Validation
    'D3-ELM': 'Detect',     # Electronic Lock Monitoring
    'D3-FCDC': 'Detect',    # File Content Decompression Checking
    'D3-FFV': 'Detect',     # File Format Verification
    'D3-FHRA': 'Detect',    # File Hash Reputation Analysis
    'D3-FISV': 'Detect',    # File Internal Structure Verification
    'D3-FMBV': 'Detect',    # File Magic Byte Verification
    'D3-FMCV': 'Detect',    # File Metadata Consistency Validation
    'D3-FMVV': 'Detect',    # File Metadata Value Verification
    'D3-HD': 'Detect',      # Homoglyph Detection
    'D3-ID': 'Detect',      # Identifier Analysis
    'D3-IPRA': 'Detect',    # IP Reputation Analysis
    'D3-IRA': 'Detect',     # Identifier Reputation Analysis
    'D3-MSM': 'Detect',     # Motion Sensor Monitoring
    'D3-OLV': 'Detect',     # Operational Logic Validation
    'D3-PHAM': 'Detect',    # Physical Access Monitoring
    'D3-PSM': 'Detect',     # Proximity Sensor Monitoring
    'D3-URA': 'Detect',     # URL Reputation Analysis
    'D3-VS': 'Detect',      # Video Surveillance
    'D3-ACA': 'Detect',     # Active Certificate Analysis
    'D3-PCA': 'Detect',     # Passive Certificate Analysis
    'D3-DNSAL': 'Detect',   # DNS Allowlisting
    'D3-DNSAM': 'Detect',   # DNS Analysis Monitoring
    'D3-DNSBL': 'Detect',   # DNS Denylisting
    'D3-DNSDL': 'Detect',   # DNS Domain Lookup
    'D3-HRDM': 'Detect',    # Hardware Diagnostics Monitoring
    'D3-IDA': 'Detect',     # Input Device Analysis
    'D3-KDET': 'Detect',    # Kernel API Detection
    'D3-MAC': 'Detect',     # Memory Access Control
    'D3-SYMA': 'Detect',    # System Monitoring Analysis

    # ===== HARDEN (50+ techniques) =====
    'D3-AH': 'Harden',      # Application Hardening
    'D3-ACH': 'Harden',     # Application Configuration Hardening
    'D3-DLIC': 'Harden',    # Dead Code Elimination
    'D3-EHPV': 'Harden',    # Exception Handler Pointer Validation
    'D3-PSEP': 'Harden',    # Process Segment Execution Prevention
    'D3-SAOR': 'Harden',    # Segment Address Offset Randomization
    'D3-SCF': 'Harden',     # Stack Frame Canary Validation
    'D3-SCP': 'Harden',     # System Call Filtering
    'D3-CH': 'Harden',      # Credential Hardening
    'D3-BAN': 'Harden',     # Biometric Authentication
    'D3-CBAN': 'Harden',    # Certificate-based Authentication
    'D3-DENCR': 'Harden',   # Disk Encryption
    'D3-FENCR': 'Harden',   # File Encryption
    'D3-MFA': 'Harden',     # Multi-factor Authentication
    'D3-OTP': 'Harden',     # One-time Password
    'D3-SPP': 'Harden',     # Strong Password Policy
    'D3-TAAN': 'Harden',    # TPM-based Authentication
    'D3-MH': 'Harden',      # Message Hardening
    'D3-MENCR': 'Harden',   # Message Encryption
    'D3-PH': 'Harden',      # Platform Hardening
    'D3-FV': 'Harden',      # Firmware Verification
    'D3-RRID': 'Harden',    # RF Shielding
    'D3-SBV': 'Harden',     # Secure Boot Verification
    'D3-SU': 'Harden',      # Software Update
    'D3-TBI': 'Harden',     # TPM Boot Integrity
    'D3-SH': 'Harden',      # Service Hardening
    'D3-AA': 'Harden',      # Agent Authentication
    'D3-AMED': 'Harden',    # Access Mediation
    'D3-APA': 'Harden',     # Access Policy Administration
    'D3-UAP': 'Harden',     # User Account Permissions
    'D3-CTS': 'Harden',     # Credential Transmission Scoping
    'D3-DKP': 'Harden',     # Disk Partitioning
    'D3-EBWSAM': 'Harden',  # Endpoint-based Web Server Access Mediation
    'D3-EPL': 'Harden',     # Physical Locking
    'D3-IOPR': 'Harden',    # IO Port Restriction
    'D3-IRV': 'Harden',     # Integer Range Validation
    'D3-LAMED': 'Harden',   # LAN Access Mediation
    'D3-LFAM': 'Harden',    # Local File Access Mediation
    'D3-MBSV': 'Harden',    # Memory Block Start Validation
    'D3-NAM': 'Harden',     # Network Access Mediation
    'D3-NPC': 'Harden',     # Null Pointer Checking
    'D3-NRAM': 'Harden',    # Network Resource Access Mediation
    'D3-OPR': 'Harden',     # Operating Mode Restriction
    'D3-OVAR': 'Harden',    # OT Variable Access Restriction
    'D3-PAM': 'Harden',     # Physical Access Mediation
    'D3-PBWSAM': 'Harden',  # Proxy-based Web Server Access Mediation
    'D3-PV': 'Harden',      # Pointer Validation
    'D3-PWA': 'Harden',     # Password Authentication
    'D3-RAM': 'Harden',     # Routing Access Mediation
    'D3-RFAM': 'Harden',    # Remote File Access Mediation
    'D3-SCH': 'Harden',     # Source Code Hardening
    'D3-TBA': 'Harden',     # Token-based Authentication
    'D3-TL': 'Harden',      # Trusted Library
    'D3-VI': 'Harden',      # Variable Initialization
    'D3-VTV': 'Harden',     # Variable Type Validation
    'D3-WSAM': 'Harden',    # Web Session Access Mediation

    # ===== ISOLATE (25+ techniques) =====
    'D3-EI': 'Isolate',     # Execution Isolation
    'D3-ABPI': 'Isolate',   # Application-based Process Isolation
    'D3-HBPI': 'Isolate',   # Hardware-based Process Isolation
    'D3-NI': 'Isolate',     # Network Isolation
    'D3-BDI': 'Isolate',    # Broadcast Domain Isolation
    'D3-DNI': 'Isolate',    # DNS Isolation
    'D3-EDL': 'Isolate',    # Encrypted Domain List
    'D3-FWR': 'Isolate',    # Forward Resolution Domain Denylisting
    'D3-NTF': 'Isolate',    # Network Traffic Filtering
    'D3-ITF': 'Isolate',    # Inbound Traffic Filtering
    'D3-OTF': 'Isolate',    # Outbound Traffic Filtering
    'D3-CF': 'Isolate',     # Content Filtering
    'D3-EF': 'Isolate',     # Email Filtering
    'D3-HIPS': 'Isolate',   # Host-based IPS
    'D3-NIPS': 'Isolate',   # Network-based IPS
    'D3-RDI': 'Isolate',    # Reverse Resolution IP Denylisting
    'D3-CFC': 'Isolate',    # Content Format Conversion
    'D3-CM': 'Isolate',     # Content Modification
    'D3-CNE': 'Isolate',    # Content Excision
    'D3-CNR': 'Isolate',    # Content Rebuild
    'D3-CNS': 'Isolate',    # Content Substitution
    'D3-CQ': 'Isolate',     # Content Quarantine
    'D3-CV': 'Isolate',     # Content Validation

    # ===== DECEIVE (12+ techniques) =====
    'D3-DE': 'Deceive',     # Decoy Environment
    'D3-CHN': 'Deceive',    # Connected Honeynet
    'D3-IHN': 'Deceive',    # Integrated Honeynet
    'D3-SHN': 'Deceive',    # Standalone Honeynet
    'D3-DCR': 'Deceive',    # Decoy Content
    'D3-DNR': 'Deceive',    # Decoy Network Resource
    'D3-DPR': 'Deceive',    # Decoy Persona
    'D3-DUC': 'Deceive',    # Decoy User Credential
    'D3-DF': 'Deceive',     # Decoy File
    'D3-DO': 'Deceive',     # Decoy Object
    'D3-DTP': 'Deceive',    # Decoy Treasure

    # ===== EVICT (25+ techniques) =====
    'D3-CE': 'Evict',       # Credential Eviction
    'D3-AL': 'Evict',       # Account Locking
    'D3-ANCI': 'Evict',     # Authentication Cache Invalidation
    'D3-CR': 'Evict',       # Credential Revocation
    'D3-CRO': 'Evict',      # Credential Rotation
    'D3-FE': 'Evict',       # File Eviction
    'D3-FR': 'Evict',       # File Removal
    'D3-PE': 'Evict',       # Process Eviction
    'D3-PS': 'Evict',       # Process Suspension
    'D3-PT': 'Evict',       # Process Termination
    'D3-CS': 'Evict',       # Credential Scrubbing
    'D3-DKE': 'Evict',      # Disk Erasure
    'D3-DKF': 'Evict',      # Disk Formatting
    'D3-DNSCE': 'Evict',    # DNS Cache Eviction
    'D3-DRT': 'Evict',      # Domain Registration Takedown
    'D3-ER': 'Evict',       # Email Removal
    'D3-FEV': 'Evict',      # File Eviction
    'D3-OE': 'Evict',       # Object Eviction
    'D3-RKD': 'Evict',      # Registry Key Deletion
    'D3-RN': 'Evict',       # Reference Nullification
    'D3-RA': 'Evict',       # Restore Access
    'D3-RC': 'Evict',       # Restore Configuration
    'D3-RD': 'Evict',       # Restore Database
    'D3-RE': 'Evict',       # Restore Email
    'D3-RF': 'Evict',       # Restore File
    'D3-RIC': 'Evict',      # Reissue Credential
    'D3-RNA': 'Evict',      # Restore Network Access
    'D3-RO': 'Evict',       # Restore Object
    'D3-RS': 'Evict',       # Restore Software
    'D3-RUAA': 'Evict',     # Restore User Account Access
    'D3-ULA': 'Evict',      # Unlock Account

    # ===== MODEL (25+ techniques) =====
    'D3-AI': 'Model',       # Asset Inventory
    'D3-AVE': 'Model',      # Asset Vulnerability Enumeration
    'D3-CI': 'Model',       # Configuration Inventory
    'D3-DAIE': 'Model',     # Data Asset Inventory Enumeration
    'D3-HCI': 'Model',      # Hardware Component Inventory
    'D3-SCI': 'Model',      # Software Component Inventory
    'D3-OAM': 'Model',      # Operational Activity Mapping
    'D3-AM': 'Model',       # Access Modeling
    'D3-ORA': 'Model',      # Operational Risk Assessment
    'D3-SYSM': 'Model',     # System Mapping
    'D3-ALLM': 'Model',     # Active Logical Link Mapping
    'D3-APLM': 'Model',     # Active Physical Link Mapping
    'D3-DEM': 'Model',      # Data Exchange Mapping
    'D3-NVA': 'Model',      # Network Vulnerability Assessment
    'D3-PLLM': 'Model',     # Passive Logical Link Mapping
    'D3-PPLM': 'Model',     # Passive Physical Link Mapping
    'D3-SVCDM': 'Model',    # Service Dependency Mapping
    'D3-SYSDM': 'Model',    # System Dependency Mapping
    'D3-LLM': 'Model',      # Logical Link Mapping
    'D3-PLM': 'Model',      # Physical Link Mapping
    'D3-ARMA': 'Model',     # ARMA Model
    'D3-DI': 'Model',       # Data Inventory
    'D3-DPLM': 'Model',     # Direct Physical Link Mapping
    'D3-NM': 'Model',       # Network Mapping
    'D3-NNI': 'Model',      # Network Node Inventory
    'D3-SWI': 'Model',      # Software Inventory
}

# Known D3FEND tactic root techniques (kept for backwards compatibility)
# These are the top-level categories under each tactic
TACTIC_ROOTS = {
    # Detect tactic roots
    'NetworkTrafficAnalysis': 'Detect',
    'ProcessAnalysis': 'Detect', 
    'FileAnalysis': 'Detect',
    'UserBehaviorAnalysis': 'Detect',
    'PlatformMonitoring': 'Detect',
    'IdentifierAnalysis': 'Detect',
    'MessageAnalysis': 'Detect',
    
    # Harden tactic roots
    'ApplicationHardening': 'Harden',
    'CredentialHardening': 'Harden',
    'MessageHardening': 'Harden',
    'PlatformHardening': 'Harden',
    
    # Isolate tactic roots
    'ExecutionIsolation': 'Isolate',
    'NetworkIsolation': 'Isolate',
    
    # Deceive tactic roots
    'DecoyObject': 'Deceive',
    'DecoyEnvironment': 'Deceive',
    
    # Evict tactic roots
    'CredentialEviction': 'Evict',
    'FileEviction': 'Evict',
    'ProcessEviction': 'Evict',
    
    # Model tactic roots
    'AssetInventory': 'Model',
    'OperationalActivityMapping': 'Model',
    'SystemMapping': 'Model',
}

# Direct technique to tactic mappings for techniques without clear hierarchy (kept for backwards compatibility)
DIRECT_TACTIC_MAPPINGS = D3FEND_TACTIC_MAPPINGS


class Command(BaseCommand):
    help = 'Imports D3FEND ontology and ATT&CK mappings'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-ontology',
            action='store_true',
            help='Skip ontology import, only import mappings'
        )
        parser.add_argument(
            '--skip-mappings',
            action='store_true',
            help='Skip mappings import, only import ontology'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed debug output'
        )

    def handle(self, *args, **options):
        self.verbose = options.get('verbose', False)

        if not options['skip_ontology']:
            self.import_ontology()
            self.assign_tactics()

        if not options['skip_mappings']:
            self.import_mappings()

        # Record the D3FEND import timestamp/version ("live" since we pull from the
        # official ontology endpoint, so version is recorded as the import date).
        PlatformDataVersion.objects.update_or_create(
            framework='d3fend',
            defaults={'version': 'live'},
        )

        self.stdout.write(self.style.SUCCESS('D3FEND import complete!'))

    @transaction.atomic
    def import_ontology(self):
        """Import D3FEND ontology from OWL (RDF/XML) format"""
        self.stdout.write("Fetching D3FEND ontology...")
        
        try:
            response = requests.get(D3FEND_ONTOLOGY_URL, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch ontology: {e}"))
            return
        
        try:
            self.stdout.write("Parsing OWL ontology with rdflib...")
            g = rdflib.Graph()
            g.parse(data=response.content, format='xml')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to parse OWL ontology: {e}"))
            return
        
        # Define D3FEND namespace
        D3FEND = rdflib.Namespace('http://d3fend.mitre.org/ontologies/d3fend.owl#')
        
        self.stdout.write(f"Ontology loaded with {len(g)} triples")
        
        technique_count = 0
        artifact_count = 0
        technique_map = {}  # IRI -> technique object
        artifact_map = {}   # IRI -> artifact object
        
        # D3FEND Tactic classes (top-level defensive categories)
        TACTIC_CLASSES = {'Detect', 'Harden', 'Isolate', 'Deceive', 'Evict', 'Model'}
        
        # Helper function to find tactic from OWL class hierarchy
        def find_tactic_for_class(class_uri):
            """Find which tactic a class belongs to by walking subClassOf chain"""
            visited = set()
            to_check = [class_uri]
            
            while to_check:
                current = to_check.pop()
                if current in visited:
                    continue
                visited.add(current)
                
                current_str = str(current)
                # Check if this is a tactic class
                for tactic_name in TACTIC_CLASSES:
                    if current_str.endswith(f'#{tactic_name}'):
                        return tactic_name
                
                # Check if fragment matches tactic root
                if '#' in current_str:
                    fragment = current_str.split('#')[-1]
                    if fragment in TACTIC_ROOTS:
                        return TACTIC_ROOTS[fragment]
                
                # Get parent classes
                for parent in g.objects(current, RDFS.subClassOf):
                    if isinstance(parent, rdflib.URIRef):
                        to_check.append(parent)
            
            return ''
        
        self.stdout.write("Processing D3FEND classes...")
        
        # Iterate through ALL OWL classes
        for class_uri in g.subjects(RDF.type, OWL.Class):
            class_str = str(class_uri)
            
            # Only process D3FEND namespace
            if 'd3fend.mitre.org' not in class_str:
                continue
            
            # Extract fragment (class name after #)
            if '#' not in class_str:
                continue
            fragment = class_str.split('#')[-1]
            
            # Skip blank nodes and restrictions
            if not fragment or fragment.startswith('_:'):
                continue
            
            # Get rdfs:label
            label = g.value(class_uri, RDFS.label)
            if label:
                label = str(label)
            else:
                # Use fragment as fallback, converting CamelCase to spaces
                # Note: Simple pattern that handles most cases (e.g., ProcessSpawnAnalysis -> Process Spawn Analysis)
                # May not handle consecutive capitals perfectly (e.g., HTTPSConnection)
                label = re.sub(r'(?<!^)(?=[A-Z])', ' ', fragment)
            
            # Get d3fend-id annotation (the D3-XXX short ID)
            d3fend_id = None
            d3fend_id_pred = D3FEND['d3fend-id']
            id_value = g.value(class_uri, d3fend_id_pred)
            if id_value:
                d3fend_id = str(id_value)
            
            # Get definition
            definition = ''
            def_value = g.value(class_uri, D3FEND.definition)
            if def_value:
                definition = str(def_value)
            else:
                comment = g.value(class_uri, RDFS.comment)
                if comment:
                    definition = str(comment)
            
            # Determine if this is a defensive technique or artifact
            # Check parent classes
            parent_iris = []
            tactic = ''
            
            for parent_uri in g.objects(class_uri, RDFS.subClassOf):
                # Skip restriction nodes (blank nodes)
                if isinstance(parent_uri, rdflib.BNode):
                    continue
                parent_str = str(parent_uri)
                if 'd3fend.mitre.org' in parent_str and '#' in parent_str:
                    parent_iris.append(parent_str)
                    parent_fragment = parent_str.split('#')[-1]
                    if parent_fragment in TACTIC_CLASSES:
                        tactic = parent_fragment
            
            # If no tactic found from immediate parent, try OWL hierarchy walk
            if not tactic:
                tactic = find_tactic_for_class(class_uri)
            
            # Determine type: Technique (has d3fend-id) vs Artifact vs Category
            is_technique = d3fend_id is not None and d3fend_id.startswith('D3-')
            is_artifact = 'DigitalArtifact' in fragment or any('DigitalArtifact' in p for p in parent_iris)
            
            if is_technique:
                # This is a defensive technique
                # Try to get tactic from comprehensive mapping first, fallback to hierarchy detection
                if not tactic and d3fend_id in D3FEND_TACTIC_MAPPINGS:
                    tactic = D3FEND_TACTIC_MAPPINGS[d3fend_id]
                
                technique, created = D3fendDefensiveTechnique.objects.update_or_create(
                    d3fend_id=d3fend_id,
                    defaults={
                        'name': label,
                        'definition': definition,
                        'iri': class_str,
                        'tactic': tactic,
                    }
                )
                technique_map[class_str] = {
                    'obj': technique,
                    'parent_iris': parent_iris
                }
                if created:
                    technique_count += 1
                    if self.verbose:
                        self.stdout.write(f"  + Technique: {d3fend_id} - {label}")
            
            elif is_artifact:
                # This is a digital artifact
                artifact, created = D3fendDigitalArtifact.objects.update_or_create(
                    artifact_id=fragment,
                    defaults={
                        'name': label,
                        'definition': definition,
                        'iri': class_str,
                    }
                )
                artifact_map[class_str] = artifact
                if created:
                    artifact_count += 1
                    if self.verbose:
                        self.stdout.write(f"  + Artifact: {fragment} - {label}")
        
        # Second pass: Link parent-child relationships for techniques
        self.stdout.write("Linking parent-child relationships...")
        linked_parents = 0
        for iri, data in technique_map.items():
            for parent_iri in data['parent_iris']:
                if parent_iri in technique_map:
                    parent_tech = technique_map[parent_iri]['obj']
                    data['obj'].parent = parent_tech
                    data['obj'].save()
                    linked_parents += 1
                    break  # Only link first valid parent (database schema allows single parent)
        
        # Third pass: Link artifacts to techniques via predicates
        self.stdout.write("Linking digital artifacts to techniques...")
        artifact_link_count = 0
        
        artifact_predicates = [
            D3FEND.analyzes,
            D3FEND.produces,
            D3FEND.monitors,
            D3FEND.modifies,
            D3FEND.accesses,
        ]
        
        for technique_str, data in technique_map.items():
            technique_uri = rdflib.URIRef(technique_str)
            technique = data['obj']
            
            for predicate in artifact_predicates:
                for artifact_uri in g.objects(technique_uri, predicate):
                    artifact_str = str(artifact_uri)
                    if artifact_str in artifact_map:
                        artifact = artifact_map[artifact_str]
                        artifact.techniques.add(technique)
                        artifact_link_count += 1
        
        self.stdout.write(self.style.SUCCESS(
            f"Imported {technique_count} techniques, {artifact_count} artifacts, "
            f"{linked_parents} parent links, and {artifact_link_count} artifact-technique links"
        ))

    def assign_tactics(self):
        """Assign tactics to all techniques using the comprehensive mapping"""
        self.stdout.write("Assigning tactics to D3FEND techniques...")
        
        updated = 0
        unmapped = []
        to_update = []
        
        for tech in D3fendDefensiveTechnique.objects.all():
            if tech.d3fend_id in D3FEND_TACTIC_MAPPINGS:
                tactic = D3FEND_TACTIC_MAPPINGS[tech.d3fend_id]
                if tech.tactic != tactic:
                    tech.tactic = tactic
                    to_update.append(tech)
                    updated += 1
                    if self.verbose:
                        self.stdout.write(f"  {tech.d3fend_id}: {tactic}")
            elif not tech.tactic:
                unmapped.append(tech.d3fend_id)
        
        if to_update:
            D3fendDefensiveTechnique.objects.bulk_update(to_update, ['tactic'], batch_size=500)
        
        self.stdout.write(self.style.SUCCESS(f"Assigned tactics to {updated} techniques"))
        
        if unmapped:
            self.stdout.write(self.style.WARNING(
                f"  {len(unmapped)} techniques without mapping: {unmapped[:10]}..."
            ))

    def _extract_iri_fragment(self, iri):
        """Extract fragment (class name) from IRI"""
        if '#' in iri:
            return iri.split('#')[-1]
        return None

    @transaction.atomic
    def import_mappings(self):
        """Import ATT&CK to D3FEND mappings from CSV"""
        self.stdout.write("Fetching D3FEND mappings...")
        
        try:
            response = requests.get(D3FEND_MAPPINGS_CSV_URL, timeout=120)
            response.raise_for_status()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch mappings: {e}"))
            return
        
        self.stdout.write("Parsing CSV mappings...")
        
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        
        if self.verbose:
            self.stdout.write(f"CSV columns: {reader.fieldnames}")
        
        # Build lookup: IRI -> D3FEND technique object
        # This is needed because CSV has IRIs, not D3-XXX IDs
        d3fend_by_iri = {}
        for tech in D3fendDefensiveTechnique.objects.all():
            if tech.iri:
                d3fend_by_iri[tech.iri] = tech
                # Also index by fragment (class name after #) for fallback matching
                fragment = self._extract_iri_fragment(tech.iri)
                if fragment:
                    d3fend_by_iri[fragment] = tech
        
        if self.verbose:
            self.stdout.write(f"D3FEND IRI lookup has {len(d3fend_by_iri)} entries")
        
        mapping_count = 0
        skipped_attack = 0
        skipped_d3fend = 0
        processed = 0
        
        # Track unique mappings to avoid duplicates
        seen_mappings = set()
        
        for row in reader:
            processed += 1
            
            # Get ATT&CK technique ID from 'off_tech_id' column
            attack_id = row.get('off_tech_id', '').strip()
            
            # Get D3FEND technique IRI from 'def_tech' column
            # Example: "http://d3fend.mitre.org/ontologies/d3fend.owl#ProcessSpawnAnalysis"
            d3fend_iri = row.get('def_tech', '').strip()
            
            if not attack_id or not d3fend_iri:
                continue
            
            # Skip if not a valid ATT&CK ID
            if not attack_id.startswith('T'):
                continue
            
            # Skip duplicates
            mapping_key = (attack_id, d3fend_iri)
            if mapping_key in seen_mappings:
                continue
            seen_mappings.add(mapping_key)
            
            # Find ATT&CK technique
            attack_technique = MitreAttackTechnique.objects.filter(
                technique_id=attack_id
            ).first()
            
            if not attack_technique:
                skipped_attack += 1
                if self.verbose and skipped_attack <= 10:
                    self.stdout.write(f"  ! ATT&CK not found: {attack_id}")
                continue
            
            # Find D3FEND technique by IRI or fragment
            d3fend_technique = d3fend_by_iri.get(d3fend_iri)
            
            if not d3fend_technique:
                # Try matching by fragment (class name) as fallback
                fragment = self._extract_iri_fragment(d3fend_iri)
                if fragment:
                    d3fend_technique = d3fend_by_iri.get(fragment)
            
            if not d3fend_technique:
                skipped_d3fend += 1
                if self.verbose and skipped_d3fend <= 10:
                    self.stdout.write(f"  ! D3FEND not found: {d3fend_iri}")
                continue
            
            # Create mapping
            _, created = D3fendAttackMapping.objects.get_or_create(
                attack_technique=attack_technique,
                d3fend_technique=d3fend_technique,
                defaults={'relationship': 'counters'}
            )
            
            if created:
                mapping_count += 1
                if self.verbose and mapping_count <= 5:
                    self.stdout.write(f"  + Mapping: {attack_id} -> {d3fend_technique.d3fend_id}")
        
        self.stdout.write(self.style.SUCCESS(
            f"Processed {processed} CSV rows, imported {mapping_count} ATT&CK → D3FEND mappings "
            f"(skipped {skipped_attack} missing ATT&CK, {skipped_d3fend} missing D3FEND)"
        ))
