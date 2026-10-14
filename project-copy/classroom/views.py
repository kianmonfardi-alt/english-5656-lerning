
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    UserProfile,
    Expression,
    Game,
    WeeklyExam,
    ExamQuestion,
    ExamAttempt,
    ExamAnswer,
    Message,
    MessagePermission,
    Notification,
)


# -----------------------------------------
# نقش کاربران و هدایت به پنل مربوطه
# -----------------------------------------

def get_user_role(user):
    if not user.is_authenticated:
        return None

    if user.is_superuser:
        return "manager"

    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        return None


def role_redirect(role):
    routes = {
        "manager": "dashboard",
        "teacher": "teacher_dashboard",
        "student": "student_dashboard",
    }
    return routes.get(role, "login")


def require_role(request, allowed_roles):
    role = get_user_role(request.user)

    if role not in allowed_roles:
        messages.error(
            request,
            "You do not have permission to access this page.",
        )
        return None

    return role


# -----------------------------------------
# ابزارهای اعلان
# -----------------------------------------

def create_notification(recipient, title, message):
    """ساخت اعلان برای یک کاربر مشخص."""
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
    )


def notify_users(users, title, message):
    """ساخت اعلان برای چند کاربر."""
    notifications = [
        Notification(
            recipient=user,
            title=title,
            message=message,
        )
        for user in users
    ]

    if notifications:
        Notification.objects.bulk_create(notifications)


def get_notification_context(user):
    notifications = Notification.objects.filter(
        recipient=user,
    ).order_by("-created_at")

    return {
        "notifications": notifications[:50],
        "unread_notification_count": notifications.filter(
            is_read=False,
        ).count(),
    }


@login_required(login_url="login")
@require_POST
def mark_notification_read(request, notification_id):
    """علامت‌گذاری اعلان متعلق به کاربر واردشده."""
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=request.user,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return redirect(role_redirect(get_user_role(request.user)))


@login_required(login_url="login")
@require_POST
def mark_all_notifications_read(request):
    """علامت‌گذاری همه اعلان‌های کاربر به‌عنوان خوانده‌شده."""
    Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    messages.success(request, "All notifications marked as read.")
    return redirect(role_redirect(get_user_role(request.user)))


# -----------------------------------------
# محاسبه رتبه و پیشرفت دانش‌آموزان
# -----------------------------------------

def get_student_statistics():
    students = User.objects.filter(
        profile__role="student",
        is_active=True,
    ).order_by("username")

    leaderboard = []

    for student in students:
        attempts = ExamAttempt.objects.filter(
            student=student,
        ).select_related("exam")

        attempt_count = attempts.count()
        total_earned = 0
        total_possible = 0
        percentage_sum = 0

        for attempt in attempts:
            question_points = ExamQuestion.objects.filter(
                exam=attempt.exam,
            ).aggregate(total=Sum("points"))["total"] or 0

            total_earned += attempt.score
            total_possible += question_points

            if question_points > 0:
                percentage_sum += (
                    attempt.score / question_points
                ) * 100

        average_percentage = (
            percentage_sum / attempt_count
            if attempt_count else 0
        )

        leaderboard.append({
            "student": student,
            "username": student.username,
            "attempt_count": attempt_count,
            "total_score": total_earned,
            "average_percentage": round(average_percentage, 2),
            "total_possible": total_possible,
        })

    leaderboard.sort(
        key=lambda item: (
            item["average_percentage"],
            item["attempt_count"],
            item["total_score"],
        ),
        reverse=True,
    )

    for index, item in enumerate(leaderboard, start=1):
        item["rank"] = index
        item["is_top_student"] = (
            index == 1 and item["attempt_count"] > 0
        )

    top_student = next(
        (
            item for item in leaderboard
            if item["attempt_count"] > 0
        ),
        None,
    )

    return leaderboard, top_student


def get_student_progress(student):
    attempts = ExamAttempt.objects.filter(
        student=student,
    ).select_related("exam").order_by("-submitted_at")

    results = []

    for attempt in attempts:
        possible_score = ExamQuestion.objects.filter(
            exam=attempt.exam,
        ).aggregate(total=Sum("points"))["total"] or 0

        percentage = (
            round(attempt.score / possible_score * 100, 2)
            if possible_score > 0 else 0
        )

        results.append({
            "attempt": attempt,
            "exam": attempt.exam,
            "score": attempt.score,
            "possible_score": possible_score,
            "percentage": percentage,
        })

    return {
        "results": results,
        "exam_count": len(results),
        "total_score": sum(item["score"] for item in results),
        "average_percentage": (
            round(
                sum(item["percentage"] for item in results)
                / len(results),
                2,
            )
            if results else 0
        ),
    }


