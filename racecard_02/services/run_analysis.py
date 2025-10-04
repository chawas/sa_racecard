import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, List
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Avg, Count, Max, Min
from racecard_02.models import Run, Horse, Race

class RunAnalysisService:
    
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback
        self.class_groups = self._load_class_groups()
        self._log_debug("🔧 RunAnalysisService initialized with Class Analysis")
    
    def _log_debug(self, message):
        """Internal debug logging method"""
        if self.debug_callback and callable(self.debug_callback):
            self.debug_callback(message)
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
    
    def calculate_class_score(self, horse: Horse, race: Race) -> float:
        """Calculate class suitability score based on horse's history vs current race"""
        self._log_debug(f"\n🎯 Calculating class score for {horse.horse_name} in {race.race_class}")
        
        try:
            # Get current race class weight
            current_group, current_weight = self.find_class_group(race.race_class)
            self._log_debug(f"📊 Current race: {current_group} (weight: {current_weight})")
            
            # Get horse's past runs
            runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]
            
            if not runs:
                # No past runs - base score on current class
                base_score = current_weight * 2.5  # Convert to 0-100 scale
                self._log_debug(f"📭 No past runs, using base score: {base_score:.1f}")
                return min(100, max(0, base_score))
            
            # Analyze past performances
            past_performances = []
            for run in runs:
                run_group, run_weight = self.find_class_group(run.race_class)
                position = self._parse_position(run.position)
                
                if position and position > 0:
                    performance_score = self._calculate_performance_score(position)
                    weighted_score = (run_weight * 0.7) + (performance_score * 0.3)
                    past_performances.append({
                        'weight': run_weight,
                        'performance': performance_score,
                        'score': weighted_score
                    })
            
            if not past_performances:
                base_score = current_weight * 2.5
                self._log_debug(f"📊 No valid performances, using base score: {base_score:.1f}")
                return min(100, max(0, base_score))
            
            # Calculate average past performance
            avg_past_score = sum(p['score'] for p in past_performances) / len(past_performances)
            self._log_debug(f"📈 Average past performance score: {avg_past_score:.1f}")
            
            # Compare with current class
            current_class_score = current_weight * 2.5
            
            if avg_past_score >= current_class_score:
                # Horse has performed well at this level or higher
                class_score = min(100, avg_past_score * 1.1)  # 10% bonus
                self._log_debug(f"✅ Horse proven at this level: {class_score:.1f} (+10% bonus)")
            else:
                # Horse moving up in class
                class_score = max(0, avg_past_score * 0.9)  # 10% penalty
                self._log_debug(f"⚠️ Horse moving up in class: {class_score:.1f} (-10% penalty)")
            
            return float(class_score)
            
        except Exception as e:
            self._log_debug(f"❌ Error calculating class score: {e}")
            return 50.0
    
    def calculate_form_score(self, horse: Horse) -> float:
        """Calculate form score based on recent performances"""
        self._log_debug(f"\n🔥 Calculating form score for {horse.horse_name}")
        
        try:
            # Get recent runs (last 6 months)
            six_months_ago = timezone.now().date() - timedelta(days=180)
            runs = Run.objects.filter(
                horse=horse, 
                run_date__gte=six_months_ago
            ).order_by('-run_date')[:10]
            
            if not runs:
                self._log_debug("📭 No recent runs found")
                return 50.0
            
            # Calculate performance scores for each run
            performance_scores = []
            for i, run in enumerate(runs):
                position = self._parse_position(run.position)
                if position and position > 0:
                    performance_score = self._calculate_performance_score(position)
                    # Weight recent runs more heavily
                    weight = 1.0 / (i + 1)  # Most recent gets weight 1, next 0.5, etc.
                    performance_scores.append(performance_score * weight)
                    self._log_debug(f"🏇 Run {i+1}: Pos {position} -> Score {performance_score} (Weight: {weight:.2f})")
            
            if not performance_scores:
                self._log_debug("📊 No valid positions in recent runs")
                return 50.0
            
            # Calculate weighted average
            total_weight = sum(1.0 / (i + 1) for i in range(len(performance_scores)))
            form_score = sum(performance_scores) / total_weight
            
            # Apply trend analysis
            trend = self._analyze_form_trend(runs)
            if trend == "improving":
                form_score = min(100, form_score * 1.15)
                self._log_debug(f"📈 Form improving: {form_score:.1f} (+15% bonus)")
            elif trend == "declining":
                form_score = max(0, form_score * 0.85)
                self._log_debug(f"📉 Form declining: {form_score:.1f} (-15% penalty)")
            else:
                self._log_debug(f"➡️ Form stable: {form_score:.1f}")
            
            return float(form_score)
            
        except Exception as e:
            self._log_debug(f"❌ Error calculating form score: {e}")
            return 50.0
    
    def _analyze_form_trend(self, runs: List[Run]) -> str:
        """Analyze if form is improving or declining"""
        if len(runs) < 3:
            return "stable"
        
        # Get performance scores for last 3 runs vs previous 3
        recent_scores = []
        previous_scores = []
        
        for i, run in enumerate(runs[:6]):  # Analyze up to 6 most recent runs
            position = self._parse_position(run.position)
            if position and position > 0:
                score = self._calculate_performance_score(position)
                if i < 3:
                    recent_scores.append(score)
                else:
                    previous_scores.append(score)
        
        if not recent_scores or not previous_scores:
            return "stable"
        
        avg_recent = sum(recent_scores) / len(recent_scores)
        avg_previous = sum(previous_scores) / len(previous_scores)
        
        if avg_recent > avg_previous + 15:
            return "improving"
        elif avg_recent < avg_previous - 15:
            return "declining"
        else:
            return "stable"
    
    def _calculate_performance_score(self, position: int) -> float:
        """Calculate performance score based on finishing position"""
        if position == 1:
            return 100.0
        elif position == 2:
            return 85.0
        elif position == 3:
            return 70.0
        elif position <= 5:
            return 50.0
        elif position <= 10:
            return 30.0
        else:
            return 10.0
    
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
                # Handle DNF, DNS, etc.
                if position.upper() in ['DNF', 'DNS', 'WD', 'SCR']:
                    return 20  # Penalty for non-finishers
        except (ValueError, TypeError):
            pass
        
        return None
    
    def get_horse_run_stats(self, horse: Horse) -> Dict[str, Any]:
        """Get comprehensive run statistics for a horse"""
        self._log_debug(f"\n📊 Getting run stats for {horse.horse_name}")
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')
        
        stats = {
            'total_runs': runs.count(),
            'recent_runs': runs.filter(run_date__gte=timezone.now().date() - timedelta(days=180)).count(),
            'best_position': runs.aggregate(Min('position'))['position__min'],
            'avg_position': runs.aggregate(Avg('position'))['position__avg'],
            'win_count': runs.filter(position='1').count(),
            'place_count': runs.filter(position__in=['1', '2', '3']).count(),
            'last_run_date': runs.first().run_date if runs else None,
        }
        
        self._log_debug(f"📈 Stats: {stats}")
        return stats
    
    def analyze_horse_class_history(self, horse: Horse) -> Dict[str, Any]:
        """Analyze a horse's class history"""
        self._log_debug(f"\n📊 Analyzing class history for {horse.horse_name}")
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]
        
        if not runs:
            return self._get_empty_class_analysis()
        
        class_analysis = {
            'runs_analyzed': len(runs),
            'class_breakdown': {},
            'recent_performance': self._calculate_recent_performance(runs),
            'best_class_performance': self._find_best_class_performance(runs),
        }
        
        # Analyze class distribution
        for run in runs:
            class_group, _ = self.find_class_group(run.race_class)
            if class_group:
                if class_group not in class_analysis['class_breakdown']:
                    class_analysis['class_breakdown'][class_group] = 0
                class_analysis['class_breakdown'][class_group] += 1
        
        self._log_debug(f"📊 Class analysis: {class_analysis}")
        return class_analysis
    
    def _calculate_recent_performance(self, runs: List[Run]) -> float:
        """Calculate recent performance average"""
        if not runs:
            return 0.0
        
        recent_runs = runs[:3]  # Last 3 runs
        scores = []
        
        for run in recent_runs:
            position = self._parse_position(run.position)
            if position and position > 0:
                scores.append(self._calculate_performance_score(position))
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _find_best_class_performance(self, runs: List[Run]) -> Dict[str, Any]:
        """Find the best class performance"""
        best_performance = None
        
        for run in runs:
            position = self._parse_position(run.position)
            if position and position == 1:  # Only consider wins
                class_group, class_weight = self.find_class_group(run.race_class)
                performance_score = self._calculate_performance_score(position)
                
                if not best_performance or class_weight > best_performance['class_weight']:
                    best_performance = {
                        'class_group': class_group,
                        'class_weight': class_weight,
                        'performance_score': performance_score,
                        'date': run.run_date,
                        'position': position
                    }
        
        return best_performance or {}
    
    def _get_empty_class_analysis(self):
        return {
            'runs_analyzed': 0,
            'class_breakdown': {},
            'recent_performance': 0,
            'best_class_performance': {}
        }