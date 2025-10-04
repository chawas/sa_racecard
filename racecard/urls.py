# racecard/urls.py
from django.urls import path
from . import views



urlpatterns = [
    path('', views.horse_selection_view, name='horse_selection'),
    path('<int:horse_id>/', views.horse_detail_view, name='horse_detail'),
    path('scores/', views.horse_scores_view, name='horse_scores'),
    path('scores/<int:race_id>/', views.horse_scores_view, name='race_scores'),
    path('score/<int:score_id>/', views.horse_score_detail, name='horse_score_detail'),
    path('rankings/<str:race_date>/<int:race_no>/<str:field_name>/', 
         views.race_rankings_view, name='race_rankings'),
    path('horse/<str:horse_name>/history/', 
         views.horse_rankings_history_view, name='horse_rankings_history'),
    path('top-rankings/', views.top_rankings_view, name='top_rankings'),
    path('top-rankings/<int:days>/', views.top_rankings_view, name='top_rankings_days'),
    path('rankings/', views.available_races_view, name='available_races'),
   
]