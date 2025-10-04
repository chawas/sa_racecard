# racecard/forms.py
from django import forms
from django.utils import timezone


#from .models import ManualResult, ManualHorseResult

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



class ManualResultForm(forms.ModelForm):
    class Meta:
        model = ManualResult
        fields = ['verified']
        widgets = {'verified': forms.HiddenInput()}

class HorseResultForm(forms.ModelForm):
    class Meta:
        model = ManualHorseResult
        fields = ['horse', 'position', 'margin', 'time']
        widgets = {
            'horse': forms.HiddenInput(),
            'position': forms.NumberInput(attrs={'min': 1, 'max': 20, 'class': 'form-control'}),
            'margin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 1.5L'}),
            'time': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 1:23.45'}),
        }

# Formset for multiple horse results
HorseResultFormSet = forms.inlineformset_factory(
    ManualResult,
    ManualHorseResult,
    form=HorseResultForm,
    extra=0,
    can_delete=False,
    min_num=1,
    validate_min=True
)