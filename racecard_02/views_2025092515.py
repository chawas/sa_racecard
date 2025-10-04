from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q

from .models import Race, Horse, HorseScore, Ranking
from .forms import DateSelectionForm

@login_required
def horse_selection_view(request):
    form = DateSelectionForm(request.GET or None)
    selected_date = timezone.now().date()
    race_number = None
    races = Race.objects.none()
    all_rankings = []
    
    if form.is_valid():
        selected_date = form.cleaned_data['selected_date']
        race_number = form.cleaned_data['race_number']
        
        # Filter races for selected date
        races = Race.objects.filter(race_date=selected_date)
        
        if race_number:
            races = races.filter(race_no=race_number)
        
        # Get rankings for the filtered races
        if races.exists():
            all_rankings = Ranking.objects.filter(
                race__in=races
            ).select_related('horse', 'race').order_by('race__race_no', 'rank')
    
    # If no rankings exist but we have races, calculate them from HorseScore
    if races.exists() and not all_rankings:
        all_rankings = calculate_rankings_from_scores(races)
    
    # Pagination
    paginator = Paginator(all_rankings, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'selected_date': selected_date,
        'race_number': race_number,
        'races': races,
        'page_obj': page_obj,
        'total_horses': len(all_rankings),
        'today': timezone.now().date(),
    }
    
    return render(request, 'horse_selection.html', context)

def calculate_rankings_from_scores(races):
    """
    Calculate rankings directly from HorseScore data without saving to database
    """
    all_rankings = []
    
    for race in races:
        # Get all horse scores for this race
        horse_scores = HorseScore.objects.filter(race=race).select_related('horse')
        
        if not horse_scores.exists():
            continue
        
        # Sort by overall_score (descending) and assign ranks
        sorted_scores = sorted(horse_scores, key=lambda x: x.overall_score, reverse=True)
        
        for rank, horse_score in enumerate(sorted_scores, 1):
            # Create a ranking-like object with all score parameters
            ranking_obj = type('RankingObj', (), {})()
            ranking_obj.race = race
            ranking_obj.horse = horse_score.horse
            ranking_obj.rank = rank
            
            # Overall scores
            ranking_obj.overall_score = horse_score.overall_score
            ranking_obj.speed_score = horse_score.speed_score
            ranking_obj.form_score = horse_score.form_score
            ranking_obj.class_score = horse_score.class_score
            ranking_obj.consistency_score = horse_score.consistency_score
            ranking_obj.value_score = horse_score.value_score
            ranking_obj.physical_score = horse_score.physical_score
            ranking_obj.intangible_score = horse_score.intangible_score
            
            # Individual parameter scores
            ranking_obj.speed_rating_score = horse_score.speed_rating_score
            ranking_obj.best_mr_score = horse_score.best_mr_score
            ranking_obj.current_mr_score = horse_score.current_mr_score
            ranking_obj.jt_score = horse_score.jt_score
            ranking_obj.odds_score = horse_score.odds_score
            ranking_obj.weight_score = horse_score.weight_score
            ranking_obj.draw_score = horse_score.draw_score
            ranking_obj.blinkers_score = horse_score.blinkers_score
            
            all_rankings.append(ranking_obj)
    
    return all_rankings

@login_required
def horse_detail_view(request, horse_id):
    horse = get_object_or_404(Horse.objects.select_related('race'), id=horse_id)
    runs = horse.run_set.all().order_by('-run_date')[:10]  # Last 10 runs
    
    # Get horse score if available
    try:
        horse_score = HorseScore.objects.get(horse=horse, race=horse.race)
    except HorseScore.DoesNotExist:
        horse_score = None
    
    context = {
        'horse': horse,
        'runs': runs,
        'horse_score': horse_score,
    }
    return render(request, 'horse_detail.html', context)

def home_view(request):
    """Simple homepage view that redirects to horse selection"""
    return redirect('horse_selection')

def horse_scores_view(request, race_id=None):
    """View to display horse scores"""
    if race_id:
        race = get_object_or_404(Race, id=race_id)
        scores = HorseScore.objects.filter(race=race).select_related('horse').order_by('-overall_score')
        title = f"Scores for {race.race_name} - {race.race_date}"
    else:
        scores = HorseScore.objects.select_related('horse', 'race').order_by('-calculated_at', '-overall_score')
        title = "All Horse Scores"
    
    paginator = Paginator(scores, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'title': title,
        'race': race if race_id else None,
    }
    return render(request, 'horse_scores.html', context)

def horse_score_detail(request, score_id):
    """Detailed view for a specific horse score"""
    score = get_object_or_404(HorseScore.objects.select_related('horse', 'race'), id=score_id)
    
    context = {
        'score': score,
    }
    return render(request, 'horse_score_detail.html', context)

# ============================
# RANKING VIEWS
# ============================

