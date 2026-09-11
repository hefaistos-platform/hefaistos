#!/usr/bin/env python3
"""
Integration test for format detection with real problematic file.
Run via: docker compose exec rule_connector python test_problematic_file.py
"""

import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the detection function
from connector import detect_format_from_content, parse_kql_file

def test_problematic_file():
    """Test the actual problematic KQL file that was reported."""
    logger.info("=" * 80)
    logger.info("Testing Problematic KQL File (with .yml extension)")
    logger.info("=" * 80)
    
    # Path to the test fixture
    test_file = Path(__file__).parent / "test_fixtures" / "kql_rule_as_yml.yml"
    
    if not test_file.exists():
        logger.error(f"Test file not found: {test_file}")
        return False
    
    logger.info(f"Test file: {test_file}")
    
    try:
        # Read the file
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info(f"File size: {len(content)} bytes")
        logger.info(f"File preview (first 200 chars):\n{content[:200]}")
        
        # Test 1: Format detection
        logger.info("\n[TEST 1] Format Detection")
        logger.info("-" * 80)
        detected_format = detect_format_from_content(content, str(test_file))
        logger.info(f"Detected format: {detected_format}")
        
        if detected_format == 'KQL':
            logger.info("✅ PASS: File correctly detected as KQL")
        else:
            logger.error(f"❌ FAIL: Expected KQL, got {detected_format}")
            return False
        
        # Test 2: KQL Parsing
        logger.info("\n[TEST 2] KQL Metadata Extraction")
        logger.info("-" * 80)
        try:
            metadata = parse_kql_file(content, str(test_file))
            logger.info(f"Title: {metadata['title']}")
            logger.info(f"Description: {metadata['description'][:50]}..." if metadata['description'] else "Description: (none)")
            logger.info(f"Author: {metadata['author']}")
            logger.info(f"Status: {metadata['status']}")
            logger.info(f"Level: {metadata['level']}")
            logger.info(f"Tags: {metadata['tags']}")
            logger.info("✅ PASS: KQL metadata extracted successfully")
        except Exception as e:
            logger.error(f"❌ FAIL: Failed to parse KQL metadata: {e}")
            return False
        
        # Test 3: Verify this wouldn't be parsed as YAML
        logger.info("\n[TEST 3] YAML Parsing (should fail gracefully)")
        logger.info("-" * 80)
        import yaml
        try:
            yaml_doc = yaml.safe_load(content)
            logger.warning(f"YAML parsing succeeded (got {type(yaml_doc)})")
            if not isinstance(yaml_doc, dict):
                logger.info("✅ PASS: YAML parse result is not a dict (would have been skipped)")
            else:
                logger.warning(f"⚠️  YAML parsing returned a dict with {len(yaml_doc)} keys")
        except yaml.YAMLError as e:
            logger.info(f"YAML parsing failed (as expected): {str(e)[:100]}")
            logger.info("✅ PASS: Would have failed as YAML, but now handled as KQL")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ All tests passed! The problematic file is now handled correctly.")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    success = test_problematic_file()
    sys.exit(0 if success else 1)
