from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Race, Horse, HorseScore, Ranking
from .forms import DateSelectionForm
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import Http404
from django.db.models import Q

from racecard_02.services.scoring_service import ScoringService

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
            ranking = type('RankingObj', (), {})()
            ranking.race = race
            ranking.horse = horse_score.horse
            ranking.rank = rank
            
            # Overall scores
            ranking.overall_score = horse_score.overall_score
            ranking.speed_score = horse_score.speed_score
            ranking.form_score = horse_score.form_score
            ranking.class_score = horse_score.class_score
            ranking.consistency_score = horse_score.consistency_score
            ranking.value_score = horse_score.value_score
            ranking.physical_score = horse_score.physical_score
            ranking.intangible_score = horse_score.intangible_score
            
            # Individual parameter scores
            ranking.speed_rating_score = horse_score.speed_rating_score
            ranking.best_mr_score = horse_score.best_mr_score
            ranking.current_mr_score = horse_score.current_mr_score
            ranking.jt_score = horse_score.jt_score
            ranking.odds_score = horse_score.odds_score
            ranking.weight_score = horse_score.weight_score
            ranking.draw_score = horse_score.draw_score
            ranking.blinkers_score = horse_score.blinkers_score
            
            all_rankings.append(ranking)
    
    return all_rankings

@login_required
def horse_detail_view(request, horse_id):
    horse = Horse.objects.select_related('race').get(id=horse_id)
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

def horse_ranking_view(request, race_date, race_no, race_field):
    race = get_object_or_404(Race, race_date=race_date, race_no=race_no, race_field=race_field)
    
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
            rankings_list.append(ranking_obj)
        
        rankings = rankings_list
    
    context = {
        'race': race,
        'rankings': rankings,
    }
    
    return render(request, 'horse_ranking.html', context)

def horse_rankings_history_view(request, horse_name):
    """View all rankings for a specific horse across races"""
    rankings = Ranking.objects.filter(
        horse__horse_name__iexact=horse_name
    ).select_related('race', 'horse').order_by('-race__race_date', 'rank')
    
    context = {
        'horse_name': horse_name,
        'rankings': rankings,
    }
    return render(request, 'horse_rankings_history.html', context)

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
    return render(request, 'top_rankings.html', context)

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
def manual_results_entry(request, race_id):
    """View for manual results entry"""
    race = get_object_or_404(Race, id=race_id)
    horses = race.horse_set.all().order_by('horse_no')
    
    try:
        manual_result = ManualResult.objects.get(race=race)
    except ManualResult.DoesNotExist:
        manual_result = ManualResult.objects.create(race=race, entered_by=request.user)
    
    if request.method == 'POST':
        form = ManualResultForm(request.POST, instance=manual_result)
        formset = HorseResultFormSet(request.POST, instance=manual_result)
        
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            
            # Update main results if verified
            if manual_result.verified:
                _update_official_results(manual_result)
            
            messages.success(request, f"Results saved for {race.race_name}!")
            return redirect('race_results', race_id=race.id)
    else:
        form = ManualResultForm(instance=manual_result)
        formset = HorseResultFormSet(instance=manual_result)
    
    # Prepare horse data for template
    horse_forms = []
    for horse in horses:
        try:
            horse_result = manual_result.horse_results.get(horse=horse)
        except ManualHorseResult.DoesNotExist:
            horse_result = ManualHorseResult(manual_result=manual_result, horse=horse)
        
        horse_forms.append({
            'horse': horse,
            'form': HorseResultForm(instance=horse_result, prefix=f'horse_{horse.id}')
        })
    
    context = {
        'race': race,
        'form': form,
        'horse_forms': horse_forms,
        'manual_result': manual_result,
    }
    return render(request, 'manual_results_entry.html', context)

def _update_official_results(manual_result):
    """Update official results from manual entry"""
    from .models import RaceResult, HorseResult
    
    # Create or update race result
    race_result, created = RaceResult.objects.get_or_create(
        race=manual_result.race,
        defaults={'results_available': True}
    )
    
    # Update horse results
    for manual_horse_result in manual_result.horse_results.all():
        HorseResult.objects.update_or_create(
            race_result=race_result,
            horse=manual_horse_result.horse,
            defaults={
                'official_position': manual_horse_result.position,
                'official_margin': manual_horse_result.margin,
                'official_time': manual_horse_result.time,
            }
        )

def race_results_view(request, race_id):
    """View race results"""
    race = get_object_or_404(Race, id=race_id)
    
    # Try to get official results first, then manual results
    try:
        results = race.raceresult
        results_type = 'official'
    except RaceResult.DoesNotExist:
        try:
            results = race.manualresult
            results_type = 'manual'
        except ManualResult.DoesNotExist:
            results = None
            results_type = None
    
    context = {
        'race': race,
        'results': results,
        'results_type': results_type,
    }
    return render(request, 'race_results.html', context)

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

# Add this new view for calculating and saving rankings
@login_required
def calculate_and_save_rankings(request, race_id=None):
    """View to calculate and save rankings to database"""
    from django.db import transaction
    
    if race_id:
        races = Race.objects.filter(id=race_id)
    else:
        # Calculate for all recent races without rankings
        races = Race.objects.filter(
            race_date__gte=timezone.now().date() - timezone.timedelta(days=30)
        )
    
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
    
    if race_id:
        return redirect('horse_ranking_view', 
                       race_date=race.race_date, 
                       race_no=race.race_no, 
                       race_field=race.race_field)
    else:
        return redirect('horse_selection')