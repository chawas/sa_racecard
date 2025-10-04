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

   

    weight = models.FloatField(default=0.0, help_text="Declared weight")
    apprentice_allowance = models.FloatField(default=0.0, help_text="Apprentice allowance")
    actual_weight = models.FloatField(default=0.0, help_text="Actual weight after allowance")
  
    best_merit_rating = models.IntegerField(null=True, blank=True, verbose_name="Best MR")
    # ... other fields ...
    
    class Meta:
        verbose_name = "Horse"
        verbose_name_plural = "Horses"
    def __str__(self):
        weight_display = f" ({self.weight})" if self.weight else ""
        return f"{self.horse_name}{weight_display}"

# models.py - Update HorseScore model
class HorseScore(models.Model):
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE, related_name='scores')  # ✅ ForeignKey
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    
    # Overall scores
    overall_score = models.FloatField()
    speed_score = models.FloatField()
    form_score = models.FloatField()
    class_score = models.FloatField()
    consistency_score = models.FloatField()
    
    value_score = models.FloatField(default=50)
    physical_score = models.FloatField()
    intangible_score = models.FloatField()
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    # Individual parameter scores
    speed_rating_score = models.FloatField()
    best_mr_score = models.FloatField()
    current_mr_score = models.FloatField()
    jt_score = models.FloatField()
    odds_score = models.FloatField()
    weight_score = models.FloatField()
    draw_score = models.FloatField()
    blinkers_score = models.FloatField()

    # Magic Tips fields
    is_magic_tip = models.BooleanField(default=False, verbose_name="Magic Tips Selection")
    magic_tips_boost = models.FloatField(default=0.0, verbose_name="Magic Tips Boost")
    magic_tips_weight = models.FloatField(default=0.4, verbose_name="Magic Tips Weight")  # 40%
    
    # Raw values for reference
    best_mr_value = models.IntegerField(default=0)
    current_mr_value = models.IntegerField(default=0)
    jt_value = models.IntegerField(default=50)
    odds_value = models.FloatField(default=0)
    weight_value = models.FloatField(default=0)
    draw_value = models.IntegerField(default=0)
    blinkers_value = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['horse', 'race']  # ✅ Unique by horse and race
# racecard_02/models.py
class Run(models.Model):
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE, related_name='runs')
    run_date = models.DateField()
    
    # These columns already exist in your database
    track = models.CharField(max_length=50, null=True, blank=True)
    going = models.CharField(max_length=20, null=True, blank=True)
    race_class = models.CharField(max_length=20, null=True, blank=True)
    distance = models.IntegerField(null=True, blank=True)  # Changed to IntegerField
    position = models.CharField(max_length=20, null=True, blank=True)
    margin = models.CharField(max_length=20, null=True, blank=True)
    weight = models.FloatField(null=True, blank=True)
    merit_rating = models.IntegerField(null=True, blank=True)
    
    # Add only the fields that are missing from database
    jockey = models.CharField(max_length=100, null=True, blank=True)
    draw = models.IntegerField(null=True, blank=True)
    field_size = models.IntegerField(null=True, blank=True)
    time_seconds = models.FloatField(null=True, blank=True)
    starting_price = models.CharField(max_length=20, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)
    days_since_last_run = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        unique_together = ['horse', 'run_date']
        db_table = 'racecard_02_run'

    def __str__(self):
        return f"{self.horse.horse_name} - {self.run_date} - {self.position}"
    

    
# models.py - Update Ranking model
# racecard_02/models.py
class Ranking(models.Model):
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE, related_name='rankings')
    rank = models.IntegerField()
    
    # Magic Tips fields
    is_magic_tip = models.BooleanField(default=False)
    magic_tips_boost = models.FloatField(default=0.0)
    adjusted_score = models.FloatField(default=0.0)
    
    # Overall scores
    overall_score = models.FloatField()
    speed_score = models.FloatField()
    form_score = models.FloatField()
    class_score = models.FloatField()
    consistency_score = models.FloatField()
    value_score = models.FloatField(default=50)
    physical_score = models.FloatField()
    intangible_score = models.FloatField()
    
    # Individual parameter scores
    speed_rating_score = models.FloatField()
    best_mr_score = models.FloatField()
    current_mr_score = models.FloatField()
    jt_score = models.FloatField()
    odds_score = models.FloatField()
    weight_score = models.FloatField()
    draw_score = models.FloatField()
    blinkers_score = models.FloatField()
    
    # Raw values
    best_mr_value = models.IntegerField(default=0)
    current_mr_value = models.IntegerField(default=0)
    jt_value = models.IntegerField(default=50)
    odds_value = models.FloatField(default=0)
    weight_value = models.FloatField(default=0)
    draw_value = models.IntegerField(default=0)
    blinkers_value = models.BooleanField(default=False)
    
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['race', 'horse']
        ordering = ['race', 'rank']

    def __str__(self):
        magic_indicator = " ✨" if self.is_magic_tip else ""
        return f"{self.race} - {self.horse.horse_name} - Rank {self.rank}{magic_indicator}"

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