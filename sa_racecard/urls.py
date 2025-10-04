"""
URL configuration for sa_race project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

## sa_racecard/urls.py
from django.contrib import admin
from django.urls import path, include
from racecard.views import home_view  # Import the home_view
from django.contrib import admin
from django.urls import path, include
from racecard_02.views import dashboard_view # Import dashboard view



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_view, name='home'),  # Root URL shows dashboard
    path('', include('racecard_02.urls')),  # Include app URLs at root level
]