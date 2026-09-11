class ACHScoringEngine:
    # Weights for evidence credibility
    WEIGHTS = {
        'HIGH': 3,
        'MEDIUM': 2,
        'LOW': 1
    }
    
    # Scores for consistency (Weighted Inconsistency Counting)
    # In ACH, we look for inconsistency to disprove hypotheses.
    # Higher score = More inconsistent = Less likely
    SCORE_VALUES = {
        'CC': 0,  # Very Consistent
        'C': 0,   # Consistent
        'N': 0,   # Neutral
        'I': 1,   # Inconsistent
        'II': 2   # Very Inconsistent
    }
    
    # Scoring category thresholds
    CATEGORY_THRESHOLDS = {
        'MOST_LIKELY': 3,      # Score 0-3: Most likely
        'PLAUSIBLE': 10,       # Score 4-10: Plausible
        # Score 11+: Eliminated
    }

    @staticmethod
    def calculate_scores(analysis):
        """
        Calculates the inconsistency score for each hypothesis in the analysis.
        Returns a dictionary mapping hypothesis_id to score.
        """
        results = {}
        hypotheses = analysis.hypotheses.all().prefetch_related('matrix_cells', 'matrix_cells__evidence')
        
        for hypothesis in hypotheses:
            score = 0
            for cell in hypothesis.matrix_cells.all():
                evidence_weight = ACHScoringEngine.WEIGHTS.get(cell.evidence.credibility, 1)
                cell_score = ACHScoringEngine.SCORE_VALUES.get(cell.score, 0)
                score += (evidence_weight * cell_score)
            results[str(hypothesis.id)] = score
            
        return results
    
    @staticmethod
    def get_category(score):
        """
        Determines the category of a hypothesis based on its score.
        Returns: ('MOST_LIKELY', 'PLAUSIBLE', or 'ELIMINATED')
        """
        if score <= ACHScoringEngine.CATEGORY_THRESHOLDS['MOST_LIKELY']:
            return 'MOST_LIKELY'
        elif score <= ACHScoringEngine.CATEGORY_THRESHOLDS['PLAUSIBLE']:
            return 'PLAUSIBLE'
        else:
            return 'ELIMINATED'
    
    @staticmethod
    def get_visual_bar(score, max_score=None):
        """
        Generates a visual bar representation proportional to score.
        Uses █ character, with bar length proportional to score (max 32 chars).
        """
        if max_score is None:
            max_score = 30  # Default max for proportion
        
        if score == 0:
            return '█'
        
        # Scale score to bar length (max 32 characters)
        bar_length = min(int((score / max_score) * 32) + 1, 32)
        return '█' * bar_length