# -----------------------------------------
# ورود کاربران
# -----------------------------------------

def login_page(request):
    if request.user.is_authenticated:
        role = get_user_role(request.user)

        if role:
            return redirect(role_redirect(role))

        logout(request)
        messages.error(request, "Your account has no valid role.")
        return redirect("login")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None or not user.is_active:
            messages.error(request, "Invalid username or password.")
            return render(request, "login.html")

        role = get_user_role(user)

        if role not in ("manager", "teacher", "student"):
            messages.error(request, "Your account has no valid role.")
            return render(request, "login.html")

        login(request, user)
        return redirect(role_redirect(role))

    return render(request, "login.html")


# -----------------------------------------
# پنل مدیر
# -----------------------------------------

@login_required(login_url="login")
def dashboard(request):
    role = require_role(request, ("manager",))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    leaderboard, top_student = get_student_statistics()

    context = {
        "leaderboard": leaderboard,
        "top_student": top_student,
        "student_count": User.objects.filter(
            profile__role="student",
            is_active=True,
        ).count(),
        "teacher_count": User.objects.filter(
            profile__role="teacher",
            is_active=True,
        ).count(),
        "exam_count": WeeklyExam.objects.count(),
        "game_count": Game.objects.count(),
        **get_notification_context(request.user),
    }

    return render(request, "dashboard.html", context)


# -----------------------------------------
# پنل معلم
# -----------------------------------------

@login_required(login_url="login")
def teacher_dashboard(request):
    role = require_role(request, ("teacher",))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    leaderboard, top_student = get_student_statistics()

    context = {
        "leaderboard": leaderboard,
        "top_student": top_student,
        **get_notification_context(request.user),
    }

    return render(request, "teacher_dashboard.html", context)


# -----------------------------------------
# پنل دانش‌آموز
# -----------------------------------------

@login_required(login_url="login")
def student_dashboard(request):
    role = require_role(request, ("student",))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    leaderboard, top_student = get_student_statistics()
    progress = get_student_progress(request.user)

    own_rank = next(
        (
            item["rank"]
            for item in leaderboard
            if item["student"].pk == request.user.pk
        ),
        None,
    )

    context = {
        "leaderboard": leaderboard,
        "top_student": top_student,
        "own_rank": own_rank,
        "progress": progress,
        **get_notification_context(request.user),
    }

    return render(request, "student_dashboard.html", context)


# -----------------------------------------
# مدیریت کاربران توسط مدیر
# -----------------------------------------

@login_required(login_url="login")
def users_page(request):
    role = require_role(request, ("manager",))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "create":
            username = request.POST.get("username", "").strip()
            password = request.POST.get("password", "")
            new_role = request.POST.get("role", "")

            if not username or not password:
                messages.error(
                    request,
                    "Username and password are required.",
                )
            elif new_role not in ("teacher", "student"):
                messages.error(request, "Invalid role.")
            elif len(password) < 8:
                messages.error(
                    request,
                    "Password must be at least 8 characters.",
                )
            elif User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
            else:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            username=username,
                            password=password,
                        )

                        UserProfile.objects.create(
                            user=user,
                            role=new_role,
                        )

                        if new_role == "student":
                            MessagePermission.objects.get_or_create(
                                student=user,
                            )

                    messages.success(
                        request,
                        "Account created successfully.",
                    )

                except IntegrityError:
                    messages.error(
                        request,
                        "Could not create this account.",
                    )

            return redirect("users")

        elif action == "delete":
            user_id = request.POST.get("user_id", "")

            try:
                target = User.objects.get(pk=user_id)

                if (
                    target.pk == request.user.pk
                    or target.is_superuser
                    or target.is_staff
                ):
                    messages.error(
                        request,
                        "This account is protected.",
                    )
                else:
                    target.delete()
                    messages.success(request, "Account deleted.")

            except (User.DoesNotExist, ValueError):
                messages.error(request, "User not found.")

            return redirect("users")

    users = User.objects.all().order_by("username")

    permission_map = {
        permission.student_id: permission.can_message
        for permission in MessagePermission.objects.filter(
            student__profile__role="student",
        )
    }

    for user in users:
        user.can_message = permission_map.get(user.pk, False)

    context = {
        "users": users,
        **get_notification_context(request.user),
    }

    return render(request, "users.html", context)


# -----------------------------------------
# مدیریت مجوز پیام دانش‌آموزان
# فقط مدیر مجاز است
# -----------------------------------------

