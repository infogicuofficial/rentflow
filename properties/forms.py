from django import forms

from .models import Document, Occupant, RentRevision


class OccupantForm(forms.ModelForm):
    class Meta:
        model = Occupant
        fields = [
            "full_name", "occupant_id", "email", "phone", "nid",
            "emergency_contact_name", "emergency_contact_phone", "photo", "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["doc_type", "title", "file"]


class RentRevisionForm(forms.ModelForm):
    class Meta:
        model = RentRevision
        fields = ["effective_from", "new_rent", "note"]
        widgets = {"effective_from": forms.DateInput(attrs={"type": "date"})}
