TO CHECK WHICH FILE IS BEING USED
>>> import racecard.models
>>> print(racecard.models.__file__)
/home/wrf/deployed/django/projects/sa_racecard/racecard/models.py
>>> print(racecard.admin.__file__)
/home/wrf/deployed/django/projects/sa_racecard/racecard/admin.py
>>> 



TO CHECK WHICH FILE IS BEING USED


DATABSE ACTIONS::

find racecard/migrations -name "0*.py" -not -name "__init__.py" -delete
find racecard/migrations -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -r {} +


Change to another database e.g. postgres
race_card=# DROP DATABASE race_card;
ERROR:  cannot drop the currently open database
race_card=# \c postgres
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_256_GCM_SHA384, compression: off)
You are now connected to database "postgres" as user "postgres".
postgres=# DROP DATABASE race_card;
DROP DATABASE
postgres=# CREATE DATABASE race_card;
CREATE DATABASE
postgres=# 


REMOVE MIGRATIONS
=================
# Delete the migrations folder if it exists
rm -rf racecard_02/migrations/

# Recreate migrations folder
mkdir racecard_02/migrations
touch racecard_02/migrations/__init__.py

# Now create migrations
python manage.py makemigrations racecard_02

VERIFY APP IS WORKING
=====================
Verify the app is working
python
# Test in Django shell
python manage.py shell

# Try to import your AI models
from racecard_02.models import AIPrediction
print("AI models imported successfully!")

# Or check if tables will be created
from django.db import connection
tables = connection.introspection.table_names()
ai_tables = [t for t in tables if t.startswith('racecard_02_')]
print(f"AI tables to be created: {ai_tables}")


Action	                  Windows/Linux Shortcut	  Mac Shortcut
Find in Current File     	Ctrl + F	               Cmd + F
Find Across All Files	    Ctrl + Shift + F	       Cmd + Shift + F
Replace in Current File	    Ctrl + H	               Cmd + Option + F
Go to Line	Ctrl + G	    Ctrl + G
Find next occurrence	     F3	F3
Find previous occurrence	Shift + F3	                Shift + F3


Action                           	How to Do It                                                          	Result
Indent Forward	                    Press Tab after a line ending with :, or let the editor auto-indent.	Starts a new code block (e.g., function, loop, condition).
Indent Backward	                    Press Backspace or Shift+Tab at the start of a line.	                Ends the current code block.


DELETE DATA IN TABLES::

Race.objects.all().delete()
Horse.objects.all().delete() 
HorseScore.objects.all().delete()
Run.objects.all().delete()
Ranking.objects.all().delete()

# Delete ALL objects of a model
Race.objects.all().delete()
Horse.objects.all().delete()
Run.objects.all().delete()

# Delete specific objects
Race.objects.filter(race_no=1).delete()  # Delete races with race_no = 1
Race.objects.filter(race_date__year=2024).delete()  # Delete 2024 races

# Delete a single specific object
race = Race.objects.get(id=1)
race.delete()

# Delete using ID
Race.objects.filter(id=1).delete()



Re install environment::

cd /home/wrf/deployed/chawas_03
rm -rf chawas_03_env
python3.12 -m venv chawas_03_env
source chawas_03_env/bin/activate
pip install -r requirements.txt



DATE

Examples:

Include date + hour only (UTC, 24-hour clock):

from datetime import datetime, timezone

today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H")
print(today)   # e.g. "2025-09-25 14"


Include date + hour:minute:

today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
print(today)   # e.g. "2025-09-25 14:37"


Full timestamp with seconds:

today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
print(today)   # e.g. "2025-09-25 14:37:05"