@login_required(login_url="login")
@require_POST
def manage_message_permission(request):
    role = require_role(request, ("manager",))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    student_id = request.POST.get("student_id", "")
    action = request.POST.get("action", "")

    student = get_object_or_404(
        User,
        pk=student_id,
        is_active=True,
        profile__role="student",
    )

    permission, _ = MessagePermission.objects.get_or_create(
        student=student,
    )

    if action == "enable":
        permission.can_message = True
        permission.save()

        messages.success(
            request,
            f"Message permission enabled for {student.username}.",
        )

    elif action == "disable":
        permission.can_message = False
        permission.save()

        messages.success(
            request,
            f"Message permission disabled for {student.username}.",
        )

    else:
        messages.error(request, "Invalid permission action.")

    return redirect("users")


# -----------------------------------------
# کتابخانه اصطلاحات انگلیسی
# -----------------------------------------

@login_required(login_url="login")
def expressions_page(request):
    role = get_user_role(request.user)

    if role not in ("manager", "teacher", "student"):
        logout(request)
        messages.error(request, "Access denied.")
        return redirect("login")

    can_manage = role in ("manager", "teacher")

    if request.method == "POST":
        if not can_manage:
            messages.error(
                request,
                "You cannot edit expressions.",
            )
            return redirect("expressions")

        action = request.POST.get("action", "")

        if action == "save":
            expression_id = request.POST.get(
                "expression_id", ""
            ).strip()
            phrase = request.POST.get("phrase", "").strip()
            meaning = request.POST.get("meaning", "").strip()
            example = request.POST.get("example", "").strip()

            if not phrase or not meaning or not example:
                messages.error(
                    request,
                    "Please fill in every field.",
                )
                return redirect("expressions")

            if expression_id:
                expression = get_object_or_404(
                    Expression,
                    pk=expression_id,
                )

                expression.phrase = phrase
                expression.meaning = meaning
                expression.example = example
                expression.save()

                messages.success(request, "Expression updated.")

            else:
                Expression.objects.create(
                    phrase=phrase,
                    meaning=meaning,
                    example=example,
                )

                # اعلان اصطلاح جدید برای همه دانش‌آموزان فعال
                students = User.objects.filter(
                    is_active=True,
                    profile__role="student",
                )

                notify_users(
                    students,
                    "New expression",
                    f'A new expression was added: "{phrase}".',
                )

                messages.success(request, "Expression added.")

            return redirect("expressions")

        elif action == "delete":
            expression_id = request.POST.get(
                "expression_id", ""
            ).strip()

            expression = get_object_or_404(
                Expression,
                pk=expression_id,
            )

            expression.delete()
            messages.success(request, "Expression deleted.")
            return redirect("expressions")

    editing = None
    edit_id = request.GET.get("edit")

    if can_manage and edit_id:
        editing = get_object_or_404(Expression, pk=edit_id)

    expressions = Expression.objects.all().order_by("id")

    context = {
        "expressions": expressions,
        "can_manage": can_manage,
        "editing": editing,
        **get_notification_context(request.user),
    }

    return render(request, "expressions.html", context)


# -----------------------------------------
# ساخت و مدیریت بازی‌ها
# -----------------------------------------

@login_required(login_url="login")
def games_page(request):
    role = get_user_role(request.user)

    if role not in ("teacher", "manager"):
        messages.error(
            request,
            "شما اجازه دسترسی به این صفحه را ندارید.",
        )
        return redirect(role_redirect(role))

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        game_type = request.POST.get("game_type", "quiz")
        points_text = request.POST.get("points", "10")

        allowed_types = (
            "quiz",
            "matching",
            "puzzle",
            "expressions",
        )

        if not title:
            messages.error(request, "عنوان بازی را وارد کن.")

        elif game_type not in allowed_types:
            messages.error(request, "نوع بازی معتبر نیست.")

        elif (
            not points_text.isdigit()
            or not 0 <= int(points_text) <= 1000
        ):
            messages.error(
                request,
                "امتیاز باید عددی بین ۰ تا ۱۰۰۰ باشد.",
            )

        else:
            Game.objects.create(
                title=title,
                description=description,
                game_type=game_type,
                points=int(points_text),
                created_by=request.user,
            )

            messages.success(request, "بازی با موفقیت ساخته شد.")
            return redirect("games")

    games = Game.objects.order_by("-created_at")

    context = {
        "games": games,
        **get_notification_context(request.user),
    }

    return render(request, "games.html", context)


# -----------------------------------------
# مدیریت آزمون‌ها و سؤال‌ها
# -----------------------------------------

