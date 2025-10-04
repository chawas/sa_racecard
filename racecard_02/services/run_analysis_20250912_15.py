import json
import os
import re
from datetime import datetime
from typing import Dict, Optional, Tuple, Any, List
from django.conf import settings
from django.utils import timezone
from racecard_02.models import Run, Horse

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
    
    def analyze_horse_runs(self, horse: Horse) -> Dict[str, Any]:
        """Comprehensive analysis of a horse's past runs including class analysis"""
        self._log_debug(f"\n📊 ===== ANALYZING RUNS FOR {horse.horse_name} =====")
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]
        
        if not runs:
            self._log_debug("ℹ️ No past runs found for this horse")
            return self._get_empty_analysis()
        
        self._log_debug(f"📅 Found {len(runs)} recent runs:")
        
        # Initialize analysis data structures
        run_analyses = []
        total_score = 0
        
        for i, run in enumerate(runs, 1):
            run_class = run.race_class
            position = run.position
            self._log_debug(f"\n  🏇 Run {i}: {run.run_date} - {run_class} - Pos: {position}")
            
            # Run-level analysis (class + performance)
            run_analysis = self.calculate_run_score(run_class, position)
            run_analyses.append(run_analysis)
            total_score += run_analysis['run_score']
            self._log_debug(f"  → Final score: {run_analysis['run_score']:.2f}")
        
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
        
        # Compile comprehensive analysis
        analysis_result = {
            'run_analyses': run_analyses,
            'average_score': round(avg_score, 2),
            'best_performance': best_performance,
            'runs_analyzed': len(runs),
            'recent_class': run_analyses[0]['class_group'] if run_analyses else None,
            'recent_performance': run_analyses[0]['performance_score'] if run_analyses else 0,
            'horse_id': horse.id
        }
        
        self._log_debug(f"🏁 Comprehensive analysis completed")
        return analysis_result

    def _get_empty_analysis(self):
        return {
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'runs_analyzed': 0,
            'recent_class': None,
            'recent_performance': 0,
            'horse_id': None
        }