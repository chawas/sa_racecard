from django.urls import path
from . import views

app_name = 'racecard_02'  # Make sure you have this

urlpatterns = [
    # Dashboard
    path('', views.dashboard_view, name='dashboard'),
    
    # Horse-related URLs
    
    path('horse_selection/', views.horse_selection_view, name='horse_selection'),
    path('horses/<int:horse_id>/', views.horse_detail_view, name='horse_detail'),  # Add this
    path('horses/<str:horse_name>/history/', views.horse_rankings_history_view, name='horse_rankings_history'),
    
    # Scores URLs
    path('scores/', views.horse_scores_view, name='horse_scores'),
    path('scores/race/<int:race_id>/', views.horse_scores_view, name='race_scores'),
    path('scores/<int:score_id>/', views.horse_score_detail, name='horse_score_detail'),
    
    # Rankings URLs - Make sure these match your template
    path('rankings/', views.available_races_view, name='available_races'),
    
    path('race/<str:race_date>/<int:race_no>/<str:race_field>/ranking/', views.horse_ranking_view, name='horse_ranking'),
    
    path('rankings/top/', views.top_rankings_view, name='top_rankings'),
    path('rankings/top/<int:days>/', views.top_rankings_view, name='top_rankings_days'),
    path('rankings/', views.race_rankings, name='race_rankings'),
    path('rankings/<int:race_id>/', views.race_rankings, name='race_rankings_detail'),
    path('api/rankings/<int:race_id>/', views.rankings_api, name='rankings_api'),
    
    # Race results URLs
    path('races/<int:race_id>/results/', views.race_results_view, name='race_results'),
    path('races/<int:race_id>/results/entry/', views.manual_results_entry, name='manual_results_entry'),
]