@login_required(login_url="login")
def teacher_exams_page(request):
    role = require_role(request, ("teacher", "manager"))

    if role is None:
        return redirect(role_redirect(get_user_role(request.user)))

    if request.method == "POST":
        action = request.POST.get("action", "create_exam")

        if action == "create_exam":
            title = request.POST.get("title", "").strip()
            description = request.POST.get("description", "").strip()
            start_text = request.POST.get("start_time", "").strip()
            end_text = request.POST.get("end_time", "").strip()

            if not title or not start_text or not end_text:
                messages.error(
                    request,
                    "عنوان و زمان شروع و پایان الزامی است.",
                )
                return redirect("teacher_exams")

            try:
                start = datetime.fromisoformat(start_text)
                end = datetime.fromisoformat(end_text)

                if timezone.is_naive(start):
                    start = timezone.make_aware(
                        start,
                        timezone.get_current_timezone(),
                    )

                if timezone.is_naive(end):
                    end = timezone.make_aware(
                        end,
                        timezone.get_current_timezone(),
                    )

                if end <= start:
                    messages.error(
                        request,
                        "زمان پایان باید بعد از شروع باشد.",
                    )
                    return redirect("teacher_exams")

                exam = WeeklyExam.objects.create(
                    title=title,
                    description=description,
                    start_time=start,
                    end_time=end,
                    is_active=True,
                    created_by=request.user,
                )

                # اعلان آزمون جدید برای دانش‌آموزان فعال
                students = User.objects.filter(
                    is_active=True,
                    profile__role="student",
                )

                notify_users(
                    students,
                    "New exam",
                    f'A new exam "{exam.title}" has been created.',
                )

                messages.success(request, "آزمون ساخته شد.")
                return redirect("teacher_exams")

            except ValueError:
                messages.error(
                    request,
                    "فرمت تاریخ یا زمان معتبر نیست.",
                )
                return redirect("teacher_exams")

        elif action == "add_question":
            exam_id = request.POST.get("exam_id", "")
            exam = get_object_or_404(WeeklyExam, pk=exam_id)

            text = request.POST.get(
                "question_text", ""
            ).strip()
            option_a = request.POST.get("option_a", "").strip()
            option_b = request.POST.get("option_b", "").strip()
            option_c = request.POST.get("option_c", "").strip()
            option_d = request.POST.get("option_d", "").strip()
            correct_option = request.POST.get(
                "correct_option", ""
            ).strip().lower()
            points_text = request.POST.get("points", "1")

            if not exam.is_active:
                messages.error(
                    request,
                    "این آزمون غیرفعال است.",
                )
                return redirect("teacher_exams")

            if not all((
                text, option_a, option_b, option_c, option_d
            )):
                messages.error(
                    request,
                    "متن سؤال و هر چهار گزینه الزامی است.",
                )
                return redirect("teacher_exams")

            if correct_option not in ("a", "b", "c", "d"):
                messages.error(
                    request,
                    "گزینه صحیح باید a، b، c یا d باشد.",
                )
                return redirect("teacher_exams")

            try:
                points = int(points_text)

                if not 1 <= points <= 1000:
                    raise ValueError

            except (TypeError, ValueError):
                messages.error(
                    request,
                    "امتیاز سؤال باید بین ۱ تا ۱۰۰۰ باشد.",
                )
                return redirect("teacher_exams")

            if exam.start_time <= timezone.now():
                messages.error(
                    request,
                    "پس از شروع آزمون نمی‌توان سؤال جدید اضافه کرد.",
                )
                return redirect("teacher_exams")

            ExamQuestion.objects.create(
                exam=exam,
                text=text,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_option=correct_option,
                points=points,
            )

            messages.success(
                request,
                "سؤال به آزمون اضافه شد.",
            )
            return redirect("teacher_exams")

        messages.error(request, "عملیات آزمون معتبر نیست.")
        return redirect("teacher_exams")

    exams = WeeklyExam.objects.prefetch_related(
        "questions"
    ).order_by("-start_time")

    context = {
        "exams": exams,
        **get_notification_context(request.user),
    }

    return render(request, "teacher_exams.html", context)


# -----------------------------------------
# آزمون‌های دانش‌آموز و ثبت پاسخ‌ها
# -----------------------------------------

