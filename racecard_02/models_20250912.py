# models.py
from django.db import models
from datetime import time
from django.utils import timezone  # Add this import


from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator



class Race(models.Model):
    race_date = models.DateField()
    race_no = models.IntegerField()
    race_time = models.TimeField(default=time(0, 0))  # ✅ Default added
    race_field = models.CharField(max_length=100)
    race_name = models.CharField(max_length=255)
    race_distance = models.CharField(max_length=50, default="Unknown")
    race_class = models.CharField(max_length=100, null=True, blank=True)
    race_merit = models.IntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('race_date', 'race_no', 'race_field')

    def __str__(self):
        return f"{self.race_date} - R{self.race_no} - {self.race_field}"
   


class Horse(models.Model):
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    horse_no = models.IntegerField(default=0)
    horse_name = models.CharField(max_length=100)
    blinkers = models.BooleanField(default=False)
    age = models.CharField(max_length=10, null=True, blank=True)
    dob = models.CharField(max_length=20, null=True, blank=True)
    horse_merit = models.IntegerField(null=True, blank=True)
    odds = models.CharField(max_length=20, null=True, blank=True)
    race_class = models.CharField(max_length=100, null=True, blank=True)
    speed_rating = models.IntegerField(
        null=True, 
        blank=True, 
        default=50,
        verbose_name="Speed Rating"
    )
    trainer = models.CharField(max_length=100, null=True, blank=True)  # 🆞️
    jockey = models.CharField(max_length=100, null=True, blank=True)   # 🆞️

    # In your models.py, add this field to the Horse model:
    jt_score = models.IntegerField(default=50, verbose_name="Jockey-Trainer Score")
    jt_rating = models.CharField(max_length=20, default="Average", verbose_name="Jockey-Trainer Rating")

    weight = models.CharField(max_length=20, blank=True, null=True)  # Use CharField for weight (e.g., "52.5kg")
    # ... other fields you might have ...
    # ... your existing fields ...
    best_merit_rating = models.IntegerField(null=True, blank=True, verbose_name="Best MR")
    # ... other fields ...
    
    class Meta:
        verbose_name = "Horse"
        verbose_name_plural = "Horses"
    def __str__(self):
        weight_display = f" ({self.weight})" if self.weight else ""
        return f"{self.horse_name}{weight_display}"
   
    

class Run(models.Model):
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE)
    run_date = models.DateField()
    position = models.CharField(max_length=10)
    margin = models.CharField(max_length=20)
    distance = models.CharField(max_length=20)
    race_class = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.horse.horse_name} - {self.run_date}"


# models.py - Update the Ranking model
class Ranking(models.Model):
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE)
    rank = models.IntegerField()  # Should NOT have null=True
    score = models.FloatField()
    
    # Other fields with proper defaults
    merit_score = models.IntegerField(default=0)
    class_score = models.FloatField(default=0.0)
    form_score = models.FloatField(default=0.0)
    jt_score = models.FloatField(default=0.0)
    jt_rating = models.CharField(max_length=20, default='', blank=True)
    jockey = models.CharField(max_length=100, default='', blank=True)
    trainer = models.CharField(max_length=100, default='', blank=True)
    class_trend = models.CharField(max_length=20, default='stable', blank=True)
    
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['race', 'horse']


class HorseScore(models.Model):
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE, related_name='scores')
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='horse_scores')
    
    # Main score
    overall_score = models.FloatField(default=0)
    
    # Component scores
    best_mr_score = models.FloatField(default=0)
    current_mr_score = models.FloatField(default=0)
    jt_score = models.FloatField(default=0)
    form_score = models.FloatField(default=0)
    class_score = models.FloatField(default=0)
    speed_rating = models.FloatField(default=0)  # ADD THIS FIELD
    consistency_score = models.FloatField(default=0)
    distance_score = models.FloatField(default=0)
    track_affinity = models.FloatField(default=0)  # ADD THIS FIELD
    recovery_score = models.FloatField(default=0)
    odds_score = models.FloatField(default=0)
    draw_score = models.FloatField(default=0)
    equipment_score = models.FloatField(default=0)
    age_score = models.FloatField(default=0)
    
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['horse', 'race']
class RaceResult(models.Model):
    race = models.OneToOneField(Race, on_delete=models.CASCADE, primary_key=True)
    results_available = models.BooleanField(default=False)
    results_updated_at = models.DateTimeField(auto_now=True)
    total_runners = models.IntegerField(null=True, blank=True)
    winning_time = models.FloatField(null=True, blank=True)  # in seconds
    going = models.CharField(max_length=20, blank=True, null=True)  # track condition
    
    class Meta:
        verbose_name = "Race Result"
        verbose_name_plural = "Race Results"

class HorseResult(models.Model):
    race_result = models.ForeignKey(RaceResult, on_delete=models.CASCADE, related_name='horse_results')
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE)
    official_position = models.IntegerField()
    official_margin = models.CharField(max_length=20, blank=True, null=True)
    official_time = models.FloatField(null=True, blank=True)  # in seconds
    beaten_lengths = models.FloatField(null=True, blank=True)
    finish_time = models.FloatField(null=True, blank=True)  # in seconds
    
    # Performance metrics
    speed_rating = models.FloatField(null=True, blank=True)
    pace_rating = models.FloatField(null=True, blank=True)
    finish_rating = models.FloatField(null=True, blank=True)
    
    # Betting metrics
    starting_price = models.FloatField(null=True, blank=True)
    finishing_price = models.FloatField(null=True, blank=True)
    
    class Meta:
        unique_together = ('race_result', 'horse')
        ordering = ['official_position']




class ManualResult(models.Model):
    race = models.OneToOneField('racecard.Race', on_delete=models.CASCADE, primary_key=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    entered_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "Manual Race Result"
        verbose_name_plural = "Manual Race Results"

class ManualHorseResult(models.Model):
    manual_result = models.ForeignKey(ManualResult, on_delete=models.CASCADE, related_name='horse_results')
    horse = models.ForeignKey('racecard.Horse', on_delete=models.CASCADE)  # String reference
    position = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(20)])
    margin = models.CharField(max_length=20, blank=True, null=True)
    time = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        unique_together = ('manual_result', 'horse')
        ordering = ['position']