def race_rankings(request, race_id=None):
    """
    Display rankings for races - MAIN RANKING VIEW
    """
    if race_id:
        # Specific race rankings
        race = get_object_or_404(Race, id=race_id)
        rankings = get_race_rankings(race)
        
        context = {
            'race': race,
            'rankings': rankings,
            'single_race': True,
        }
        
    else:
        # Today's races with rankings
        today = timezone.now().date()
        races_with_rankings = []
        
        today_races = Race.objects.filter(race_date=today)
        
        for race in today_races:
            rankings = get_race_rankings(race)
            if rankings:
                races_with_rankings.append({
                    'race': race,
                    'rankings': rankings
                })
        
        context = {
            'races_with_rankings': races_with_rankings,
            'single_race': False,
            'display_date': today,
        }
    
    return render(request, 'rankings.html', context)

def get_race_rankings(race):
    """
    Get rankings for a specific race from database or calculate from scores
    """
    # Try to get existing rankings first
    rankings = Ranking.objects.filter(race=race).select_related('horse').order_by('rank')
    
    # If no rankings exist, calculate from HorseScore
    if not rankings.exists():
        horse_scores = HorseScore.objects.filter(race=race).select_related('horse').order_by('-overall_score')
        rankings_list = []
        
        for rank, score in enumerate(horse_scores, 1):
            # Create ranking-like object
            ranking_obj = type('RankingObj', (), {})()
            ranking_obj.rank = rank
            ranking_obj.horse = score.horse
            ranking_obj.overall_score = score.overall_score
            ranking_obj.speed_score = score.speed_score
            ranking_obj.form_score = score.form_score
            ranking_obj.class_score = score.class_score
            ranking_obj.consistency_score = score.consistency_score
            ranking_obj.value_score = score.value_score
            ranking_obj.physical_score = score.physical_score
            ranking_obj.intangible_score = score.intangible_score
            ranking_obj.speed_rating_score = score.speed_rating_score
            ranking_obj.best_mr_score = score.best_mr_score
            ranking_obj.current_mr_score = score.current_mr_score
            ranking_obj.jt_score = score.jt_score
            ranking_obj.odds_score = score.odds_score
            ranking_obj.weight_score = score.weight_score
            ranking_obj.draw_score = score.draw_score
            ranking_obj.blinkers_score = score.blinkers_score
            rankings_list.append(ranking_obj)
        
        return rankings_list
    
    return rankings

def rankings_api(request, race_id):
    """
    API endpoint for rankings data (useful for AJAX)
    """
    race = get_object_or_404(Race, id=race_id)
    rankings = get_race_rankings(race)
    
    data = {
        'race': {
            'id': race.id,
            'date': race.race_date,
            'number': race.race_no,
            'name': race.race_name,
            'field': race.race_field,
        },
        'rankings': []
    }
    
    for ranking in rankings:
        data['rankings'].append({
            'rank': ranking.rank,
            'horse_name': ranking.horse.horse_name,
            'horse_number': ranking.horse.horse_no,
            'jockey': ranking.horse.jockey or '',
            'trainer': ranking.horse.trainer or '',
            'weight': ranking.horse.weight or '',
            'odds': ranking.horse.odds or '',
            
            # Scores
            'overall_score': round(getattr(ranking, 'overall_score', 0), 2),
            'speed_score': round(getattr(ranking, 'speed_score', 0), 2),
            'form_score': round(getattr(ranking, 'form_score', 0), 2),
            'class_score': round(getattr(ranking, 'class_score', 0), 2),
            'consistency_score': round(getattr(ranking, 'consistency_score', 0), 2),
            'value_score': round(getattr(ranking, 'value_score', 0), 2),
            'physical_score': round(getattr(ranking, 'physical_score', 0), 2),
            'intangible_score': round(getattr(ranking, 'intangible_score', 0), 2),
            
            # Individual parameters
            'speed_rating_score': round(getattr(ranking, 'speed_rating_score', 0), 2),
            'best_mr_score': round(getattr(ranking, 'best_mr_score', 0), 2),
            'current_mr_score': round(getattr(ranking, 'current_mr_score', 0), 2),
            'jt_score': round(getattr(ranking, 'jt_score', 0), 2),
            'odds_score': round(getattr(ranking, 'odds_score', 0), 2),
            'weight_score': round(getattr(ranking, 'weight_score', 0), 2),
            'draw_score': round(getattr(ranking, 'draw_score', 0), 2),
            'blinkers_score': round(getattr(ranking, 'blinkers_score', 0), 2),
        })
    
    return JsonResponse(data)

def horse_ranking_view(request, race_date, race_no, race_field):
    """Legacy ranking view - redirect to new system"""
    race = get_object_or_404(Race, race_date=race_date, race_no=race_no, race_field=race_field)
    #return redirect('race_rankings', race_id=race.id)
    return redirect('racecard_02:race_rankings_detail', race_id=race.id)

