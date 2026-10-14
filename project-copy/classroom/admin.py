from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import WeeklyExam, ExamQuestion, ExamAttempt, ExamAnswer


class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    extra = 1


@admin.register(WeeklyExam)
class WeeklyExamAdmin(admin.ModelAdmin):
    list_display = ("title", "start_time", "end_time", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title",)
    inlines = [ExamQuestionInline]


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("exam", "student", "score", "submitted_at")
    list_filter = ("exam",)
    search_fields = ("student__username", "exam__title")


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    list_display = ("attempt", "question", "selected_option")
