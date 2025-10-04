# racecard/forms.py
from django import forms
from django.utils import timezone

class DateSelectionForm(forms.Form):
    selected_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date(),
        label="Select Date"
    )
    race_number = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'All races'}),
        label="Race Number (optional)",
        min_value=1
    )