@login_required(login_url="login")
def student_exams_page(request):
    role = get_user_role(request.user)

    if role != "student":
        messages.error(
            request,
            "این بخش مخصوص دانش‌آموزان است.",
        )
        return redirect(role_redirect(role))

    now = timezone.now()

    if request.method == "POST":
        if request.POST.get("action") != "submit_exam":
            messages.error(request, "عملیات آزمون معتبر نیست.")
            return redirect("student_exams")

        exam_id = request.POST.get("exam_id", "")

        exam = get_object_or_404(
            WeeklyExam,
            pk=exam_id,
            is_active=True,
            start_time__lte=now,
            end_time__gte=now,
        )

        questions = list(exam.questions.order_by("id"))

        if not questions:
            messages.error(
                request,
                "این آزمون هنوز سؤالی ندارد.",
            )
            return redirect("student_exams")

        try:
            with transaction.atomic():
                attempt = ExamAttempt.objects.create(
                    exam=exam,
                    student=request.user,
                    score=0,
                )

                total_score = 0

                for question in questions:
                    selected = request.POST.get(
                        f"question_{question.pk}", ""
                    ).strip().lower()

                    if selected not in ("a", "b", "c", "d"):
                        selected = ""

                    ExamAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        selected_option=selected,
                    )

                    if selected and selected == question.correct_option:
                        total_score += question.points

                attempt.score = total_score
                attempt.save(update_fields=["score"])

            messages.success(
                request,
                f"آزمون ثبت شد. امتیاز شما: {total_score}",
            )

        except IntegrityError:
            messages.error(
                request,
                "شما قبلاً در این آزمون شرکت کرده‌اید.",
            )

        return redirect("student_exams")

    exams = WeeklyExam.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gte=now,
    ).prefetch_related("questions").order_by("end_time")

    attempted_ids = list(
        ExamAttempt.objects.filter(
            student=request.user,
            exam__in=exams,
        ).values_list("exam_id", flat=True)
    )

    context = {
        "exams": exams,
        "attempted_ids": attempted_ids,
        **get_notification_context(request.user),
    }

    return render(request, "student_exams.html", context)


# -----------------------------------------
# سیستم پیام‌رسانی
# -----------------------------------------

@login_required(login_url="login")
def messages_page(request):
    role = get_user_role(request.user)

    if role not in ("manager", "teacher", "student"):
        messages.error(request, "دسترسی مجاز نیست.")
        return redirect("login")

    permission = None

    if role == "student":
        permission, _ = MessagePermission.objects.get_or_create(
            student=request.user,
        )

    if request.method == "POST":
        if role == "student" and not permission.can_message:
            messages.error(
                request,
                "اجازه ارسال پیام برای شما فعال نیست.",
            )
            return redirect("messages")

        recipient_id = request.POST.get("recipient", "")
        text = request.POST.get("text", "").strip()

        if not text:
            messages.error(request, "متن پیام را وارد کنید.")
            return redirect("messages")

        if len(text) > 2000:
            messages.error(
                request,
                "حداکثر طول پیام ۲۰۰۰ کاراکتر است.",
            )
            return redirect("messages")

        if role == "student":
            allowed_roles = ("manager", "teacher")
        else:
            allowed_roles = ("manager", "teacher", "student")

        recipient = get_object_or_404(
            User,
            pk=recipient_id,
            is_active=True,
            profile__role__in=allowed_roles,
        )

        if recipient.pk == request.user.pk:
            messages.error(
                request,
                "نمی‌توانید به خودتان پیام بدهید.",
            )
            return redirect("messages")

        Message.objects.create(
            sender=request.user,
            recipient=recipient,
            text=text,
        )

        # اعلان پیام جدید برای گیرنده
        create_notification(
            recipient,
            "New message",
            f"You received a new message from {request.user.username}.",
        )

        messages.success(request, "پیام با موفقیت ارسال شد.")
        return redirect("messages")

    if role == "student":
        recipients = User.objects.filter(
            is_active=True,
            profile__role__in=("manager", "teacher"),
        ).order_by("username")
    else:
        recipients = User.objects.filter(
            is_active=True,
            profile__role__in=("manager", "teacher", "student"),
        ).exclude(
            pk=request.user.pk,
        ).order_by("username")

    received_messages = Message.objects.filter(
        recipient=request.user,
    ).select_related("sender")

    sent_messages = Message.objects.filter(
        sender=request.user,
    ).select_related("recipient")

    context = {
        "received_messages": received_messages,
        "sent_messages": sent_messages,
        "recipients": recipients,
        "can_message": (
            permission.can_message if permission else True
        ),
        "role": role,
        **get_notification_context(request.user),
    }

    return render(request, "messages.html", context)


# -----------------------------------------
# خروج از حساب
# -----------------------------------------

@login_required(login_url="login")
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")
