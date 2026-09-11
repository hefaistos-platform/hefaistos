#!/usr/bin/env python3
"""
Test script for format detection in rule connector.
Can be run locally or in Docker: docker compose exec rule_connector python test_format_detection.py

Tests the detect_format_from_content function with various rule formats.
"""

import sys
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the detection function
from connector import detect_format_from_content

# Test cases
TEST_CASES = [
    {
        'name': 'KQL Rule (Comment Style)',
        'content': '''// TITLE: Account Manipulation Detection
// DESCRIPTION: Detects account manipulation activities
// AUTHOR: Security Team
// TAGS: attack.t1098.005, account-manipulation

SecurityEvent
| where EventID == 4738
| where TimeGenerated > ago(24h)
| project ComputerName, Account, EventID, TimeGenerated
| summarize count() by ComputerName''',
        'expected': 'KQL'
    },
    {
        'name': 'KQL Rule with Let Statement',
        'content': '''let suspicious_processes = dynamic(["cmd.exe", "powershell.exe", "cscript.exe"]);
DeviceProcessEvents
| where ProcessName in (suspicious_processes)
| where TimeGenerated > ago(1h)
| project DeviceName, ProcessName, CommandLine
| order by TimeGenerated desc''',
        'expected': 'KQL'
    },
    {
        'name': 'KQL Rule with Table Names',
        'content': '''// Detects failed sign-in attempts from multiple IPs
SigninLogs
| where ResultType != 0
| where TimeGenerated > ago(24h)
| summarize AttemptCount = count() by UserPrincipalName, IPAddress
| where AttemptCount > 5''',
        'expected': 'KQL'
    },
    {
        'name': 'SIGMA Rule Standard Format',
        'content': '''title: Suspicious Process Creation
id: 12345678-1234-1234-1234-123456789abc
status: experimental
description: Detects suspicious process creation events
author: Security Team
date: 2026-02-03
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        Image|endswith:
            - '\\cmd.exe'
            - '\\powershell.exe'
    condition: selection
falsepositives:
    - Legitimate administrative activity
level: medium''',
        'expected': 'SIGMA'
    },
    {
        'name': 'SIGMA Rule with Minimal Fields',
        'content': '''title: Test Detection
logsource:
    product: windows
detection:
    selection:
        EventID: 4688
    condition: selection
status: test''',
        'expected': 'SIGMA'
    },
    {
        'name': 'Ambiguous Content',
        'content': '''Some random content that doesn't match any pattern
This could be anything
No clear indicators''',
        'expected': 'UNKNOWN'
    },
    {
        'name': 'Empty Content',
        'content': '',
        'expected': 'UNKNOWN'
    },
    {
        'name': 'KQL with Pipes and Where',
        'content': '''DeviceNetworkEvents
| where RemotePort in (4444, 5555, 8080)
| where RemoteIPType == "Public"
| where TimeGenerated > ago(1h)
| project Timestamp, DeviceName, RemoteIP, RemotePort''',
        'expected': 'KQL'
    },
]

def run_tests():
    """Run all test cases and report results."""
    logger.info("=" * 80)
    logger.info("Starting Format Detection Tests")
    logger.info("=" * 80)
    
    passed = 0
    failed = 0
    
    for test_case in TEST_CASES:
        name = test_case['name']
        content = test_case['content']
        expected = test_case['expected']
        
        try:
            detected = detect_format_from_content(content, f"test_{name.lower().replace(' ', '_')}.yml")
            
            if detected == expected:
                logger.info(f"✅ PASS: {name}")
                logger.info(f"   Expected: {expected}, Got: {detected}")
                passed += 1
            else:
                logger.error(f"❌ FAIL: {name}")
                logger.error(f"   Expected: {expected}, Got: {detected}")
                failed += 1
                logger.debug(f"   Content preview: {content[:100]}...")
        except Exception as e:
            logger.error(f"❌ ERROR: {name}")
            logger.error(f"   Exception: {e}")
            failed += 1
    
    logger.info("=" * 80)
    logger.info(f"Test Results: {passed} passed, {failed} failed out of {len(TEST_CASES)} tests")
    logger.info("=" * 80)
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
