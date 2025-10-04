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
    with special handling for maiden horses
    """
    
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback
        self.default_score = 50.0
        self.magic_tips_horses = []  # Store magic tips for scoring
    
    def _debug(self, msg: str) -> None:
        if self.debug_callback:
            self.debug_callback(msg)
    
    def set_magic_tips(self, magic_tips: List[int]) -> None:
        """Set the magic tips for the current race"""
        self.magic_tips_horses = magic_tips
        self._debug(f"🎯 Magic Tips set: {magic_tips}")
    
    def create_score_record(self, horse: Horse, race: Race) -> Tuple[HorseScore, bool]:
        """
        Calculate comprehensive scores using all available parameters
        with special handling for maiden horses
        """
        self._debug(f"🐎 Scoring horse: {horse.horse_name}")
        self._debug(f"🏇 Current race: R{race.race_no} - {race.race_class}")
        
        # Check if this is a maiden horse
        is_maiden = self._is_maiden_horse(horse)
        if is_maiden:
            self._debug(f"   🐣 MAIDEN HORSE DETECTED - Special scoring applied")
        
        try:
            # Calculate all score components
            scores = self._calculate_all_scores(horse, race, is_maiden)
            
            # Calculate overall weighted score
            overall_score = self._calculate_overall_score(scores, is_maiden)
            
            # Apply Magic Tips boost if applicable
            is_magic_tip = horse.horse_no in self.magic_tips_horses
            magic_boost = self._calculate_magic_tips_boost(horse, overall_score, is_magic_tip)
            final_score = overall_score + magic_boost
            
            # Get blinkers as boolean
            blinkers_bool = getattr(horse, 'blinkers', False)
            
            # Create or update score record with correct data types
            score_record, created = HorseScore.objects.update_or_create(
                horse=horse,
                race=race,
                defaults={
                    'overall_score': final_score,
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
                    'speed_score': self._safe_float(getattr(horse, 'speed_rating', 0)),
                    'best_mr_value': self._safe_float(getattr(horse, 'best_merit_rating', 0)),
                    'current_mr_value': self._safe_float(getattr(horse, 'horse_merit', 0)),
                    'jt_value': self._safe_float(getattr(horse, 'jt_score', 50)),
                    'odds_value': self._parse_odds(getattr(horse, 'odds', '')),
                    'weight_value': self._safe_float(getattr(horse, 'actual_weight', getattr(horse, 'weight', 0.0))),
                    'draw_value': float(horse.horse_no),
                    'blinkers_value': blinkers_bool,
                    
                    # Magic Tips fields
                    'is_magic_tip': is_magic_tip,
                    'magic_tips_boost': magic_boost,
                    'is_maiden': is_maiden,
                }
            )
            
            if is_magic_tip:
                self._debug(f"✨ MAGIC TIP BOOST: {magic_boost:.1f} (Final: {final_score:.1f})")
            elif is_maiden:
                self._debug(f"🐣 MAIDEN FINAL SCORE: {final_score:.1f}")
            else:
                self._debug(f"✅ Final overall score: {final_score:.1f}")
                
            return score_record, created
            
        except Exception as e:
            self._debug(f"❌ Error scoring {horse.horse_name}: {e}")
            import traceback
            self._debug(f"Traceback: {traceback.format_exc()}")
            raise
    
    def _is_maiden_horse(self, horse: Horse) -> bool:
        """Check if this is a maiden horse (no or few runs, no merit ratings)"""
        # Check if merit ratings are missing or zero (common for maidens)
        current_mr = self._safe_float(getattr(horse, 'horse_merit', 0))
        best_mr = self._safe_float(getattr(horse, 'best_merit_rating', 0))
        
        # If both MRs are zero or None, likely a maiden
        if (current_mr == 0 or current_mr is None) and (best_mr == 0 or best_mr is None):
            return True
        
        # Check if horse has very few runs (you might want to check Run model here)
        # For now, we'll rely on MR data
        
        return False
    
    def _safe_float(self, value, default=0.0):
        """Safely convert value to float, handling None"""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _calculate_all_scores(self, horse: Horse, race: Race, is_maiden: bool = False) -> Dict[str, float]:
        """Calculate all score components using available parameters"""
        self._debug("   📊 Calculating scores from available parameters")
        
        return {
            # Core components
            'speed': self._calculate_speed_score(horse, is_maiden),
            'form': self._calculate_form_score(horse, is_maiden),
            'class': self._calculate_class_score(horse, race, is_maiden),
            'consistency': self._calculate_consistency_score(horse, is_maiden),
            'value': self._calculate_value_score(horse),
            'physical': self._calculate_physical_score(horse),
            'intangible': self._calculate_intangible_score(horse, is_maiden),
            
            # Individual parameter scores
            'speed_rating': self._calculate_speed_rating_score(horse),
            'best_mr': self._calculate_best_mr_score(horse, is_maiden),
            'current_mr': self._calculate_current_mr_score(horse, is_maiden),
            'jt': self._calculate_jt_score(horse),
            'odds': self._calculate_odds_score(horse),
            'weight': self._calculate_weight_score(horse),
            'draw': self._calculate_draw_score(horse, race),
            'blinkers': self._calculate_blinkers_score(horse),
        }
    
    def _calculate_speed_score(self, horse: Horse, is_maiden: bool = False) -> float:
        """Overall speed assessment with maiden handling"""
        speed_rating = self._safe_float(getattr(horse, 'speed_rating', 50))
        current_mr = self._safe_float(getattr(horse, 'horse_merit', 0))
        
        self._debug(f"   🏁 Speed analysis: Rating={speed_rating}, MR={current_mr}, Maiden={is_maiden}")
        
        if is_maiden:
            # For maidens, rely more on speed rating and pedigree
            if speed_rating > 0:
                score = min(100, speed_rating * 1.2)  # Boost speed rating importance
                self._debug(f"   🏁 Maiden speed score: {score:.1f} (Rating: {speed_rating})")
                return score
            else:
                score = 45.0  # Default for maidens with no data
                self._debug(f"   🏁 Maiden default speed score: {score:.1f}")
                return score
        
        # Regular horse scoring
        if speed_rating > 0 and current_mr > 0:
            score = (speed_rating * 0.6) + (current_mr * 0.4)
            self._debug(f"   🏁 Speed score: {score:.1f} (Rating: {speed_rating}, MR: {current_mr})")
            return min(100, score)
        
        # Fallback if missing data
        if speed_rating > 0:
            self._debug(f"   🏁 Speed score (rating only): {speed_rating:.1f}")
            return min(100, speed_rating)
        
        self._debug(f"   🏁 Speed score (default): 50.0")
        return 50.0
    
    def _calculate_form_score(self, horse: Horse, is_maiden: bool = False) -> float:
        """Form assessment with maiden handling"""
        if is_maiden:
            # Maidens have no form history, use default
            score = 50.0
            self._debug(f"   🔥 Maiden form score: {score:.1f} (No form history)")
            return score
        
        best_mr = self._safe_float(getattr(horse, 'best_merit_rating', 0))
        current_mr = self._safe_float(getattr(horse, 'horse_merit', 0))
        
        self._debug(f"   🔥 Form analysis: Current MR={current_mr}, Best MR={best_mr}")
        
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
        
        self._debug(f"   🔥 Form score: {score:.1f}")
        return score
    
    def _calculate_best_mr_score(self, horse: Horse, is_maiden: bool = False) -> float:
        """Best merit rating score with maiden handling"""
        if is_maiden:
            # Maidens don't have established MRs
            score = 40.0  # Lower baseline for maidens
            self._debug(f"   🏆 Maiden best MR score: {score:.1f} (No established rating)")
            return score
        
        best_mr = self._safe_float(getattr(horse, 'best_merit_rating', 0))
        score = min(100, max(0, best_mr * 0.8))  # Scale MR to 0-100
        self._debug(f"   🏆 Best MR score: {score:.1f} (MR: {best_mr})")
        return score
    
    def _calculate_current_mr_score(self, horse: Horse, is_maiden: bool = False) -> float:
        """Current merit rating score with maiden handling"""
        if is_maiden:
            # Maidens don't have current MRs
            score = 40.0  # Lower baseline for maidens
            self._debug(f"   📊 Maiden current MR score: {score:.1f} (No current rating)")
            return score
        
        current_mr = self._safe_float(getattr(horse, 'horse_merit', 0))
        score = min(100, max(0, current_mr * 0.8))  # Scale MR to 0-100
        self._debug(f"   📊 Current MR score: {score:.1f} (MR: {current_mr})")
        return score
    
    def _calculate_class_score(self, horse: Horse, race: Race, is_maiden: bool = False) -> float:
        """Class suitability assessment with maiden handling"""
        if is_maiden:
            # Maidens are unproven, moderate penalty
            score = 45.0
            self._debug(f"   🎯 Maiden class score: {score:.1f} (Unproven)")
            return score
        
        current_mr = self._safe_float(getattr(horse, 'horse_merit', 0))
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
    
    def _calculate_intangible_score(self, horse: Horse, is_maiden: bool = False) -> float:
        """Intangible factors assessment with maiden handling"""
        score = 50.0
        
        if is_maiden:
            # Maidens get a fresh start bonus but inexperience penalty
            score = 55.0  # Slight bonus for potential
            self._debug(f"   🌟 Maiden intangible: {score:.1f} (Fresh potential)")
        
        # Blinkers can be a positive intangible
        if getattr(horse, 'blinkers', False):
            score = min(100, score + 10.0)
            self._debug(f"   ✨ Blinkers intangible bonus: +10.0")
        
        # Good J-T combo is intangible
        jt_score = self._safe_float(getattr(horse, 'jt_score', 50))
        if jt_score > 70:
            score = min(100, score + (jt_score - 70) * 0.3)
        
        self._debug(f"   🌟 Intangible score: {score:.1f}")
        return score

    def _calculate_overall_score(self, scores: Dict[str, float], is_maiden: bool = False) -> float:
        """Calculate weighted overall score with maiden adjustments"""
        if is_maiden:
            # Different weights for maidens - focus more on speed, pedigree, J-T combo
            weights = {
                'speed': 0.25,       # 25% - Speed rating (more important for maidens)
                'form': 0.10,        # 10% - Limited form history
                'class': 0.15,       # 15% - Class suitability
                'consistency': 0.20, # 20% - J-T combo consistency (more important)
                'value': 0.10,       # 10% - Odds value
                'physical': 0.10,    # 10% - Physical condition
                'intangible': 0.10,  # 10% - Intangible factors
            }
        else:
            # Regular horse weights
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

    # KEEP ALL YOUR EXISTING METHODS FOR:
    # _calculate_consistency_score, _calculate_jt_score, _calculate_value_score,
    # _calculate_odds_score, _calculate_physical_score, _calculate_weight_score,
    # _calculate_draw_score, _calculate_blinkers_score, _calculate_speed_rating_score,
    # _parse_odds, _parse_age, calculate_scores_for_race

    def calculate_scores_for_race(self, race: Race) -> List[HorseScore]:
        """Calculate scores for all horses in a race"""
        from racecard_02.models import Horse
        
        self._debug(f"📊 Calculating scores for Race {race.race_no}...")
        
        horses = Horse.objects.filter(race=race)
        horse_scores = []
        
        for horse in horses:
            try:
                score_record, created = self.create_score_record(horse, race)
                horse_scores.append(score_record)
                
                status = "Created" if created else "Updated"
                self._debug(f"   💾 {status} score for {horse.horse_name}: {score_record.overall_score:.1f}")
                
            except Exception as e:
                self._debug(f"   ❌ Error scoring {horse.horse_name}: {e}")
                continue
        
        self._debug(f"✅ Calculated scores for {len(horse_scores)} horses")
        return horse_scores

    # Add all your other existing methods here...