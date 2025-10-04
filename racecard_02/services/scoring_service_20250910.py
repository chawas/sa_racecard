# racecard_02/services/scoring_service.py
import logging
from typing import Optional
from django.db import models

logger = logging.getLogger(__name__)

class HorseScoringService:
    """Scoring service for calculating horse scores"""
    def __init__(self, horse, race, debug_callback=None):
        self.horse = horse
        self.race = race
        self.debug_callback = debug_callback
        self.debug = debug_callback is not None
        
    def debug_log(self, message: str):
        """Output debug message if debug callback is provided"""
        if self.debug_callback:
            self.debug_callback(message)
    
    def create_score_record(self):
        """Create or update a HorseScore record for this horse and race"""
        try:
            # Use local HorseScore model instead of rankings.models
            score_record, created = HorseScore.objects.get_or_create(
                horse=self.horse,
                race=self.race,
                defaults={'overall_score': self.calculate_overall_score()}
            )
            
            # Update all score components
            if not created:
                score_record.overall_score = self.calculate_overall_score()
                score_record.best_mr_score = self._calculate_best_mr_score()
                score_record.current_mr_score = self._calculate_current_mr_score()
                score_record.jt_score = self._calculate_jt_score()
                score_record.form_score = self._calculate_form_score()
                score_record.class_score = self._calculate_class_score()
                score_record.speed_score = self._calculate_speed_score()
                score_record.save()
            else:
                # For new records, set all components
                score_record.best_mr_score = self._calculate_best_mr_score()
                score_record.current_mr_score = self._calculate_current_mr_score()
                score_record.jt_score = self._calculate_jt_score()
                score_record.form_score = self._calculate_form_score()
                score_record.class_score = self._calculate_class_score()
                score_record.speed_score = self._calculate_speed_score()
                score_record.save()
            
            return score_record, created
            
        except Exception as e:
            self.debug_log(f"❌ Error creating score record: {e}")
            return self._create_fallback_record()
    
    def calculate_overall_score(self) -> float:
        """Calculate overall score with weighted components"""
        weights = {
            'best_mr': 0.2,
            'current_mr': 0.15,
            'jt': 0.2,
            'form': 0.15,
            'class': 0.15,
            'speed': 0.15
        }
        
        best_mr_score = self._calculate_best_mr_score()
        current_mr_score = self._calculate_current_mr_score()
        jt_score = self._calculate_jt_score()
        form_score = self._calculate_form_score()
        class_score = self._calculate_class_score()
        speed_score = self._calculate_speed_score()
        
        overall_score = (
            best_mr_score * weights['best_mr'] +
            current_mr_score * weights['current_mr'] +
            jt_score * weights['jt'] +
            form_score * weights['form'] +
            class_score * weights['class'] +
            speed_score * weights['speed']
        )
        
        return max(0, min(100, overall_score))
    
    def _calculate_best_mr_score(self) -> float:
        """Calculate score based on best merit rating"""
        try:
            if hasattr(self.horse, 'best_merit_rating') and self.horse.best_merit_rating:
                best_mr = self.horse.best_merit_rating
                # Scale: 60-120 MR maps to 0-100 score
                score = max(0, min(100, (best_mr - 60) * 2.5))
                self.debug_log(f"Best MR score: {score} (from MR {best_mr})")
                return float(score)
            return 50.0
        except Exception as e:
            self.debug_log(f"⚠️ Best MR score error: {e}, using default: 50")
            return 50.0
    
    def _calculate_current_mr_score(self) -> float:
        """Calculate score based on current merit rating"""
        try:
            if hasattr(self.horse, 'horse_merit') and self.horse.horse_merit:
                current_mr = self.horse.horse_merit
                # Scale: 60-120 MR maps to 0-100 score
                score = max(0, min(100, (current_mr - 60) * 2.5))
                self.debug_log(f"Current MR score: {score} (from MR {current_mr})")
                return float(score)
            return 50.0
        except Exception as e:
            self.debug_log(f"⚠️ Current MR score error: {e}, using default: 50")
            return 50.0
    
    def _calculate_jt_score(self) -> float:
        """Calculate jockey-trainer score"""
        try:
            if hasattr(self.horse, 'jt_score') and self.horse.jt_score:
                jt_score = self.horse.jt_score
                self.debug_log(f"J-T score: {jt_score}")
                return float(jt_score)
            return 50.0
        except Exception as e:
            self.debug_log(f"⚠️ J-T score error: {e}, using default: 50")
            return 50.0
    
    def _calculate_form_score(self) -> float:
        """Calculate form score"""
        try:
            # Default form score - you can enhance this with actual form data
            form_score = 50
            self.debug_log(f"Form score: {form_score}")
            return float(form_score)
        except Exception as e:
            self.debug_log(f"⚠️ Form score error: {e}, using default: 50")
            return 50.0
    
    def _calculate_class_score(self) -> float:
        """Calculate class score"""
        try:
            # Use class analysis service if available
            try:
                from racecard_02.services.class_analysis import ClassAnalysisService
                class_service = ClassAnalysisService(debug_callback=self.debug_log)
                class_score = class_service.calculate_class_suitability(self.horse, self.race)
                self.debug_log(f"Class score: {class_score}")
                return class_score
            except ImportError:
                self.debug_log("⚠️ ClassAnalysisService not available, using default: 50")
                return 50.0
        except Exception as e:
            self.debug_log(f"⚠️ Class score error: {e}, using default: 50")
            return 50.0
    
    def _calculate_speed_score(self) -> float:
        """Calculate speed rating score - THIS IS THE KEY FIX"""
        try:
            # Check for speed_rating field (what you're storing)
            if hasattr(self.horse, 'speed_rating') and self.horse.speed_rating:
                speed_rating = self.horse.speed_rating
                self.debug_log(f"Speed score: {speed_rating} (from speed_rating field)")
                return float(speed_rating)
            
            # Fallback: check other possible speed fields
            speed_fields = ['speed_index', 'best_speed_rating', 'last_speed_rating']
            for field in speed_fields:
                if hasattr(self.horse, field) and getattr(self.horse, field):
                    speed_value = getattr(self.horse, field)
                    self.debug_log(f"Speed score: {speed_value} (from {field} field)")
                    return float(speed_value)
            
            self.debug_log("⚠️ No speed data found, using default: 50")
            return 50.0
            
        except Exception as e:
            self.debug_log(f"⚠️ Speed score error: {e}, using default: 50")
            return 50.0
    
    def _create_fallback_record(self):
        """Create a fallback score record when scoring fails"""
        try:
            score_record = HorseScore.objects.create(
                horse=self.horse,
                race=self.race,
                overall_score=50,
                best_mr_score=50,
                current_mr_score=50,
                jt_score=50,
                form_score=50,
                class_score=50,
                speed_score=50
            )
            return score_record, True
        except Exception as e:
            logger.error(f"Critical error creating fallback record: {e}")
            # Return a mock record if even fallback fails
            class MockScore:
                def __init__(self):
                    self.overall_score = 50
                    self.best_mr_score = 50
                    self.current_mr_score = 50
                    self.jt_score = 50
                    self.form_score = 50
                    self.class_score = 50
                    self.speed_score = 50
                    self.ranking_position = None
                
                def save(self):
                    pass
            
            return MockScore(), False