from django import forms
from .models import Post, PostReport


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content", "image", "video"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "composer-textarea",
                "placeholder": "What do you want to share?",
                "rows": 4,
            }),
        }


class EditPostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content", "image", "video"]
        widgets = {
            "content": forms.Textarea(attrs={
                "class": "edit-textarea",
                "placeholder": "Update your post...",
                "rows": 5,
            }),
        }


class PostReportForm(forms.ModelForm):
    class Meta:
        model = PostReport
        fields = ["reason", "details"]
        widgets = {
            "reason": forms.Select(attrs={
                "class": "report-select",
            }),
            "details": forms.Textarea(attrs={
                "class": "report-textarea",
                "placeholder": "Add more details. Optional.",
                "rows": 3,
            }),
        }