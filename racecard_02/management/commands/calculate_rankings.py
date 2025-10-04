# management/commands/calculate_rankings.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from services.ranking_service import RankingService

class Command(BaseCommand):
    help = 'Calculate and save horse rankings based on scores'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to calculate rankings for (YYYY-MM-DD)'
        )
    
    def handle(self, *args, **options):
        date_str = options.get('date')
        race_date = None
        
        if date_str:
            try:
                race_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                self.stdout.write(f"Calculating rankings for date: {race_date}")
            except ValueError:
                self.stderr.write("Invalid date format. Use YYYY-MM-DD")
                return
        
        rankings_created = RankingService.calculate_rankings(race_date)
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created/updated {rankings_created} rankings"
            )
        )