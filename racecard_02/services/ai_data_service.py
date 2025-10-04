# racecard/services/ai_data_service.py
import pandas as pd
from django.db.models import Q

class AIDataService:
    
    def create_training_dataset(self):
        """Create dataset for AI training with features and targets"""
        from ..models import Horse, Ranking, RaceResult, HorseResult
        
        training_data = []
        
        # Get all races with results
        races_with_results = RaceResult.objects.filter(results_available=True)
        
        for race_result in races_with_results:
            race = race_result.race
            
            # Get all predictions for this race
            predictions = Ranking.objects.filter(race=race).select_related('horse')
            
            # Get actual results
            actual_results = {
                hr.horse_id: {
                    'position': hr.official_position,
                    'beaten_lengths': hr.beaten_lengths,
                    'speed_rating': hr.speed_rating,
                    'finish_rating': hr.finish_rating
                }
                for hr in race_result.horse_results.all()
            }
            
            for prediction in predictions:
                horse_id = prediction.horse_id
                if horse_id in actual_results:
                    actual = actual_results[horse_id]
                    
                    # Create feature vector
                    features = self._extract_features(prediction, race, prediction.horse)
                    
                    # Add target variables
                    target = {
                        'finish_position': actual['position'],
                        'beaten_lengths': actual['beaten_lengths'],
                        'speed_rating': actual['speed_rating']
                    }
                    
                    training_data.append({
                        'race_id': race.id,
                        'horse_id': horse_id,
                        'features': features,
                        'target': target
                    })
        
        return training_data
    
    def _extract_features(self, ranking, race, horse):
        """Extract all relevant features for AI training"""
        from .class_analysis import ClassAnalysisService
        
        class_analyzer = ClassAnalysisService()
        class_history = class_analyzer.analyze_horse_class_history(horse)
        
        features = {
            # Prediction features
            'predicted_score': ranking.score,
            'predicted_rank': ranking.rank,
            'class_score': ranking.class_score,
            'jt_score': ranking.jt_score or 0,
            
            # Horse attributes
            'merit_rating': horse.horse_merit or 0,
            'age': self._parse_age(horse.age),
            'blinkers': 1 if horse.blinkers else 0,
            
            # Class analysis
            'current_class_weight': class_analyzer.get_class_weight(race.race_class),
            'avg_historical_class': class_history['average_class_weight'],
            'class_consistency': class_history['class_consistency'],
            'highest_class': class_history['highest_class'],
            
            # Race conditions
            'distance': self._parse_distance(race.race_distance),
            'race_merit': race.race_merit or 0,
            
            # Temporal features
            'days_since_last_run': self._get_days_since_last_run(horse),
        }
        
        return features