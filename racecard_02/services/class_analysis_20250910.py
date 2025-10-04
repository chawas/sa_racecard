# racecard_02/services/class_analysis.py
import json
import logging
import os
import re
from typing import Optional, Tuple, Dict, Any, List
from django.conf import settings

# Set up logger for the service
class_logger = logging.getLogger(__name__)

class ClassAnalysisService:
    
    def __init__(self, debug_callback=None):
        self._debug_callback = debug_callback
        self.class_groups = self._load_class_groups()
        self._log_debug("🔧 ClassAnalysisService initialized")

    def _log_debug(self, message):
        """Internal debug logging method"""
        if self._debug_callback and callable(self._debug_callback):
            self._debug_callback(message)
        # Also log to console for visibility
        print(f"CLASS ANALYSIS: {message}")
    
    def _load_class_groups(self):
        """Load class groups from JSON file with debug output"""
        try:
            groups_path = os.path.join(settings.BASE_DIR, 'racecard_02', 'data', 'class_weights.json')
            with open(groups_path, 'r') as f:
                data = json.load(f)
                self._log_debug(f"✅ Loaded class groups from JSON: {list(data['class_groups'].keys())}")
                return data['class_groups']
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            self._log_debug(f"⚠️ Could not load class groups: {e}. Using default groups.")
            return self._get_default_groups()
    
    def _get_default_groups(self):
        """Default class groups if JSON file not found"""
        self._log_debug("📋 Using default class groups")
        return {
            "Group 1": {"min_merit": 100, "max_merit": 120, "weight": 20, "equivalent_names": ["Group 1", "G1", "Classic", "Grade 1"]},
            "Group 2": {"min_merit": 90, "max_merit": 99, "weight": 18, "equivalent_names": ["Group 2", "G2", "Stakes", "Grade 2"]},
            "Group 3": {"min_merit": 80, "max_merit": 89, "weight": 16, "equivalent_names": ["Group 3", "G3", "Listed", "Grade 3"]},
            "Premier": {"min_merit": 70, "max_merit": 79, "weight": 14, "equivalent_names": ["Premier", "MR70+", "Feature", "Premier Handicap"]},
            "Middle": {"min_merit": 60, "max_merit": 69, "weight": 12, "equivalent_names": ["Middle", "MR60+", "Mddle", "Middle Stakes", "MR64"]},
            "Moderate": {"min_merit": 50, "max_merit": 59, "weight": 10, "equivalent_names": ["Moderate", "MR50+", "MR55", "Handicap"]},
            "Standard": {"min_merit": 40, "max_merit": 49, "weight": 8, "equivalent_names": ["Standard", "MR40+", "MR45", "Class 4"]},
            "Basic": {"min_merit": 30, "max_merit": 39, "weight": 6, "equivalent_names": ["Basic", "MR30+", "MR35", "Class 5"]},
            "Maiden": {"min_merit": 0, "max_merit": 29, "weight": 4, "equivalent_names": ["Maiden", "MP", "OM", "Novice", "Class 6"]}
        }
    
    def find_class_group(self, race_class: Optional[str]) -> Tuple[Optional[str], int]:
        """Find which group a race class belongs to with debug info"""
        if not race_class:
            self._log_debug("🔍 Class analysis: No race class provided")
            return None, 0
        
        race_class_upper = race_class.upper().strip()
        self._log_debug(f"🔍 Analyzing race class: '{race_class}' -> '{race_class_upper}'")
        
        # First, try to extract merit rating
        merit_match = re.search(r'MR\s*(\d+)', race_class_upper)
        if merit_match:
            merit_value = int(merit_match.group(1))
            self._log_debug(f"📊 Found merit rating: MR{merit_value}")
            
            for group_name, group_data in self.class_groups.items():
                if group_data['min_merit'] <= merit_value <= group_data['max_merit']:
                    self._log_debug(f"✅ Matched MR{merit_value} to group: {group_name} (weight: {group_data['weight']})")
                    return group_name, group_data['weight']
            self._log_debug(f"❌ MR{merit_value} doesn't match any group range")
        
        # Then try to match by equivalent names
        for group_name, group_data in self.class_groups.items():
            for equivalent_name in group_data['equivalent_names']:
                if equivalent_name.upper() in race_class_upper:
                    self._log_debug(f"✅ Matched '{equivalent_name}' to group: {group_name} (weight: {group_data['weight']})")
                    return group_name, group_data['weight']
        
        # Default to Maiden if no match found
        self._log_debug(f"⚠️ No specific match found for '{race_class}', defaulting to Maiden")
        return "Maiden", self.class_groups["Maiden"]["weight"]
    
    def calculate_run_score(self, race_class: Optional[str], position: Optional[str]) -> Dict[str, Any]:
        """Calculate a score for a single run with debug info"""
        self._log_debug(f"🎯 Calculating run score for class: '{race_class}', position: {position}")
        
        group_name, class_weight = self.find_class_group(race_class)
        self._log_debug(f"📦 Class group: {group_name}, Weight: {class_weight}")
        
        # Convert position to performance score
        try:
            if position and str(position).isdigit():
                pos = float(position)
                # Better performance scoring: 1st=100, 2nd=80, 3rd=60, etc.
                if pos == 1:
                    performance_score = 100
                elif pos == 2:
                    performance_score = 80
                elif pos == 3:
                    performance_score = 60
                elif pos <= 5:
                    performance_score = 40
                elif pos <= 10:
                    performance_score = 20
                else:
                    performance_score = 10
            else:
                performance_score = 30  # Default for non-finishers or unknown positions
            self._log_debug(f"📈 Position {position} -> performance score: {performance_score}")
        except (ValueError, TypeError):
            performance_score = 30
            self._log_debug(f"⚠️ Could not parse position '{position}', using default: 30")
        
        # Combine class weight and performance (weighted average)
        run_score = (class_weight * 0.7) + (performance_score * 0.3)
        
        self._log_debug(f"🧮 Run score calculation:")
        self._log_debug(f"   Class component: {class_weight} × 0.7 = {class_weight * 0.7:.2f}")
        self._log_debug(f"   Performance component: {performance_score} × 0.3 = {performance_score * 0.3:.2f}")
        self._log_debug(f"   Final run score: {run_score:.2f}")
        
        return {
            'class_group': group_name,
            'class_weight': class_weight,
            'performance_score': performance_score,
            'run_score': round(run_score, 2),
            'position': position
        }
    
    def analyze_horse_class_history(self, horse) -> Dict[str, Any]:
        """Analyze a horse's class history with detailed debug"""
        self._log_debug(f"\n📊 ===== ANALYZING CLASS HISTORY FOR {getattr(horse, 'horse_name', 'Unknown')} =====")
        
        # Try to import Run model
        try:
            from racecard_02.models import Run
            runs = Run.objects.filter(horse=horse).order_by('-run_date')[:6]  # Last 6 runs
        except ImportError:
            self._log_debug("❌ Could not import Run model")
            return self._get_empty_analysis()
        except Exception as e:
            self._log_debug(f"❌ Error querying runs: {e}")
            return self._get_empty_analysis()
        
        if not runs:
            self._log_debug("ℹ️ No past runs found for this horse")
            return self._get_empty_analysis()
        
        self._log_debug(f"📅 Found {len(runs)} recent runs:")
        
        run_analyses = []
        total_score = 0
        
        for i, run in enumerate(runs, 1):
            run_class = getattr(run, 'race_class', 'Unknown')
            position = getattr(run, 'position', None)
            self._log_debug(f"\n  🏇 Run {i}: {getattr(run, 'run_date', 'Unknown')} - {run_class} - Pos: {position}")
            
            analysis = self.calculate_run_score(run_class, position)
            run_analyses.append(analysis)
            total_score += analysis['run_score']
            self._log_debug(f"  → Final score: {analysis['run_score']:.2f}")
        
        avg_score = total_score / len(runs) if runs else 0
        self._log_debug(f"\n📈 Average run score: {total_score:.2f} / {len(runs)} = {avg_score:.2f}")
        
        # Find best performance
        best_performance = None
        for analysis in run_analyses:
            if analysis['performance_score'] >= 60:  # Good performance (top 3)
                if not best_performance or analysis['class_weight'] > best_performance['class_weight']:
                    best_performance = analysis
        
        if best_performance:
            self._log_debug(f"⭐ Best performance: {best_performance['class_group']} (weight: {best_performance['class_weight']}), Score: {best_performance['run_score']:.2f}")
        else:
            self._log_debug(f"ℹ️ No standout best performance found")
        
        return {
            'run_analyses': run_analyses,
            'average_score': round(avg_score, 2),
            'best_performance': best_performance,
            'runs_analyzed': len(runs),
            'recent_class': run_analyses[0]['class_group'] if run_analyses else None,
            'recent_performance': run_analyses[0]['performance_score'] if run_analyses else 0
        }
    
    def calculate_class_suitability(self, horse, race) -> float:
        """Calculate class suitability score with proper error handling"""
        try:
            # Input validation
            if not hasattr(horse, 'horse_name'):
                error_msg = f"Invalid horse object: {horse}"
                self._log_debug(f"❌ {error_msg}")
                return 50.0
            
            if not hasattr(race, 'race_class'):
                error_msg = f"Invalid race object: {race}"
                self._log_debug(f"❌ {error_msg}")
                return 50.0
            
            # Get current race class and weight
            race_class = getattr(race, 'race_class', '')
            current_group, current_weight = self.find_class_group(race_class)
            
            # Analyze horse's class history
            class_history = self.analyze_horse_class_history(horse)
            
            if class_history['runs_analyzed'] == 0:
                self._log_debug("📊 No class history found, using base suitability based on current race class")
                # Base suitability on current race class weight
                suitability = current_weight * 2.5  # Convert weight (4-20) to score (10-50)
                self._log_debug(f"📊 Base suitability from current class: {suitability:.2f}")
                return min(100, max(0, suitability))
            
            # Base suitability based on average performance
            suitability = class_history['average_score']
            self._log_debug(f"📊 Base suitability (average score): {suitability:.2f}")
            
            # Adjust based on current race class
            suitability = suitability * 0.7 + (current_weight * 2.5 * 0.3)
            self._log_debug(f"📊 Adjusted for current class: {suitability:.2f}")
            
            # Bonus if horse has proven ability at this level or higher
            if class_history['best_performance']:
                best_weight = class_history['best_performance']['class_weight']
                self._log_debug(f"📊 Best performance weight: {best_weight}, Current race weight: {current_weight}")
                
                if best_weight >= current_weight:
                    old_suitability = suitability
                    suitability = min(100, suitability * 1.2)  # 20% bonus
                    self._log_debug(f"🎯 Bonus: Proven ability at this level or higher (+20%)")
                    self._log_debug(f"   {old_suitability:.2f} → {suitability:.2f}")
                else:
                    # Small penalty for moving up significantly
                    if current_weight > best_weight + 4:
                        old_suitability = suitability
                        suitability *= 0.9  # 10% penalty
                        self._log_debug(f"⚠️ Penalty: Moving up significantly in class (-10%)")
                        self._log_debug(f"   {old_suitability:.2f} → {suitability:.2f}")
            
            final_score = min(100, max(0, suitability))
            self._log_debug(f"🏁 Final class suitability score: {final_score:.2f}")
            
            return float(final_score)
            
        except Exception as e:
            error_msg = f"Error in class suitability calculation for {getattr(horse, 'horse_name', 'unknown')}: {e}"
            self._log_debug(f"❌ {error_msg}")
            class_logger.error(error_msg, exc_info=True)
            return 50.0  # Fallback score

    def calculate_form_score(self, horse) -> float:
        """Calculate form score based on recent class performance"""
        try:
            class_history = self.analyze_horse_class_history(horse)
            
            if class_history['runs_analyzed'] == 0:
                self._log_debug("No class history for form calculation")
                return 50.0
            
            # Use recent performance as form indicator
            if class_history['recent_performance'] > 0:
                form_score = class_history['recent_performance']  # Recent performance score
                self._log_debug(f"Form score from recent performance: {form_score:.2f}")
            else:
                form_score = class_history['average_score']  # Fallback to average
                self._log_debug(f"Form score from average: {form_score:.2f}")
            
            # Apply trend adjustment
            trend = self.get_class_trend(horse)
            if trend == "improving":
                form_score = min(100, form_score * 1.1)
                self._log_debug(f"📈 Form improving bonus: +10%")
            elif trend == "declining":
                form_score = max(0, form_score * 0.9)
                self._log_debug(f"📉 Form declining penalty: -10%")
            
            return float(form_score)
            
        except Exception as e:
            self._log_debug(f"Error calculating form score: {e}")
            return 50.0

    def get_class_trend(self, horse) -> str:
        """Analyze if horse is moving up or down in class"""
        self._log_debug(f"\n📈 Analyzing class trend for {getattr(horse, 'horse_name', 'Unknown')}")
        class_history = self.analyze_horse_class_history(horse)
        
        if class_history['runs_analyzed'] < 2:
            self._log_debug("ℹ️ Not enough runs to determine trend, returning 'stable'")
            return "stable"
        
        # Get average class weight of last 2 runs vs previous runs
        recent_runs = class_history['run_analyses'][:2]
        previous_runs = class_history['run_analyses'][2:]
        
        if not previous_runs:
            self._log_debug("ℹ️ Not enough previous runs for comparison")
            return "stable"
        
        recent_avg = sum(run['class_weight'] for run in recent_runs) / len(recent_runs)
        previous_avg = sum(run['class_weight'] for run in previous_runs) / len(previous_runs)
        
        self._log_debug(f"📊 Recent avg class weight: {recent_avg:.2f}, Previous avg: {previous_avg:.2f}")
        
        if recent_avg > previous_avg + 2:
            self._log_debug("📈 Trend: Moving up in class")
            return "improving"
        elif recent_avg < previous_avg - 2:
            self._log_debug("📉 Trend: Moving down in class")
            return "declining"
        else:
            self._log_debug("➡️ Trend: Stable class level")
            return "stable"
    
    def _get_empty_analysis(self) -> Dict[str, Any]:
        return {
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'runs_analyzed': 0,
            'recent_class': None,
            'recent_performance': 0
        }
    
    def get_class_weight(self, race_class: Optional[str]) -> int:
        """Get the weight for a given race class"""
        self._log_debug(f"⚖️ Getting class weight for: '{race_class}'")
        _, weight = self.find_class_group(race_class)
        self._log_debug(f"⚖️ Weight: {weight}")
        return weight