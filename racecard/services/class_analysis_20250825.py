# racecard/services/class_analysis.py
import json
import os
import re
from django.conf import settings

class ClassAnalysisService:
    
    def __init__(self):
        self.class_weights = self._load_class_weights()
    
    def _load_class_weights(self):
        """Load class weights from JSON file"""
        weights_path = os.path.join(settings.BASE_DIR, 'racecard', 'data', 'class_weights.json')
        try:
            with open(weights_path, 'r') as f:
                data = json.load(f)
                return {cls['abbreviation']: cls for cls in data['classes']}
        except FileNotFoundError:
            return self._get_default_weights()
        except json.JSONDecodeError:
            return self._get_default_weights()
    
    def _get_default_weights(self):
        """Default weights if JSON file not found"""
        return {
            'MP': {'name': 'Maiden Plate', 'weight': 1},
            'MP-F': {'name': 'Maiden Plate (Fillies)', 'weight': 2},
            'OM': {'name': 'Open Maiden', 'weight': 3},
            'Juv': {'name': 'Juvenile', 'weight': 4},
            'Cl6': {'name': 'Class 6', 'weight': 5},
            'Cl5': {'name': 'Class 5', 'weight': 6},
            'Cl4': {'name': 'Class 4', 'weight': 7},
            'Cl3': {'name': 'Class 3', 'weight': 8},
            'Cl2': {'name': 'Class 2', 'weight': 9},
            'Cl1': {'name': 'Class 1', 'weight': 10},
            'L': {'name': 'Listed', 'weight': 11},
            'G3': {'name': 'Group 3', 'weight': 12},
            'G2': {'name': 'Group 2', 'weight': 13},
            'G1': {'name': 'Group 1', 'weight': 14},
            'Hcp': {'name': 'Handicap', 'weight': 15},
            'MR': {'name': 'Merit Rated', 'weight': 16},
            'BM': {'name': 'Benchmark', 'weight': 17},
            'Stk': {'name': 'Stakes', 'weight': 18},
            'Cond': {'name': 'Conditions', 'weight': 19},
            'Allow': {'name': 'Allowance', 'weight': 20},
            'App': {'name': 'Apprentice', 'weight': 21},
            'Nov': {'name': 'Novice', 'weight': 22},
            'Grad': {'name': 'Graduation', 'weight': 23},
            'Rest': {'name': 'Restricted', 'weight': 24}
        }
    
    def get_class_weight(self, race_class):
        """Get weight for a given race class with better matching"""
        if not race_class:
            return 0
        
        race_class = race_class.upper().strip()
        
        # Try exact abbreviation matches first
        for abbrev, cls_data in self.class_weights.items():
            if abbrev.upper() == race_class:
                return cls_data['weight']
        
        # Try partial matches
        for abbrev, cls_data in self.class_weights.items():
            if abbrev.upper() in race_class:
                return cls_data['weight']
        
        # Try name matches
        for cls_data in self.class_weights.values():
            if cls_data['name'].upper() in race_class:
                return cls_data['weight']
        
        # Special handling for merit rated races
        merit_match = re.search(r'MR\s*(\d+)', race_class)
        if merit_match:
            merit_value = int(merit_match.group(1))
            return max(16, min(25, merit_value / 2 + 10))  # Scale based on MR value
        
        # Default for unknown classes
        return 25
    
    def analyze_horse_class_history(self, horse):
        """Analyze a horse's class history with performance context"""
        from racecard.models import Run
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')[:4]
        
        if not runs:
            return {
                'average_class_weight': 0,
                'class_consistency': 0,
                'highest_class': 0,
                'lowest_class': 0,
                'runs_analyzed': 0,
                'performance_score': 0
            }
        
        class_weights = []
        performance_scores = []
        
        for run in runs:
            if run.race_class:
                weight = self.get_class_weight(run.race_class)
                class_weights.append(weight)
                
                # Calculate performance score (better position = higher score)
                try:
                    position = float(run.position) if run.position and run.position.isdigit() else 10
                    performance_score = max(0, 100 - (position * 10))  # 1st=90, 2nd=80, etc.
                    performance_scores.append(performance_score)
                except:
                    performance_scores.append(50)  # Default for unknown positions
        
        if not class_weights:
            return {
                'average_class_weight': 0,
                'class_consistency': 0,
                'highest_class': 0,
                'lowest_class': 0,
                'runs_analyzed': 0,
                'performance_score': 0
            }
        
        # Calculate metrics
        avg_weight = sum(class_weights) / len(class_weights)
        max_weight = max(class_weights)
        min_weight = min(class_weights)
        avg_performance = sum(performance_scores) / len(performance_scores) if performance_scores else 50
        
        # Consistency (lower std dev = more consistent)
        variance = sum((w - avg_weight) ** 2 for w in class_weights) / len(class_weights)
        consistency = max(0, 100 - (variance * 10))
        
        return {
            'average_class_weight': avg_weight,
            'class_consistency': consistency,
            'highest_class': max_weight,
            'lowest_class': min_weight,
            'runs_analyzed': len(class_weights),
            'performance_score': avg_performance,
            'recent_classes': class_weights,
            'recent_performances': performance_scores
        }
    
    def calculate_class_suitability(self, horse, current_race):
        """Calculate how suitable the horse is for the current race class"""
        # Get current race class weight
        current_class_weight = self.get_class_weight(current_race.race_class)
        
        # Analyze horse's class history
        class_history = self.analyze_horse_class_history(horse)
        
        if class_history['runs_analyzed'] == 0:
            return 50  # Neutral score for no history
        
        # Calculate suitability score (0-100)
        avg_historical = class_history['average_class_weight']
        performance_score = class_history['performance_score']
        
        # Horse is suited if current class is similar to historical average
        class_difference = abs(current_class_weight - avg_historical)
        
        # Score based on difference (lower difference = higher score)
        suitability = max(0, 100 - (class_difference * 2))
        
        # Adjust based on consistency
        consistency_factor = class_history['class_consistency'] / 100
        suitability *= consistency_factor
        
        # Adjust based on recent performance
        performance_factor = performance_score / 100
        suitability *= (0.7 + performance_factor * 0.3)  # 70% base + 30% performance
        
        # Bonus if horse has proven ability at this level or higher
        if class_history['highest_class'] >= current_class_weight:
            suitability = min(100, suitability * 1.2)
        
        # Penalty if horse is moving up significantly in class
        if current_class_weight > avg_historical + 5:
            suitability *= 0.8
        
        return min(100, max(0, suitability))
    
    def get_class_trend(self, horse):
        """Analyze if horse is moving up or down in class with performance context"""
        from racecard.models import Run
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')[:4]
        class_weights = []
        performances = []
        
        for run in runs:
            if run.race_class:
                weight = self.get_class_weight(run.race_class)
                class_weights.append(weight)
                
                # Get performance (lower position number = better)
                try:
                    position = float(run.position) if run.position and run.position.isdigit() else 10
                    performances.append(position)
                except:
                    performances.append(5)  # Default
        
        if len(class_weights) < 2:
            return "stable"  # Not enough data
        
        # Calculate trend considering both class and performance
        recent_class = class_weights[0]
        recent_perf = performances[0] if performances else 5
        previous_avg_class = sum(class_weights[1:]) / len(class_weights[1:])
        previous_avg_perf = sum(performances[1:]) / len(performances[1:]) if len(performances) > 1 else 5
        
        # Moving up in class AND performing well
        if recent_class > previous_avg_class + 3 and recent_perf <= previous_avg_perf:
            return "moving_up_strong"
        # Moving up in class but performing worse
        elif recent_class > previous_avg_class + 3 and recent_perf > previous_avg_perf:
            return "moving_up_weak"
        # Moving down in class AND performing better
        elif recent_class < previous_avg_class - 3 and recent_perf < previous_avg_perf:
            return "moving_down_strong"
        # Moving down in class but performing worse
        elif recent_class < previous_avg_class - 3 and recent_perf >= previous_avg_perf:
            return "moving_down_weak"
        else:
            return "stable"