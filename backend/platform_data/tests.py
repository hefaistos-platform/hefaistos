from django.test import TestCase
from platform_data.models import D3fendDefensiveTechnique
from platform_data.management.commands.import_d3fend import TACTIC_ROOTS, D3FEND_TACTIC_MAPPINGS


class D3FENDTacticAssignmentTests(TestCase):
    """Test tactic assignment logic for D3FEND techniques"""
    
    def test_tactic_roots_dictionary(self):
        """Verify TACTIC_ROOTS contains expected tactic categories"""
        expected_tactics = {'Detect', 'Harden', 'Isolate', 'Deceive', 'Evict', 'Model'}
        
        # Get all unique tactics from TACTIC_ROOTS
        tactics_in_roots = set(TACTIC_ROOTS.values())
        
        # All tactics should be represented
        self.assertEqual(tactics_in_roots, expected_tactics)
        
        # Verify some expected mappings
        self.assertEqual(TACTIC_ROOTS.get('NetworkTrafficAnalysis'), 'Detect')
        self.assertEqual(TACTIC_ROOTS.get('ApplicationHardening'), 'Harden')
        self.assertEqual(TACTIC_ROOTS.get('ExecutionIsolation'), 'Isolate')
        self.assertEqual(TACTIC_ROOTS.get('DecoyObject'), 'Deceive')
        self.assertEqual(TACTIC_ROOTS.get('CredentialEviction'), 'Evict')
        self.assertEqual(TACTIC_ROOTS.get('AssetInventory'), 'Model')
    
    def test_d3fend_tactic_mappings(self):
        """Verify D3FEND_TACTIC_MAPPINGS contains comprehensive technique mappings"""
        # Verify some expected direct mappings from each tactic
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-CF'), 'Isolate')  # Content Filtering
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-AA'), 'Harden')  # Agent Authentication
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-AI'), 'Model')  # Asset Inventory
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-SDA'), 'Detect')  # System Daemon Analysis
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-DE'), 'Deceive')  # Decoy Environment
        self.assertEqual(D3FEND_TACTIC_MAPPINGS.get('D3-CE'), 'Evict')  # Credential Eviction
        
        # All values should be valid tactics
        valid_tactics = {'Detect', 'Harden', 'Isolate', 'Deceive', 'Evict', 'Model'}
        for d3fend_id, tactic in D3FEND_TACTIC_MAPPINGS.items():
            self.assertIn(tactic, valid_tactics, 
                         f"Technique {d3fend_id} has invalid tactic: {tactic}")
        
        # Verify we have a comprehensive mapping (should be 226 techniques as of this PR)
        self.assertGreaterEqual(len(D3FEND_TACTIC_MAPPINGS), 226,
                               "D3FEND_TACTIC_MAPPINGS should contain at least 226 technique mappings")
    
    def test_tactic_coverage_by_category(self):
        """Verify each tactic category has expected number of mappings"""
        from collections import Counter
        
        tactic_counts = Counter(D3FEND_TACTIC_MAPPINGS.values())
        
        # Verify we have techniques in each tactic (approximate expected counts)
        # Using slightly lower thresholds to allow for potential variations
        self.assertGreater(tactic_counts['Detect'], 75, "Should have 75+ Detect techniques")
        self.assertGreater(tactic_counts['Harden'], 50, "Should have 50+ Harden techniques")
        self.assertGreater(tactic_counts['Isolate'], 20, "Should have 20+ Isolate techniques")
        self.assertGreater(tactic_counts['Deceive'], 10, "Should have 10+ Deceive techniques")
        self.assertGreater(tactic_counts['Evict'], 25, "Should have 25+ Evict techniques")
        self.assertGreater(tactic_counts['Model'], 20, "Should have 20+ Model techniques")
