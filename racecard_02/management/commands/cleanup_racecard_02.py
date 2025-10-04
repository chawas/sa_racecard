from django.core.management.base import BaseCommand
from racecard_02.models import HorseScore, Horse, Race

class Command(BaseCommand):
    help = 'Delete all data from racecard_02 app'
    
    def handle(self, *args, **options):
        # Delete in reverse order to avoid foreign key constraints
        HorseScore.objects.all().delete()
        self.stdout.write("✅ Deleted all HorseScore objects")
        
        Horse.objects.all().delete()
        self.stdout.write("✅ Deleted all Horse objects")
        
        Race.objects.all().delete()
        self.stdout.write("✅ Deleted all Race objects")
        
        self.stdout.write(self.style.SUCCESS("🎉 All racecard_02 data deleted successfully!"))