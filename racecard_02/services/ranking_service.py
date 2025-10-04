# services/ranking_service.py
from django.db import transaction
from datetime import datetime
from racecard.models import Ranking, Race, Horse, HorseScore

# Ranking Service (kept outside Command class for potential reuse)
class RankingService:
    @staticmethod
    def get_race_rankings(race):
        """Get rankings for a specific race"""
        return Ranking.objects.filter(race=race).select_related('horse').order_by('rank')
    
    @staticmethod
    def get_horse_ranking(race, horse):
        """Get ranking for a specific horse in a race"""
        try:
            return Ranking.objects.get(race=race, horse=horse)
        except Ranking.DoesNotExist:
            return None
    
    @staticmethod
    def get_top_rankings(days=30, limit=10):
        """Get top rankings from recent races"""
        from datetime import date, timedelta
        start_date = date.today() - timedelta(days=days)
        
        return Ranking.objects.filter(
            race__race_date__gte=start_date,
            rank=1
        ).select_related('race', 'horse').order_by('-race__race_date')[:limit]

    # Simple function to calculate rankings without saving (for views)
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
                ranking_obj = {
                    'race': race,
                    'horse': horse_score.horse,
                    'rank': rank,
                    'overall_score': horse_score.overall_score,
                    'speed_score': horse_score.speed_score,
                    'form_score': horse_score.form_score,
                    'class_score': horse_score.class_score,
                    'consistency_score': horse_score.consistency_score,
                    'value_score': horse_score.value_score,
                    'physical_score': horse_score.physical_score,
                    'intangible_score': horse_score.intangible_score,
                    'speed_rating_score': horse_score.speed_rating_score,
                    'best_mr_score': horse_score.best_mr_score,
                    'current_mr_score': horse_score.current_mr_score,
                    'jt_score': horse_score.jt_score,
                    'odds_score': horse_score.odds_score,
                    'weight_score': horse_score.weight_score,
                    'draw_score': horse_score.draw_score,
                    'blinkers_score': horse_score.blinkers_score,
                }
                all_rankings.append(ranking_obj)
        
        return all_rankings

    if __name__ == "__main__":
        # For standalone testing
        command = Command()
        command.stdout = sys.stdout
        command.stderr = sys.stderr
        command.handle()