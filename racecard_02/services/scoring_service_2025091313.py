import math
import re
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Any
from django.db import models
from django.utils import timezone
from racecard_02.models import Horse, Race, HorseScore, Run

class ScoringService:
    """
    Comprehensive scoring service using all available horse and race parameters
    """
    
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback
        self.default_score = 50.0
    
    def _debug(self, msg: str) -> None:
        if self.debug_callback:
            self.debug_callback(msg)
    
    def create_score_record(self, horse: Horse, race: Race) -> Tuple[HorseScore, bool]:
        """
        Calculate comprehensive scores using all available parameters
        """
        self._debug(f"🐎 Scoring horse: {horse.horse_name}")
        self._debug(f"🏇 Current race: R{race.race_no} - {race.race_class}")
        
        # Calculate all score components
        scores = self._calculate_all_scores(horse, race)
        
        # Calculate overall weighted score
        overall_score = self._calculate_overall_score(scores)
        
        # Create or update score record with all parameters
        score_record, created = HorseScore.objects.update_or_create(
            horse=horse,
            race=race,
            defaults={
                'overall_score': overall_score,
                'speed_score': scores['speed'],
                'form_score': scores['form'],
                'class_score': scores['class'],
                'consistency_score': scores['consistency'],
                'value_score': scores['value'],
                'physical_score': scores['physical'],
                'intangible_score': scores['intangible'],
                
                # Individual component scores for detailed analysis
                'speed_rating_score': scores['speed_rating'],
                'best_mr_score': scores['best_mr'],
                'current_mr_score': scores['current_mr'],
                'jt_score': scores['jt'],
                'odds_score': scores['odds'],
                'weight_score': scores['weight'],
                'draw_score': scores['draw'],
                'blinkers_score': scores['blinkers'],
                
                # Store raw values for reference
                'speed_rating_value': getattr(horse, 'speed_rating', 0),
                'best_mr_value': getattr(horse, 'best_merit_rating', 0),
                'current_mr_value': getattr(horse, 'horse_merit', 0),
                'jt_value': getattr(horse, 'jt_score', 50),
                'odds_value': self._parse_odds(getattr(horse, 'odds', '')),
                'weight_value': 0,  # Will be populated if available
                'draw_value': horse.horse_no,  # Using horse number as draw
                'blinkers_value': 1 if getattr(horse, 'blinkers', False) else 0,
            }
        )
        
        self._debug(f"✅ Final overall score: {overall_score:.1f}")
        return score_record, created
    
    def _calculate_all_scores(self, horse: Horse, race: Race) -> Dict[str, float]:
        """Calculate all score components using available parameters"""
        self._debug("   📊 Calculating scores from available parameters")
        
        return {
            # Core components
            'speed': self._calculate_speed_score(horse),
            'form': self._calculate_form_score(horse),
            'class': self._calculate_class_score(horse, race),
            'consistency': self._calculate_consistency_score(horse),
            'value': self._calculate_value_score(horse),
            'physical': self._calculate_physical_score(horse),
            'intangible': self._calculate_intangible_score(horse),
            
            # Individual parameter scores
            'speed_rating': self._calculate_speed_rating_score(horse),
            'best_mr': self._calculate_best_mr_score(horse),
            'current_mr': self._calculate_current_mr_score(horse),
            'jt': self._calculate_jt_score(horse),
            'odds': self._calculate_odds_score(horse),
            'weight': self._calculate_weight_score(horse),
            'draw': self._calculate_draw_score(horse, race),
            'blinkers': self._calculate_blinkers_score(horse),
        }
    
    def _calculate_speed_score(self, horse: Horse) -> float:
        """Overall speed assessment"""
        speed_rating = getattr(horse, 'speed_rating', 50)
        current_mr = getattr(horse, 'horse_merit', 0)
        
        # Combine speed rating and current merit
        if speed_rating > 0 and current_mr > 0:
            score = (speed_rating * 0.6) + (current_mr * 0.4)
            self._debug(f"   🏁 Speed score: {score:.1f} (Rating: {speed_rating}, MR: {current_mr})")
            return min(100, score)
        
        return 50.0
    
    def _calculate_speed_rating_score(self, horse: Horse) -> float:
        """Pure speed rating score"""
        speed_rating = getattr(horse, 'speed_rating', 50)
        score = min(100, max(0, speed_rating))
        self._debug(f"   ⚡ Speed rating: {score:.1f}")
        return score
    
    def _calculate_form_score(self, horse: Horse) -> float:
        """Form assessment based on current vs best MR"""
        best_mr = getattr(horse, 'best_merit_rating', 0)
        current_mr = getattr(horse, 'horse_merit', 0)
        
        if best_mr > 0 and current_mr > 0:
            form_ratio = current_mr / best_mr
            if form_ratio >= 0.95:
                score = 90.0  # Near best form
            elif form_ratio >= 0.85:
                score = 70.0  # Good form
            elif form_ratio >= 0.75:
                score = 50.0  # Average form
            else:
                score = 30.0  # Poor form
        else:
            score = 50.0  # Unknown form
        
        self._debug(f"   🔥 Form score: {score:.1f} (Current MR: {current_mr}, Best MR: {best_mr})")
        return score
    
    def _calculate_best_mr_score(self, horse: Horse) -> float:
        """Best merit rating score"""
        best_mr = getattr(horse, 'best_merit_rating', 0)
        score = min(100, max(0, best_mr * 0.8))  # Scale MR to 0-100
        self._debug(f"   🏆 Best MR score: {score:.1f} (MR: {best_mr})")
        return score
    
    def _calculate_current_mr_score(self, horse: Horse) -> float:
        """Current merit rating score"""
        current_mr = getattr(horse, 'horse_merit', 0)
        score = min(100, max(0, current_mr * 0.8))  # Scale MR to 0-100
        self._debug(f"   📊 Current MR score: {score:.1f} (MR: {current_mr})")
        return score
    
    def _calculate_class_score(self, horse: Horse, race: Race) -> float:
        """Class suitability assessment"""
        current_mr = getattr(horse, 'horse_merit', 0)
        race_class = race.race_class or ""
        
        # Simple class assessment based on MR and class string
        score = 50.0  # Default
        
        if current_mr > 0:
            # Adjust based on MR (higher MR = better class ability)
            score = min(100, current_mr * 0.8)
        
        # Adjust based on class keywords
        class_upper = race_class.upper()
        if "GROUP" in class_upper or "G1" in class_upper or "G2" in class_upper:
            score *= 0.9  # Slightly penalize for group races unless MR is high
            self._debug(f"   🏆 Group race adjustment: {score:.1f}")
        
        self._debug(f"   🎯 Class score: {score:.1f}")
        return score
    
    def _calculate_consistency_score(self, horse: Horse) -> float:
        """Consistency assessment based on J-T combo"""
        jt_score = getattr(horse, 'jt_score', 50)
        
        # JT score is a good indicator of consistency
        consistency = jt_score
        
        # Blinkers can improve consistency
        if getattr(horse, 'blinkers', False):
            consistency = min(100, consistency + 5.0)
            self._debug(f"   👓 Blinkers consistency bonus: +5.0")
        
        self._debug(f"   📈 Consistency score: {consistency:.1f} (JT: {jt_score})")
        return consistency
    
    def _calculate_jt_score(self, horse: Horse) -> float:
        """Jockey-Trainer combination score"""
        jt_score = getattr(horse, 'jt_score', 50)
        self._debug(f"   🤝 J-T score: {jt_score:.1f}")
        return jt_score
    
    def _calculate_value_score(self, horse: Horse) -> float:
        """Value assessment based on odds"""
        odds = getattr(horse, 'odds', '')
        odds_value = self._parse_odds(odds)
        
        if odds_value > 0:
            # Lower odds = better value = higher score
            if odds_value < 3.0:
                score = 30.0  # Short price, poor value
            elif odds_value < 6.0:
                score = 50.0  # Fair price
            elif odds_value < 10.0:
                score = 70.0  # Good value
            else:
                score = 90.0  # Excellent value
        else:
            score = 50.0  # Unknown odds
        
        self._debug(f"   💰 Value score: {score:.1f} (Odds: {odds_value:.1f})")
        return score
    
    def _calculate_odds_score(self, horse: Horse) -> float:
        """Pure odds-based score (lower odds = better)"""
        odds = getattr(horse, 'odds', '')
        odds_value = self._parse_odds(odds)
        
        if odds_value > 0:
            # Convert odds to score (2.0 odds = 90, 10.0 odds = 50, 20.0 odds = 30)
            score = max(30, min(90, 100 - (odds_value * 3)))
        else:
            score = 50.0
        
        self._debug(f"   📉 Odds score: {score:.1f} (Odds: {odds_value:.1f})")
        return score
    
    def _calculate_physical_score(self, horse: Horse) -> float:
        """Physical condition assessment"""
        # Use age as a proxy for physical condition
        age = self._parse_age(getattr(horse, 'age', ''))
        
        if age:
            if age <= 4:
                score = 80.0  # Prime age
            elif age <= 6:
                score = 70.0  # Mature
            elif age <= 8:
                score = 60.0  # Experienced
            else:
                score = 40.0  # Older horse
        else:
            score = 50.0  # Unknown age
        
        self._debug(f"   💪 Physical score: {score:.1f} (Age: {age or 'Unknown'})")
        return score
    
    def _calculate_weight_score(self, horse: Horse) -> float:
        """Weight assessment (placeholder - needs actual weight data)"""
        # This would use actual weight data when available
        score = 50.0
        self._debug(f"   ⚖️ Weight score: {score:.1f} (Default)")
        return score
    
    def _calculate_draw_score(self, horse: Horse, race: Race) -> float:
        """Draw assessment based on horse number"""
        draw = horse.horse_no  # Using horse number as draw proxy
        
        # Simple draw assessment (lower numbers better for inside draws)
        if draw <= 4:
            score = 70.0  # Good draw
        elif draw <= 8:
            score = 60.0  # Average draw
        else:
            score = 40.0  # Wide draw
        
        self._debug(f"   🎯 Draw score: {score:.1f} (Draw: {draw})")
        return score
    
    def _calculate_intangible_score(self, horse: Horse) -> float:
        """Intangible factors assessment"""
        score = 50.0
        
        # Blinkers can be a positive intangible
        if getattr(horse, 'blinkers', False):
            score = min(100, score + 10.0)
            self._debug(f"   ✨ Blinkers intangible bonus: +10.0")
        
        # Good J-T combo is intangible
        jt_score = getattr(horse, 'jt_score', 50)
        if jt_score > 70:
            score = min(100, score + (jt_score - 70) * 0.3)
        
        self._debug(f"   🌟 Intangible score: {score:.1f}")
        return score
    
    def _calculate_blinkers_score(self, horse: Horse) -> float:
        """Blinkers assessment"""
        has_blinkers = getattr(horse, 'blinkers', False)
        score = 70.0 if has_blinkers else 50.0
        self._debug(f"   👓 Blinkers score: {score:.1f} ({'With' if has_blinkers else 'Without'} blinkers)")
        return score
    
    def _parse_odds(self, odds_text: str) -> float:
        """Parse odds from text to decimal value"""
        if not odds_text:
            return 0.0
        
        try:
            # Handle fractions like "5/2", "2/1"
            if '/' in odds_text:
                numerator, denominator = odds_text.split('/')
                return float(numerator) / float(denominator) + 1
            
            # Handle decimals
            return float(odds_text)
        except (ValueError, TypeError):
            return 0.0
    
    def _parse_age(self, age_text: str) -> Optional[int]:
        """Parse age from text"""
        if not age_text:
            return None
        
        try:
            # Extract digits from age text
            match = re.search(r'\d+', age_text)
            if match:
                return int(match.group())
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _calculate_overall_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted overall score"""
        weights = {
            'speed': 0.20,       # 20% - Speed rating and current form
            'form': 0.15,        # 15% - Current vs best form
            'class': 0.15,       # 15% - Class suitability
            'consistency': 0.12, # 12% - Consistency (J-T combo)
            'value': 0.10,       # 10% - Odds value
            'physical': 0.10,    # 10% - Physical condition
            'intangible': 0.08,  # 8%  - Intangible factors
            'draw': 0.05,        # 5%  - Draw position
            'weight': 0.05,      # 5%  - Weight (when available)
        }
        
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