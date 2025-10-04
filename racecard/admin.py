
# admin.py
from django.contrib import admin
from .models import Race, Horse, Run, Ranking, HorseScore  # Add HorseScore

@admin.register(HorseScore)
class HorseScoreAdmin(admin.ModelAdmin):
    list_display = ['horse', 'race', 'overall_score', 'merit_score', 'form_score', 'calculated_at']
    list_filter = ['race', 'calculated_at']
    search_fields = ['horse__horse_name', 'race__race_name']
    readonly_fields = ['calculated_at']
    
    def horse_name(self, obj):
        return obj.horse.horse_name
    horse_name.short_description = 'Horse Name'
    
    def race_name(self, obj):
        return obj.race.race_name
    race_name.short_description = 'Race Name'

@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ('race_date','race_time', 'race_no', 'race_field', 'race_distance', 'race_class', 'race_merit')
    search_fields = ('race_field', 'race_class')
    list_filter = ('race_date', 'race_field')

@admin.register(Horse)
class HorseAdmin(admin.ModelAdmin):
    list_display = ('race', 'horse_no', 'horse_name', 'horse_merit', 'odds', 'blinkers', 'jockey', 'trainer')
    list_filter = ('race__race_date', 'race__race_field')  # ✅ Fix for foreign key fields
    search_fields = ('name', 'jockey', 'trainer')


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display = ('horse', 'run_date', 'position', 'margin', 'distance', 'race_class')
    list_filter = ('run_date',)

# admin.py - Update Ranking admin
@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    list_display = ['race_info', 'horse_info', 'rank', 'score', 'class_score', 'jt_score']
    list_filter = ['race__race_date', 'race__race_no', 'rank']
    search_fields = ['horse__horse_name', 'race__race_name', 'jockey', 'trainer']
    readonly_fields = ['race', 'horse']
    
    def race_info(self, obj):
        return f"{obj.race.race_date} - R{obj.race.race_no} - {obj.race.race_name}"
    race_info.short_description = 'Race'
    
    def horse_info(self, obj):
        return f"{obj.horse.horse_no}. {obj.horse.horse_name}"
    horse_info.short_description = 'Horse'
