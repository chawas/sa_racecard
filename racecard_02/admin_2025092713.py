
# admin.py
from django.contrib import admin
from .models import Race, Horse, Run, HorseScore, Ranking, ManualResult, ManualHorseResult # Add HorseScore


@admin.register(HorseScore)
class HorseScoreAdmin(admin.ModelAdmin):
    list_display = ['horse', 'race', 'current_mr_score', 'form_score', 'calculated_at']
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
    list_display = [
        'horse', 
        'run_date', 
        'track', 
        'position',  # Changed from 'position'
        'margin',    # Changed from 'margin'
        'weight',
        'jockey'
    ]
    
    list_filter = [
        'run_date',
        'track',
        'race_class',
        'going',
        'position'  # Changed from 'position'
    ]
    
    search_fields = [
        'horse__horse_name',  # Changed from 'horse_name' (access through foreign key)
        'jockey',
        'track',
        'comment'
    ]
    
    list_per_page = 50
    
    fieldsets = (
        ('Horse Information', {
            'fields': ('horse', 'run_date', 'days_since_last_run')  # Changed from 'horse_name'
        }),
        ('Race Details', {
            'fields': ('track', 'going', 'race_class', 'distance', 'draw', 'field_size')
        }),
        ('Performance', {
            'fields': ('position', 'margin', 'weight', 'merit_rating', 'time_seconds')  # Changed field names
        }),
        ('Betting & Personnel', {
            'fields': ('starting_price', 'jockey')
        }),
        ('Additional Info', {
            'fields': ('comment',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    # If you want to display horse name in the list display instead of the horse object
    def horse_name(self, obj):
        return obj.horse.horse_name
    horse_name.short_description = 'Horse Name'
    
    # Optional: If you want to use horse_name in list_display instead of horse object
    # Change list_display to use 'horse_name' instead of 'horse'
    # list_display = ['horse_name', 'run_date', 'track', ...]

# admin.py - Update Ranking admin
@admin.register(Ranking)
class RankingAdmin(admin.ModelAdmin):
    list_display = ['race_info', 'horse_info', 'rank', 'overall_score_display', 'class_score', 'jt_score']
    list_filter = ['race__race_date', 'race__race_no', 'rank']
    search_fields = ['horse__horse_name', 'race__race_name', 'jockey', 'trainer']
    readonly_fields = ['race', 'horse']



    def overall_score_display(self, obj):
        return round(obj.overall_score, 2)  # limit decimals
    overall_score_display.short_description = "Overall Score"

    
    def race_info(self, obj):
        return f"{obj.race.race_date} - R{obj.race.race_no} - {obj.race.race_name}"
    race_info.short_description = 'Race'
    
    def horse_info(self, obj):
        return f"{obj.horse.horse_no}. {obj.horse.horse_name}"
    horse_info.short_description = 'Horse'


@admin.register(ManualResult)
class ManualResultAdmin(admin.ModelAdmin):
    list_display = ['race', 'entered_by', 'entered_at', 'verified']
    list_filter = ['verified', 'entered_at']
    readonly_fields = ['entered_by', 'entered_at']

@admin.register(ManualHorseResult)
class ManualHorseResultAdmin(admin.ModelAdmin):
    list_display = ['horse', 'manual_result', 'position', 'margin']
    list_filter = ['manual_result__race__race_date', 'position']
