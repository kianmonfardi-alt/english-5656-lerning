
from django.db import models
from django.conf import settings


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("manager", "Manager"),
        ("teacher", "Teacher"),
        ("student", "Student"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="student",
    )

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class Expression(models.Model):
    phrase = models.CharField(max_length=200)
    meaning = models.CharField(max_length=300)
    example = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.phrase


class Game(models.Model):
    GAME_TYPES = [
        ("quiz", "Questions & Answers"),
        ("matching", "Matching"),
        ("puzzle", "Puzzle"),
        ("expressions", "Expression Challenge"),
    ]

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    game_type = models.CharField(
        max_length=20,
        choices=GAME_TYPES,
        default="quiz",
    )
    points = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_games",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class WeeklyExam(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exams",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_time"]

    def __str__(self):
        return self.title


class ExamQuestion(models.Model):
    OPTION_CHOICES = [
        ("a", "Option A"),
        ("b", "Option B"),
        ("c", "Option C"),
        ("d", "Option D"),
    ]

    exam = models.ForeignKey(
        WeeklyExam,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    text = models.CharField(max_length=500)
    option_a = models.CharField(max_length=250)
    option_b = models.CharField(max_length=250)
    option_c = models.CharField(max_length=250)
    option_d = models.CharField(max_length=250)
    correct_option = models.CharField(
        max_length=1,
        choices=OPTION_CHOICES,
    )
    points = models.PositiveIntegerField(default=1)

    def __str__(self):
        return self.text


class ExamAttempt(models.Model):
    exam = models.ForeignKey(
        WeeklyExam,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    score = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="unique_exam_attempt_per_student",
            ),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.exam.title}"


class ExamAnswer(models.Model):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    selected_option = models.CharField(
        max_length=1,
        choices=ExamQuestion.OPTION_CHOICES,
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_answer_per_question",
            ),
        ]

    def __str__(self):
        return f"{self.attempt.student.username} - {self.question_id}"


class MessagePermission(models.Model):
    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_permission",
    )
    can_message = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "Enabled" if self.can_message else "Disabled"
        return f"{self.student.username} - {status}"


class Message(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_class_messages",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_class_messages",
    )
    text = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.sender.username} → "
            f"{self.recipient.username}"
        )


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"