def horse_rankings_history_view(request, horse_name):
    """View all rankings for a specific horse across races"""
    rankings = Ranking.objects.filter(
        horse__horse_name__iexact=horse_name
    ).select_related('race', 'horse').order_by('-race__race_date', 'rank')
    
    context = {
        'horse_name': horse_name,
        'rankings': rankings,
    }
    return render(request, 'racecard_02/horse_rankings_history.html', context)

def top_rankings_view(request, days=30):
    """View top rankings from recent races"""
    from datetime import date, timedelta
    start_date = date.today() - timedelta(days=days)
    
    rankings = Ranking.objects.filter(
        race__race_date__gte=start_date,
        rank=1  # Only show winners
    ).select_related('race', 'horse').order_by('-race__race_date')
    
    context = {
        'days': days,
        'rankings': rankings,
    }
    return render(request, 'racecard_02/top_rankings.html', context)

def available_races_view(request):
    """View to list all available races with rankings"""
    # Get races that have either rankings or horse scores
    races_with_scores = Race.objects.filter(
        Q(horsescore__isnull=False) | Q(ranking__isnull=False)
    ).distinct().order_by('-race_date', 'race_no')
    
    context = {
        'races': races_with_scores,
    }
    return render(request, 'available_races_02.html', context)

@login_required
def calculate_and_save_rankings(request, race_id=None):
    """View to calculate and save rankings to database"""
    from django.db import transaction
    from racecard_02.models import Ranking, HorseScore
    
    if race_id:
        races = Race.objects.filter(id=race_id)
        redirect_race = races.first() if races.exists() else None
    else:
        # Calculate for all recent races without rankings
        races = Race.objects.filter(
            race_date__gte=timezone.now().date() - timezone.timedelta(days=30)
        )
        redirect_race = None
    
    rankings_created = 0
    
    with transaction.atomic():
        for race in races:
            # Delete existing rankings for this race
            Ranking.objects.filter(race=race).delete()
            
            # Get horse scores for this race
            horse_scores = HorseScore.objects.filter(race=race).select_related('horse')
            
            if not horse_scores.exists():
                continue
            
            # Sort by overall_score and create rankings
            sorted_scores = sorted(horse_scores, key=lambda x: x.overall_score, reverse=True)
            
            for rank, horse_score in enumerate(sorted_scores, 1):
                ranking = Ranking(
                    race=race,
                    horse=horse_score.horse,
                    rank=rank,
                    overall_score=horse_score.overall_score,
                    speed_score=horse_score.speed_score,
                    form_score=horse_score.form_score,
                    class_score=horse_score.class_score,
                    consistency_score=horse_score.consistency_score,
                    value_score=horse_score.value_score,
                    physical_score=horse_score.physical_score,
                    intangible_score=horse_score.intangible_score,
                    speed_rating_score=horse_score.speed_rating_score,
                    best_mr_score=horse_score.best_mr_score,
                    current_mr_score=horse_score.current_mr_score,
                    jt_score=horse_score.jt_score,
                    odds_score=horse_score.odds_score,
                    weight_score=horse_score.weight_score,
                    draw_score=horse_score.draw_score,
                    blinkers_score=horse_score.blinkers_score,
                    best_mr_value=horse_score.best_mr_value,
                    current_mr_value=horse_score.current_mr_value,
                    jt_value=horse_score.jt_value,
                    odds_value=horse_score.odds_value,
                    weight_value=horse_score.weight_value,
                    draw_value=horse_score.draw_value,
                    blinkers_value=horse_score.blinkers_value,
                )
                ranking.save()
                rankings_created += 1
    
    messages.success(request, f"Successfully created {rankings_created} rankings!")
    
    if redirect_race:
        return redirect('race_rankings', race_id=redirect_race.id)
    else:
        return redirect('horse_selection')

def dashboard_view(request):
    """Dashboard view that links to all sections"""
    # Get today's date
    today = timezone.now().date()
    
    # Get some recent data for the dashboard
    recent_races = Race.objects.order_by('-race_date')[:5]
    top_scores = HorseScore.objects.select_related('horse', 'race').order_by('-overall_score')[:5]
    recent_rankings = Ranking.objects.select_related('horse', 'race').order_by('-race__race_date')[:5]
    
    # Get today's races and horses
    todays_races = Race.objects.filter(race_date=today)
    todays_horses = Horse.objects.filter(race__in=todays_races)[:10]
    
    context = {
        'recent_races': recent_races,
        'top_scores': top_scores,
        'recent_rankings': recent_rankings,
        'todays_horses': todays_horses,
        'todays_races': todays_races,
        'today': today,
    }
    return render(request, 'dashboard.html', context)