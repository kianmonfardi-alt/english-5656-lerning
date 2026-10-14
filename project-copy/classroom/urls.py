
from django.urls import path
from . import views

urlpatterns = [
    # ورود و پنل‌ها
    path("", views.login_page, name="login"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("student/", views.student_dashboard, name="student_dashboard"),

    # مدیریت کاربران
    path("users/", views.users_page, name="users"),

    # اصطلاحات انگلیسی
    path("expressions/", views.expressions_page, name="expressions"),

    # بازی‌ها
    path("games/", views.games_page, name="games"),

    # آزمون‌ها
    path("teacher/exams/", views.teacher_exams_page, name="teacher_exams"),
    path("student/exams/", views.student_exams_page, name="student_exams"),

    # پیام‌ها و مجوز ارسال پیام
    path("messages/", views.messages_page, name="messages"),
    path(
        "messages/permissions/",
        views.manage_message_permission,
        name="manage_message_permission",
    ),

    # اعلان‌ها
    path(
        "notifications/<int:notification_id>/read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path(
        "notifications/read-all/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),

    # خروج از حساب
    path("logout/", views.logout_view, name="logout"),
]
