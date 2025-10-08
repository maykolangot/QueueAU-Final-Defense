from django import forms
from core.models import User

class ChangePasswordForm(forms.Form):
    new_password = forms.CharField(
        label="New Password", widget=forms.PasswordInput, min_length=6)
    confirm_password = forms.CharField(
        label="Repeat Password", widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get("new_password")
        pw2 = cleaned_data.get("confirm_password")

        if pw1 and pw2 and pw1 != pw2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data


class QueueModeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['process_mode']
        widgets = {
            'process_mode': forms.Select(attrs={'class': 'form-select'})
        }
        labels = {
            'process_mode': 'Queue Processing Mode'
        }


class CashierForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['name', 'email', 'windowNum', 'process_mode', 'verified', 'isOnline']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'windowNum': forms.NumberInput(attrs={'class': 'form-control'}),
            'process_mode': forms.Select(attrs={'class': 'form-select'}),
            'verified': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'isOnline': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

        