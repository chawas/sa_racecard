from django.urls import path
from . import views

app_name = 'racecard_02'

urlpatterns = [
    # Main pages
    path('', views.home_view, name='home'),
    path('horses/', views.horse_selection_view, name='horse_selection'),
    path('horse/<int:horse_id>/', views.horse_detail_view, name='horse_detail'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Scores
    path('scores/', views.horse_scores_view, name='horse_scores'),
    path('scores/<int:race_id>/', views.horse_scores_view, name='race_scores'),
    path('score/<int:score_id>/', views.horse_score_detail, name='horse_score_detail'),
    
    # Rankings - MAIN RANKING PATHS
    path('rankings/', views.race_rankings, name='race_rankings'),
    path('rankings/<int:race_id>/', views.race_rankings, name='race_rankings_detail'),
    path('rankings/api/<int:race_id>/', views.rankings_api, name='rankings_api'),
    
    # Legacy ranking paths (redirect to new system)
    path('ranking/<path:race_date>/<int:race_no>/<path:race_field>/', 
         views.horse_ranking_view, name='horse_ranking'),
    
    # Additional ranking views
    path('rankings/horse/<str:horse_name>/', views.horse_rankings_history_view, name='horse_rankings_history'),
    path('rankings/top/', views.top_rankings_view, name='top_rankings'),
    path('races/', views.available_races_view, name='available_races'),
    
    # Ranking calculation
    path('calculate-rankings/', views.calculate_and_save_rankings, name='calculate_rankings'),
    path('calculate-rankings/<int:race_id>/', views.calculate_and_save_rankings, name='calculate_rankings_race'),
]