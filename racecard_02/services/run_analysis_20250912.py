import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
from django.utils import timezone
from django.db.models import Q
from django.conf import settings

class RunAnalysisService:
    
    def __init__(self, debug_callback=None):
        self._debug_callback = debug_callback
        self.class_groups = self._load_class_groups()
        self._log_debug("🔧 RunAnalysisService initialized with Class Analysis")
    
    def _log_debug(self, message):
        """Internal debug logging method"""
        if self._debug_callback and callable(self._debug_callback):
            self._debug_callback(message)
        # Also log to console for visibility
        print(f"RUN ANALYSIS: {message}")
    
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
    
    def analyze_horse_runs(self, horse):
        """Comprehensive analysis of a horse's past runs including class analysis"""
        self._log_debug(f"\n📊 ===== ANALYZING RUNS FOR {getattr(horse, 'horse_name', 'Unknown')} =====")
        
        # Try to import Run model
        try:
            from racecard_02.models import Run
            runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]  # Last 10 runs
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
        
        # Initialize analysis data structures
        positions = []
        margins = []
        distances = []
        class_weights = []
        days_since = []
        performance_scores = []
        run_analyses = []
        total_score = 0
        
        current_date = timezone.now().date()
        
        for i, run in enumerate(runs, 1):
            run_class = getattr(run, 'race_class', 'Unknown')
            position = getattr(run, 'position', None)
            self._log_debug(f"\n  🏇 Run {i}: {getattr(run, 'run_date', 'Unknown')} - {run_class} - Pos: {position}")
            
            # Run-level analysis (class + performance)
            run_analysis = self.calculate_run_score(run_class, position)
            run_analyses.append(run_analysis)
            total_score += run_analysis['run_score']
            self._log_debug(f"  → Final score: {run_analysis['run_score']:.2f}")
            
            # Position analysis
            pos = self._parse_position(position)
            if pos is not None:
                positions.append(pos)
                performance_scores.append(self._calculate_performance_score(pos))
            
            # Margin analysis
            margin = self._parse_margin(getattr(run, 'margin', None))
            if margin is not None:
                margins.append(margin)
            
            # Distance analysis
            distance = self._parse_distance(getattr(run, 'distance', None))
            if distance is not None:
                distances.append(distance)
            
            # Class weight (from class analysis)
            class_weights.append(run_analysis['class_weight'])
            
            # Days since run
            if hasattr(run, 'run_date') and run.run_date:
                try:
                    days = (current_date - run.run_date).days
                    days_since.append(days)
                except:
                    pass
        
        # Calculate overall metrics
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
        
        # Calculate form and class trends
        class_trend = self._get_class_trend(run_analyses)
        performance_trend = self._calculate_performance_trend(performance_scores)
        
        # Compile comprehensive analysis
        analysis_result = {
            # Run performance metrics
            'average_position': self._safe_average(positions),
            'average_margin': self._safe_average(margins),
            'recent_distance': self._most_common_value(distances),
            'days_since_last_run': min(days_since) if days_since else None,
            'form_rating': self._calculate_form_rating(positions),
            'consistency': self._calculate_consistency(positions),
            'performance_trend': performance_trend,
            
            # Class analysis metrics
            'average_class': self._safe_average(class_weights),
            'class_trend': class_trend,
            'run_analyses': run_analyses,
            'average_score': round(avg_score, 2),
            'best_performance': best_performance,
            'recent_class': run_analyses[0]['class_group'] if run_analyses else None,
            'recent_performance': run_analyses[0]['performance_score'] if run_analyses else 0,
            
            # Metadata
            'runs_analyzed': len(runs),
            'horse_id': getattr(horse, 'id', None)
        }
        
        self._log_debug(f"🏁 Comprehensive analysis completed")
        return analysis_result
    
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

    def analyze_horse_class_history(self, horse) -> Dict[str, Any]:
        """Analyze a horse's class history with detailed debug"""
        self._log_debug(f"\n📊 ===== ANALYZING CLASS HISTORY FOR {getattr(horse, 'horse_name', 'Unknown')} =====")
        
        # Get runs for the horse
        runs = self._get_horse_runs(horse)
        
        if not runs:
            self._log_debug("ℹ️ No past runs found for this horse")
            return self._get_empty_class_analysis()
        
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
    
    def get_class_trend(self, horse) -> str:
        """Analyze if horse is moving up or down in class"""
        self._log_debug(f"\n📈 Analyzing class trend for {getattr(horse, 'horse_name', 'Unknown')}")
        class_history = self.analyze_horse_class_history(horse)
        
        if class_history['runs_analyzed'] < 2:
            self._log_debug("ℹ️ Not enough runs to determine trend, returning 'stable'")
            return "stable"
        
        return self._get_class_trend(class_history['run_analyses'])
    
    def _get_class_trend(self, run_analyses):
        """Internal method to calculate class trend from run analyses"""
        if len(run_analyses) < 2:
            return "stable"
        
        # Get average class weight of last 2 runs vs previous runs
        recent_runs = run_analyses[:2]
        previous_runs = run_analyses[2:]
        
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
    
    def get_class_weight(self, race_class: Optional[str]) -> int:
        """Get the weight for a given race class"""
        self._log_debug(f"⚖️ Getting class weight for: '{race_class}'")
        _, weight = self.find_class_group(race_class)
        self._log_debug(f"⚖️ Weight: {weight}")
        return weight
    
    def _get_horse_runs(self, horse):
        """Get runs for the horse"""
        from racecard_02.models import Run, Horse
        
        try:
            if hasattr(horse, 'id') and horse.id:
                return Run.objects.filter(horse=horse).order_by('-run_date')[:6]  # Last 6 runs for class analysis
            else:
                horse_name = getattr(horse, 'horse_name', str(horse))
                horse_obj = Horse.objects.filter(horse_name=horse_name).first()
                if horse_obj:
                    return Run.objects.filter(horse=horse_obj).order_by('-run_date')[:6]
                return []
        except Exception as e:
            self._log_debug(f"DEBUG: Error getting runs: {e}")
            return []
    
    # Helper methods from the original RunAnalysisService
    def _parse_position(self, position):
        """Parse position value"""
        if position is None:
            return None
        
        try:
            if isinstance(position, str):
                # Handle DNF, DNS, etc.
                if position.upper() in ['DNF', 'DNS', 'WD', 'SCR']:
                    return 20  # Penalty for non-finishers
                elif position.isdigit():
                    return float(position)
            elif isinstance(position, (int, float)):
                return float(position)
        except:
            pass
        return None
    
    def _parse_distance(self, distance):
        """Parse distance value"""
        if not distance:
            return None
        
        try:
            distance_str = str(distance)
            # Extract numeric distance (e.g., "1200m" -> 1200)
            match = re.search(r'\d+', distance_str)
            if match:
                return int(match.group())
        except:
            pass
        return None
    
    def _calculate_performance_score(self, position):
        """Calculate performance score (1st=100, 2nd=80, etc.)"""
        if position is None:
            return 50
        
        try:
            # Better scoring: 1st=100, 2nd=85, 3rd=70, etc.
            if position <= 1:
                return 100
            elif position <= 3:
                return 100 - (position * 15)
            else:
                return max(10, 70 - (position * 5))
        except:
            return 50
    
    def _parse_margin(self, margin_text):
        """Parse margin text into numeric value"""
        if not margin_text:
            return None
            
        try:
            margin_text = str(margin_text).strip().upper()
            
            # Common margin abbreviations
            margin_map = {
                'DH': 0.0, 'DEAD HEAT': 0.0,
                'NSE': 0.05, 'NOSE': 0.05,
                'SH': 0.1, 'SHORT HEAD': 0.1,
                'HD': 0.2, 'HEAD': 0.2,
                'NK': 0.3, 'NECK': 0.3,
                'DIST': 10.0, 'DISTANCE': 10.0
            }
            
            if margin_text in margin_map:
                return margin_map[margin_text]
            
            # Try to parse numeric margin
            margin_text = re.sub(r'[^\d.]', '', margin_text)
            if margin_text:
                return float(margin_text)
                
        except:
            pass
        return None
    
    def _calculate_form_rating(self, positions):
        """Calculate form rating with better weighting"""
        if not positions:
            return 0
        
        try:
            # Weight recent runs more heavily
            weighted_sum = 0
            total_weight = 0
            
            for i, pos in enumerate(positions):
                weight = 0.9 ** i  # More emphasis on recent runs
                weighted_sum += pos * weight
                total_weight += weight
            
            return round(weighted_sum / total_weight, 2)
        except:
            return round(sum(positions) / len(positions), 2) if positions else 0
    
    def _calculate_consistency(self, positions):
        """Calculate consistency percentage"""
        if not positions or len(positions) < 2:
            return 0
        
        try:
            avg_position = sum(positions) / len(positions)
            # Count runs within 2 positions of average
            within_range = sum(1 for p in positions if abs(p - avg_position) <= 2)
            
            return round((within_range / len(positions)) * 100, 1)
        except:
            return 0
    
    def _calculate_performance_trend(self, performance_scores):
        """Calculate performance trend"""
        if not performance_scores or len(performance_scores) < 3:
            return "stable"
        
        try:
            # Use weighted average of last 3 runs vs previous 3
            recent_avg = sum(performance_scores[:3]) / min(3, len(performance_scores))
            previous_avg = sum(performance_scores[3:6]) / min(3, len(performance_scores[3:6])) if len(performance_scores) > 3 else recent_avg
            
            if recent_avg > previous_avg + 20:
                return "improving_strong"
            elif recent_avg > previous_avg + 10:
                return "improving"
            elif recent_avg < previous_avg - 20:
                return "declining_strong"
            elif recent_avg < previous_avg - 10:
                return "declining"
            else:
                return "stable"
        except:
            return "stable"
    
    def _safe_average(self, values):
        """Calculate average safely"""
        valid_values = [v for v in values if v is not None]
        return round(sum(valid_values) / len(valid_values), 2) if valid_values else None
    
    def _most_common_value(self, values):
        """Get most common value"""
        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None
        return max(set(valid_values), key=valid_values.count)
    
    def _get_empty_analysis(self):
        return {
            'average_position': None,
            'average_margin': None,
            'recent_distance': None,
            'days_since_last_run': None,
            'form_rating': 0,
            'consistency': 0,
            'performance_trend': "stable",
            'average_class': None,
            'class_trend': "stable",
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'recent_class': None,
            'recent_performance': 0,
            'runs_analyzed': 0,
            'horse_id': None
        }
    
    def _get_empty_class_analysis(self):
        return {
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'runs_analyzed': 0,
            'recent_class': None,
            'recent_performance': 0
        }