# models.py
from django.db import models
from datetime import time
from django.utils import timezone  # Add this import


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
    
    trainer = models.CharField(max_length=100, null=True, blank=True)  # 🆞️
    jockey = models.CharField(max_length=100, null=True, blank=True)   # 🆞️

    def __str__(self):
        return f"{self.horse_name} ({self.horse_no})"


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
    score = models.FloatField(null=True, blank=True)  # Allow null
    class_score = models.FloatField(null=True, blank=True)  # Allow null
    rank = models.IntegerField(null=True, blank=True)  # Allow null
    jt_score = models.FloatField(null=True, blank=True)
    jt_rating = models.CharField(max_length=20, blank=True, null=True)
    jockey = models.CharField(max_length=100, blank=True, null=True)
    trainer = models.CharField(max_length=100, blank=True, null=True)
    class_trend = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        ordering = ['rank']
    
    def __str__(self):
        return f"{self.rank}. {self.horse.horse_name} - Score: {self.score}"
# In racecard/models.py
class HorseScore(models.Model):
    horse = models.ForeignKey(Horse, on_delete=models.CASCADE)
    race = models.ForeignKey(Race, on_delete=models.CASCADE)
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    # Core scores
    overall_score = models.FloatField()
    merit_score = models.FloatField()
    form_score = models.FloatField()
    class_score = models.FloatField()
    distance_score = models.FloatField()
    consistency_score = models.FloatField()
    
    # Advanced metrics
    speed_rating = models.FloatField(null=True, blank=True)
    stamina_index = models.FloatField(null=True, blank=True)
    track_affinity = models.FloatField(null=True, blank=True)
    jockey_score = models.FloatField(null=True, blank=True)
    trainer_score = models.FloatField(null=True, blank=True)
    
    # Temporal factors
    days_since_last_run = models.IntegerField(null=True, blank=True)
    recovery_score = models.FloatField(null=True, blank=True)
    
    class Meta:
        unique_together = ('horse', 'race')

    def __str__(self):
        return f"{self.horse.horse_name} - Score: {self.overall_score:.2f}"