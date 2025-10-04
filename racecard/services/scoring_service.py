import os
import sys
from datetime import date, timedelta
from django.db.models import Avg, Count, Q
from django.utils import timezone

# Add the project root to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from racecard_02.models import Horse, Run, Race, HorseScore
from racecard_02.services.class_analysis import ClassAnalysisService

class HorseScoringService:
    
    def __init__(self, horse, race):
        # Handle both horse objects and horse IDs/names
        if isinstance(horse, (int, str)):
            # Look up horse by ID or name
            try:
                if isinstance(horse, int):
                    self.horse = Horse.objects.get(id=horse)
                else:
                    self.horse = Horse.objects.get(horse_name=horse)
            except Horse.DoesNotExist:
                raise ValueError(f"Horse '{horse}' not found")
            except Horse.MultipleObjectsReturned:
                self.horse = Horse.objects.filter(horse_name=horse).first()
        else:
            self.horse = horse
            
        self.race = race
        self.runs = Run.objects.filter(horse=self.horse).order_by('-run_date')
        self.class_analyzer = ClassAnalysisService()
    
    def calculate_merit_score(self):
        """Score based on horse's merit rating"""
        try:
            base_merit = getattr(self.horse, 'horse_merit', 0) or 0
            return min(base_merit / 100, 1.0)  # Normalize to 0-1
        except:
            return 0.5  # Default score
    
    def calculate_form_score(self):
        """Score based on recent form"""
        recent_runs = self.runs[:6]  # Last 6 runs
        if not recent_runs:
            return 0.5  # Neutral score for no data
        
        positions = []
        for run in recent_runs:
            try:
                if run.position:
                    if isinstance(run.position, str) and run.position.isdigit():
                        pos = float(run.position)
                    elif isinstance(run.position, (int, float)):
                        pos = float(run.position)
                    else:
                        continue
                    positions.append(pos)
            except:
                continue
        
        if not positions:
            return 0.5
        
        # Weight recent runs more heavily
        weighted_sum = 0
        total_weight = 0
        for i, pos in enumerate(positions):
            weight = 0.8 ** i  # Recent runs have higher weight
            weighted_sum += pos * weight
            total_weight += weight
        
        avg_position = weighted_sum / total_weight
        return max(0, 1 - (avg_position / 12))  # Better positions score higher
    
    def calculate_class_score(self):
        """Score based on class suitability"""
        try:
            return self.class_analyzer.calculate_class_suitability(self.horse, self.race) / 100
        except:
            return 0.5  # Default score
    
    def calculate_distance_score(self):
        """Score based on distance suitability"""
        try:
            target_distance = self._parse_distance(getattr(self.race, 'race_distance', None))
            if not target_distance:
                return 0.5
            
            distance_performances = []
            for run in self.runs[:10]:
                run_distance = self._parse_distance(getattr(run, 'distance', None))
                if run_distance and hasattr(run, 'position') and run.position:
                    try:
                        if isinstance(run.position, str) and run.position.isdigit():
                            position = float(run.position)
                        elif isinstance(run.position, (int, float)):
                            position = float(run.position)
                        else:
                            continue
                        
                        # Score based on performance at similar distances
                        distance_diff = abs(run_distance - target_distance)
                        similarity = max(0, 1 - (distance_diff / 400))  # 400m tolerance
                        performance = max(0, 1 - (position / 12))  # Better positions score higher
                        distance_performances.append(performance * similarity)
                    except:
                        continue
            
            return sum(distance_performances) / len(distance_performances) if distance_performances else 0.5
        except:
            return 0.5
    
    def calculate_consistency_score(self):
        """Score based on performance consistency"""
        try:
            recent_positions = []
            for run in self.runs[:8]:
                if hasattr(run, 'position') and run.position:
                    try:
                        if isinstance(run.position, str) and run.position.isdigit():
                            pos = float(run.position)
                        elif isinstance(run.position, (int, float)):
                            pos = float(run.position)
                        else:
                            continue
                        recent_positions.append(pos)
                    except:
                        continue
            
            if len(recent_positions) < 3:
                return 0.5
            
            avg_position = sum(recent_positions) / len(recent_positions)
            variance = sum((pos - avg_position) ** 2 for pos in recent_positions) / len(recent_positions)
            consistency = max(0, 1 - (variance / 20))  # Lower variance = higher consistency
            
            return consistency
        except:
            return 0.5
    
    def calculate_speed_rating(self):
        """Calculate speed rating based on recent performances"""
        try:
            recent_runs = self.runs[:5]
            if not recent_runs:
                return 50
            
            speed_scores = []
            for run in recent_runs:
                if hasattr(run, 'speed_rating') and run.speed_rating:
                    try:
                        speed_scores.append(float(run.speed_rating))
                    except:
                        continue
            
            return sum(speed_scores) / len(speed_scores) if speed_scores else 50
        except:
            return 50
    
    def _parse_distance(self, distance_str):
        """Parse distance string to meters"""
        if not distance_str:
            return None
        try:
            # Extract numbers from string (e.g., "1200m" -> 1200)
            import re
            numbers = re.findall(r'\d+', str(distance_str))
            return int(numbers[0]) if numbers else None
        except:
            return None
    
    def calculate_composite_score(self):
        """Calculate overall composite score"""
        weights = {
            'merit': 0.15,
            'form': 0.25,
            'class': 0.20,
            'distance': 0.15,
            'consistency': 0.10,
            'speed': 0.15
        }
        
        scores = {
            'merit': self.calculate_merit_score(),
            'form': self.calculate_form_score(),
            'class': self.calculate_class_score(),
            'distance': self.calculate_distance_score(),
            'consistency': self.calculate_consistency_score(),
            'speed': self.calculate_speed_rating() / 100  # Convert to 0-1 scale
        }
        
        composite = sum(scores[factor] * weights[factor] for factor in weights)
        return min(max(composite, 0), 1.0)  # Ensure between 0-1
    
    def create_score_record(self):
        """Create or update a comprehensive score record"""
        try:
            composite_score = self.calculate_composite_score()
            
            # Calculate all individual scores
            merit_score = self.calculate_merit_score() * 100  # Convert to 0-100 scale
            form_score = self.calculate_form_score() * 100
            class_score = self.calculate_class_score() * 100
            distance_score = self.calculate_distance_score() * 100
            consistency_score = self.calculate_consistency_score() * 100
            speed_rating = self.calculate_speed_rating()
            
            # Use update_or_create to handle existing records
            score_record, created = HorseScore.objects.update_or_create(
                horse=self.horse,
                race=self.race,
                defaults={
                    'overall_score': composite_score * 100,  # Convert to 0-100 scale
                    'merit_score': merit_score,
                    'form_score': form_score,
                    'class_score': class_score,
                    'distance_score': distance_score,
                    'consistency_score': consistency_score,
                    'speed_rating': speed_rating,
                    'calculated_at': timezone.now()
                }
            )
            
            return score_record, created
            
        except Exception as e:
            raise Exception(f"Error creating score record: {str(e)}")