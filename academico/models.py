from django.conf import settings
from django.db import models


class Cycle(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cycles")
    number = models.CharField(max_length=40)
    start_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "number"]
        unique_together = [("owner", "number")]

    def __str__(self):
        return f"Ciclo {self.number}"


class Course(models.Model):
    cycle = models.ForeignKey(Cycle, on_delete=models.CASCADE, related_name="courses")
    code = models.CharField(max_length=4)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ["code"]
        unique_together = [("cycle", "code")]

    def __str__(self):
        return f"{self.code} · {self.name}"


class StudySession(models.Model):
    class Type(models.TextChoices):
        CLASS = "class", "Clase"
        READING = "reading", "Lectura"
        PRACTICE = "practice", "Práctica"
        EXAM = "exam", "Examen"
        ESSAY = "essay", "Ensayo"
        TASK = "task", "Tarea"

    class EssayType(models.TextChoices):
        ARGUMENTATIVE = "argumentative", "Argumentativo"
        EXPOSITIVE = "expositive", "Expositivo"
        ANALYTICAL = "analytical", "Analítico"
        COMPARATIVE = "comparative", "Comparativo"
        CRITICAL = "critical", "Crítico"
        CAUSE_EFFECT = "cause_effect", "Causa y efecto"
        PROBLEM_SOLUTION = "problem_solution", "Problema y solución"
        RESEARCH = "research", "Investigación"
        REFLECTIVE = "reflective", "Reflexivo"
        LITERATURE_REVIEW = "literature_review", "Revisión bibliográfica"
        NARRATIVE = "narrative", "Narrativo"
        DESCRIPTIVE = "descriptive", "Descriptivo"
        OTHER = "other", "Otro tipo indicado por el docente"
        UNSURE = "unsure", "No estoy seguro; necesito orientación"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sessions")
    kind = models.CharField(max_length=12, choices=Type.choices)
    number = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=200)
    essay_type = models.CharField(max_length=30, choices=EssayType.choices, null=True, blank=True)
    essay_type_other = models.CharField(max_length=120, blank=True)
    performed_on = models.DateField()
    description = models.TextField(blank=True)
    scope_sessions = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="used_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-performed_on", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def essay_type_display(self):
        if self.essay_type == self.EssayType.OTHER and self.essay_type_other.strip():
            return self.essay_type_other
        return self.get_essay_type_display() if self.essay_type else ""


class StudyFile(models.Model):
    class Category(models.TextChoices):
        TRANSCRIPT = "transcript", "Transcripción"
        MATERIAL = "material", "Lectura o material"
        SLIDE = "slide", "Slides"
        MAP = "map", "Mapa conceptual del alumno"
        MODEL = "model", "Modelo del profesor"
        DRAFT = "draft", "Borrador de ensayo"
        ASSIGNMENT = "assignment", "Consigna de la tarea (PDF)"

    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="study/%Y/%m/")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.MATERIAL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    @property
    def name(self):
        from pathlib import PurePosixPath
        return PurePosixPath(self.file.name).name

    @property
    def url(self):
        from django.urls import reverse
        return reverse("view_file", args=[self.pk])


class AIArtifact(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=30)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)


class ExamAttempt(models.Model):
    class Type(models.TextChoices):
        MULTIPLE_CHOICE = "multiple_choice", "Alternativas"
        OPEN_RESPONSE = "open_response", "Preguntas abiertas"

    class Level(models.TextChoices):
        NORMAL = "normal", "Normal"
        ADVANCED = "advanced", "Avanzado"

    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name="attempts")
    exam_type = models.CharField(max_length=20, choices=Type.choices)
    level = models.CharField(max_length=20, choices=Level.choices)
    score = models.CharField(max_length=20, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)

    @property
    def duration_display(self):
        minutes, seconds = divmod(self.duration_seconds, 60)
        if minutes:
            return f"{minutes} min {seconds} s"
        return f"{seconds} s"


class AIConfiguration(models.Model):
    base_url = models.URLField(default="https://api.deepseek.com")
    model = models.CharField(max_length=80, default="deepseek-chat")
    vision_model = models.CharField(max_length=80, default="deepseek-flash")
    encrypted_api_key = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DeepSeek · {self.model}"
