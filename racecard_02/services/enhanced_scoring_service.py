
# racecard_02/services/enhanced_scoring_service.py
import logging
from typing import Optional, Dict, Any, List

class EnhancedScoringService:
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback if debug_callback else print
        self.winning_threshold = 80
        self.magic_tips = []
    
    def set_magic_tips(self, magic_tips):
        """Set magic tips for scoring boost"""
        self.magic_tips = magic_tips or []
        self._debug(f"🎯 Magic Tips set: {self.magic_tips}")
    
    def _debug(self, message):
        """Safe debug output"""
        try:
            self.debug_callback(message)
        except:
            print(message)
    
    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert any value to float with default fallback"""
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            self._debug(f"⚠️ Could not convert value '{value}' to float, using default {default}")
            return default
    
    def is_maiden_horse(self, best_mr: Optional[float], current_mr: Optional[float]) -> bool:
        """
        BULLETPROOF maiden detection
        - Maiden can have current MR but typically has no/low best MR
        """
        try:
            # Handle None values explicitly
            if best_mr is None:
                return True  # No best MR = maiden
            
            # Convert to comparable types
            best_mr_safe = self.safe_float(best_mr, 0.0)
            
            # Maiden if best performance never reached winning threshold
            return best_mr_safe < self.winning_threshold
            
        except Exception as e:
            self._debug(f"⚠️ Maiden check error: {e}, defaulting to True")
            return True  # Conservative approach
    
    def calculate_speed_score(self, rating: Optional[float], mr: Optional[float]) -> float:
        """BULLETPROOF speed score calculation"""
        try:
            rating_val = self.safe_float(rating)
            mr_val = self.safe_float(mr)
            
            # Calculate weighted score - SAFE operations only
            speed_score = (rating_val * 0.7) + (mr_val * 0.3)
            return round(max(0, min(100, speed_score)), 2)
            
        except Exception as e:
            self._debug(f"⚠️ Speed score error - Rating: {rating}, MR: {mr}, Error: {e}")
            return 50.0  # Safe default
    
    def calculate_composite_score(self, horse_data: Dict[str, Any]) -> Dict[str, Any]:
        """BULLETPROOF comprehensive scoring"""
        try:
            # Extract with safe defaults
            horse_name = horse_data.get('name', 'Unknown')
            rating = horse_data.get('rating')
            current_mr = horse_data.get('current_mr')
            best_mr = horse_data.get('best_mr')
            speed_rating = horse_data.get('speed_rating')
            jt_score = horse_data.get('jt_score')
            weight = horse_data.get('weight')
            last_runs = horse_data.get('last_runs', [])
            
            self._debug(f"🐎 Scoring {horse_name}...")
            
            # 1. Maiden check (BULLETPROOF)
            is_maiden = self.is_maiden_horse(best_mr, current_mr)
            
            # 2. Speed score
            speed_score = self.calculate_speed_score(rating, current_mr)
            
            # 3. Form score from recent runs
            form_score = self.calculate_form_score(current_mr, last_runs)
            
            # 4. Consistency score
            consistency_score = self.calculate_consistency_score(best_mr, current_mr)
            
            # 5. Additional factors (all safe)
            speed_bonus = self.safe_float(speed_rating, 50.0) * 0.1
            jt_bonus = self.safe_float(jt_score, 50.0) * 0.1
            weight_factor = self.calculate_weight_factor(weight)
            
            # Composite calculation
            composite_score = (
                speed_score * 0.4 +
                form_score * 0.25 +
                consistency_score * 0.2 +
                speed_bonus * 0.1 +
                jt_bonus * 0.05
            )
            
            # Apply weight factor
            composite_score *= weight_factor
            
            # Magic Tips boost
            horse_no = horse_data.get('horse_no')
            if horse_no in self.magic_tips:
                composite_score *= 1.1  # 10% boost
                self._debug(f"   ✨ Magic Tips boost applied to {horse_name}")
            
            # Maiden penalty
            if is_maiden:
                composite_score *= 0.9  # 10% penalty
                self._debug(f"   🏇 Maiden penalty applied to {horse_name}")
            
            return {
                'horse_name': horse_name,
                'composite_score': round(composite_score, 2),
                'speed_score': speed_score,
                'form_score': form_score,
                'consistency_score': consistency_score,
                'is_maiden': is_maiden,
                'current_mr': self.safe_float(current_mr),
                'best_mr': self.safe_float(best_mr),
                'rating': self.safe_float(rating),
                'horse_no': horse_no
            }
            
        except Exception as e:
            self._debug(f"❌ CRITICAL scoring error for {horse_data.get('name', 'Unknown')}: {e}")
            # Return safe defaults
            return {
                'horse_name': horse_data.get('name', 'Unknown'),
                'composite_score': 0.0,
                'speed_score': 0.0,
                'form_score': 0.0,
                'consistency_score': 0.0,
                'is_maiden': True,
                'current_mr': 0.0,
                'best_mr': 0.0,
                'rating': 0.0,
                'horse_no': horse_data.get('horse_no'),
                'error': str(e)
            }
    
    def calculate_form_score(self, current_mr: Optional[float], last_runs: List) -> float:
        """Safe form score calculation"""
        try:
            current_mr_val = self.safe_float(current_mr)
            
            if not last_runs:
                return current_mr_val * 0.8
            
            # Calculate average of last 3 runs safely
            recent_scores = []
            for run in last_runs[:3]:
                mr = self.safe_float(run.get('merit_rating'))
                if mr > 0:
                    recent_scores.append(mr)
            
            if recent_scores:
                avg_recent = sum(recent_scores) / len(recent_scores)
                form_score = (current_mr_val * 0.6) + (avg_recent * 0.4)
            else:
                form_score = current_mr_val * 0.8
                
            return round(max(0, min(100, form_score)), 2)
            
        except Exception as e:
            self._debug(f"⚠️ Form score error: {e}")
            return self.safe_float(current_mr) * 0.8
    
    def calculate_consistency_score(self, best_mr: Optional[float], current_mr: Optional[float]) -> float:
        """Safe consistency score"""
        try:
            best_mr_val = self.safe_float(best_mr)
            current_mr_val = self.safe_float(current_mr)
            
            if best_mr_val <= 0:
                return 0.0
            
            consistency_ratio = current_mr_val / best_mr_val
            return round(min(consistency_ratio, 1.0) * 100, 2)
            
        except Exception as e:
            self._debug(f"⚠️ Consistency score error: {e}")
            return 0.0
    
    def calculate_weight_factor(self, weight: Optional[float]) -> float:
        """Safe weight adjustment"""
        try:
            weight_val = self.safe_float(weight, 57.0)
            
            # Normalize weight effect (lighter = better)
            base_weight = 57.0
            weight_diff = abs(weight_val - base_weight)
            
            # Factor: 1.0 for ideal weight, decreasing for heavier/lighter
            factor = max(0.8, 1.0 - (weight_diff * 0.02))
            return factor
            
        except Exception as e:
            self._debug(f"⚠️ Weight factor error: {e}")
            return 1.0
    
    def calculate_scores_for_race(self, race) -> List[Dict[str, Any]]:
        """Calculate scores for all horses in a race"""
        from racecard_02.models import Horse, Run
        
        self._debug(f"🏇 Calculating scores for Race {race.race_no}")
        
        horse_scores = []
        horses = Horse.objects.filter(race=race)
        
        for horse in horses:
            try:
                # Get last runs for form calculation
                last_runs = Run.objects.filter(horse=horse).order_by('-run_date')[:5]
                run_data = []
                for run in last_runs:
                    run_data.append({
                        'merit_rating': run.merit_rating,
                        'position': run.position,
                        'track': run.track,
                        'date': run.run_date
                    })
                
                horse_data = {
                    'name': horse.horse_name,
                    'horse_no': horse.horse_no,
                    'rating': horse.horse_merit,
                    'current_mr': horse.horse_merit,
                    'best_mr': horse.best_merit_rating,
                    'speed_rating': horse.speed_rating,
                    'jt_score': horse.jt_score,
                    'weight': horse.weight,
                    'last_runs': run_data
                }
                
                scores = self.calculate_composite_score(horse_data)
                horse_scores.append(scores)
                
                self._debug(
                    f"   ✅ {horse.horse_name}: "
                    f"Score={scores['composite_score']}, "
                    f"Maiden={scores['is_maiden']}, "
                    f"BestMR={scores['best_mr']}, "
                    f"CurrentMR={scores['current_mr']}"
                )
                
            except Exception as e:
                self._debug(f"❌ Error processing {horse.horse_name}: {e}")
                continue
        
        return horse_scores