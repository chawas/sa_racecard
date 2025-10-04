from django.apps import AppConfig

class AiRacingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'racecard_02'
    
    def ready(self):
        # Import signal handlers or other initialization code here
        # This method is called after Django is fully initialized
        pass