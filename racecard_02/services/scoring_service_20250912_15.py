import math
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any
from django.db import models
from racecard_02.models import Horse, Race, HorseScore, Run

class ScoringService:
    """
    Service for calculating horse racing performance scores
    """
    
    def __init__(self, debug_callback=None):
        """
        Initialize scoring service
        
        Args:
            debug_callback: Function to call with debug messages
        """
        self.debug_callback = debug_callback
        self.default_score = 50.0
    
    def _debug(self, msg: str) -> None:
        """Send debug message if callback is provided"""
        if self.debug_callback:
            self.debug_callback(msg)
    
    def create_score_record(self, horse: Horse, race: Race) -> Tuple[HorseScore, bool]:
        """
        Calculate scores for a horse based on its past runs
        
        Returns:
            Tuple of (score_record, created_flag)
        """
        self._debug(f"🐎 Scoring horse: {horse.horse_name}")
        self._debug(f"🏇 Current race: R{race.race_no} - {race.race_name}")
        
        # Get all runs for this horse
        runs = Run.objects.filter(horse=horse)
        self._debug(f"📊 Analyzing {runs.count()} past runs")
        
        # Calculate various score components
        scores = self._calculate_all_scores(runs, horse, race)
        
        # Calculate overall weighted score
        overall_score = self._calculate_overall_score(scores)
        
        # Create or update score record
        score_record, created = HorseScore.objects.update_or_create(
            horse=horse,
            race=race,
            defaults={
                'overall_score': overall_score,
                'speed_score': scores['speed'],
                'consistency_score': scores['consistency'],
                'recent_form_score': scores['recent_form'],
                'class_score': scores['class'],
                'distance_score': scores['distance'],
                'best_mr_score': getattr(horse, 'best_merit_rating', 0) or 0,
                'current_mr_score': getattr(horse, 'horse_merit', 0) or 0,
                'jt_score': getattr(horse, 'jt_score', 50) or 50,
            }
        )
        
        self._debug(f"✅ Final score: {overall_score:.1f}")
        return score_record, created
    
    def _calculate_all_scores(self, runs: List[Run], horse: Horse, race: Race) -> Dict[str, float]:
        """Calculate all individual score components"""
        if not runs:
            self._debug("📭 No past runs - using default scores")
            return self._get_default_scores()
        
        return {
            'speed': self._calculate_speed_score(runs),
            'consistency': self._calculate_consistency_score(runs),
            'recent_form': self._calculate_recent_form_score(runs),
            'class': self._calculate_class_score(runs, race),
            'distance': self._calculate_distance_score(runs, race),
        }
    
    def _calculate_speed_score(self, runs: List[Run]) -> float:
        """Calculate score based on finishing positions"""
        valid_positions = []
        
        for run in runs:
            position = self._parse_position(run.position)
            if position is not None and position > 0:
                valid_positions.append(position)
        
        if not valid_positions:
            return self.default_score
        
        # Convert positions to scores (1st = 100, 2nd = 90, etc.)
        position_scores = [max(0, 100 - (pos * 10)) for pos in valid_positions]
        avg_score = sum(position_scores) / len(position_scores)
        
        self._debug(f"   🏁 Speed score: {avg_score:.1f} (from {len(valid_positions)} positions)")
        return avg_score
    
    def _calculate_consistency_score(self, runs: List[Run]) -> float:
        """Calculate consistency based on position variance"""
        positions = []
        
        for run in runs:
            position = self._parse_position(run.position)
            if position is not None and position > 0:
                positions.append(position)
        
        if len(positions) < 2:
            return self.default_score
        
        # Lower variance = more consistent = higher score
        avg_position = sum(positions) / len(positions)
        variance = sum((p - avg_position) ** 2 for p in positions) / len(positions)
        consistency = max(0, 100 - (variance * 5))
        
        self._debug(f"   📈 Consistency: {consistency:.1f} (variance: {variance:.2f})")
        return consistency
    
    def _calculate_recent_form_score(self, runs: List[Run]) -> float:
        """Give more weight to recent performances"""
        if not runs:
            return self.default_score
        
        # Sort runs by date (most recent first)
        dated_runs = sorted(runs, key=lambda x: x.run_date, reverse=True)
        
        # Weight recent runs more heavily (last 3 runs)
        recent_runs = dated_runs[:3]
        total_weight, weighted_score = 0, 0
        
        for i, run in enumerate(recent_runs):
            weight = 3 - i  # 3, 2, 1 weights for most recent to least recent
            position = self._parse_position(run.position)
            
            if position and position > 0:
                run_score = max(0, 100 - (position * 10))
                weighted_score += run_score * weight
                total_weight += weight
        
        if total_weight > 0:
            form_score = weighted_score / total_weight
            self._debug(f"   🔥 Recent form: {form_score:.1f} (last {len(recent_runs)} runs)")
            return form_score
        
        return self.default_score
    
    def _calculate_class_score(self, runs: List[Run], race: Race) -> float:
        """Score based on class of previous races vs current race"""
        current_class = race.race_class

        if not runs:
            return self.default_score
        
        # Count runs in similar or better class
        similar_class_runs = 0
        for run in runs:
            run_class = run.race_class
            if run_class and current_class:
                # Simple class comparison - expand with actual logic
                if run_class == current_class:
                    similar_class_runs += 1
        
        class_score = min(100, self.default_score + (similar_class_runs * 5))
        self._debug(f"   🏆 Class score: {class_score:.1f} ({similar_class_runs} similar class runs)")
        return class_score
    
    def _calculate_distance_score(self, runs: List[Run], race: Race) -> float:
        """Score based on distance suitability"""
        current_distance = race.race_distance
        
        if not runs or not current_distance:
            return self.default_score
        
        # Count runs at similar distance
        similar_distance_runs = 0
        for run in runs:
            run_distance = run.distance
            if run_distance and self._is_similar_distance(run_distance, current_distance):
                similar_distance_runs += 1
        
        distance_score = min(100, self.default_score + (similar_distance_runs * 3))
        self._debug(f"   📏 Distance score: {distance_score:.1f} ({similar_distance_runs} similar distance runs)")
        return distance_score
    
    def _calculate_overall_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted overall score"""
        weights = self._get_score_weights()
        
        total_weight = 0
        weighted_sum = 0
        
        for score_type, weight in weights.items():
            if score_type in scores:
                weighted_sum += scores[score_type] * weight
                total_weight += weight
        
        if total_weight > 0:
            overall_score = weighted_sum / total_weight
            return round(overall_score, 1)
        
        return self.default_score
    
    def _get_score_weights(self) -> Dict[str, float]:
        """Get weights for different score components"""
        return {
            'speed': 0.4,           # 40% weight to speed/position
            'recent_form': 0.3,      # 30% to recent form
            'consistency': 0.15,     # 15% to consistency
            'class': 0.1,            # 10% to class
            'distance': 0.05,        # 5% to distance
        }
    
    def _get_default_scores(self) -> Dict[str, float]:
        """Return default scores when no run data is available"""
        return {key: self.default_score for key in self._get_score_weights().keys()}
    
    def _parse_position(self, position: Any) -> Optional[int]:
        """Parse finishing position from various formats"""
        if position is None:
            return None
        
        try:
            if isinstance(position, (int, float)):
                return int(position)
            elif isinstance(position, str):
                # Handle positions like "1", "2nd", "3rd", etc.
                if position.isdigit():
                    return int(position)
                # Remove non-numeric characters and try to parse
                clean_pos = ''.join(c for c in position if c.isdigit())
                if clean_pos:
                    return int(clean_pos)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _is_similar_distance(self, dist1: str, dist2: str) -> bool:
        """Check if two distances are similar"""
        if not dist1 or not dist2:
            return False
        
        # Simple implementation - expand with actual distance comparison logic
        try:
            # Extract numeric part of distance
            num1 = float(''.join(c for c in dist1 if c.isdigit() or c == '.'))
            num2 = float(''.join(c for c in dist2 if c.isdigit() or c == '.'))
            return abs(num1 - num2) <= 200  # Within 200m considered similar
        except (ValueError, TypeError):
            return dist1 == dist2