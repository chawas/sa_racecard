from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from .models import Race, Ranking, Horse, HorseScore
from .forms import DateSelectionForm
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect


from django.http import Http404


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
        'today': timezone.now().date(),  # ← Add this line
    }
    
    return render(request, 'horse_selection.html', context)

@login_required
def horse_detail_view(request, horse_id):
    horse = Horse.objects.select_related('race').get(id=horse_id)
    runs = horse.run_set.all().order_by('-run_date')[:10]  # Last 10 runs
    
    context = {
        'horse': horse,
        'runs': runs,
    }
    return render(request, 'horse_detail.html', context) 


# Add this home_view function at the top or with your other views
def home_view(request):
    """Simple homepage view that redirects to horse selection"""
    return redirect('horse_selection')  # This redirects to the horse selection page

# OR if you want a proper homepage (not just a redirect):
def home_view(request):
    """Proper homepage with welcome message"""
    return render(request, 'home.html')




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



def race_rankings_view(request, race_date, race_no, field_name):
    """View rankings for a specific race using composite key"""
    try:
        race = get_object_or_404(Race, race_date=race_date, race_no=race_no, race_field=field_name)
        rankings = Ranking.objects.filter(race=race).select_related('horse').order_by('rank')
        
        context = {
            'race': race,
            'rankings': rankings,
        }
        return render(request, 'race_rankings.html', context)
    except Race.DoesNotExist:
        raise Http404("Race not found")

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

# racecard/views.py - Add this view
def available_races_view(request):
    """View to list all available races with rankings"""
    races_with_rankings = Race.objects.filter(
        ranking__isnull=False
    ).distinct().order_by('-race_date', 'race_no')
    
    context = {
        'races': races_with_rankings,
    }
    return render(request, 'available_races_02.html', context)