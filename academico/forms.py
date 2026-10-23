from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from pathlib import Path
from academico.domain.policies import validate_course_code
from academico.models import AIConfiguration, Course, Cycle, StudyFile, StudySession


class CycleForm(forms.ModelForm):
    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner or getattr(self.instance, "owner", None)
        self.fields["number"].label = "Número de ciclo"
        self.fields["start_date"].label = "Fecha de inicio"

    def clean_number(self):
        number = self.cleaned_data["number"].strip()
        if Cycle.objects.filter(owner=self.owner, number=number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya tienes un ciclo con ese número.")
        return number

    class Meta:
        model = Cycle
        fields = ["number", "start_date"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class CourseForm(forms.ModelForm):
    def __init__(self, *args, cycle=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cycle = cycle or getattr(self.instance, "cycle", None)
        self.fields["code"].label = "Código (máximo 4 caracteres)"
        self.fields["name"].label = "Nombre del curso"
    class Meta:
        model = Course
        fields = ["code", "name"]

    def clean_code(self):
        code = validate_course_code(self.cleaned_data["code"])
        if Course.objects.filter(cycle=self.cycle, code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un curso con ese código en este ciclo.")
        return code


class SessionScopeField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        number = str(obj.number) if obj.number is not None else "sin asignar"
        return f"{obj.get_kind_display()} · {obj.title} · N.º {number}"


class SessionForm(forms.ModelForm):
    scope = SessionScopeField(
        queryset=StudySession.objects.none(), required=False,
        label="Alcance (para práctica o examen)",
        help_text="Selecciona las sesiones de clase o lectura que se evaluarán.",
        widget=forms.CheckboxSelectMultiple,
    )
    class Meta:
        model = StudySession
        fields = ["kind", "number", "title", "essay_type", "essay_type_other", "performed_on", "description", "scope"]
        widgets = {"performed_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}
    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_kind = self.instance.kind
        self.fields["performed_on"].initial = timezone.localdate
        self.fields["kind"].label = "Tipo de sesión"
        self.fields["number"].label = "Número de sesión"
        self.fields["title"].label = "Título"
        self.fields["essay_type"].label = "Tipo de ensayo"
        self.fields["essay_type"].help_text = "Elige el formato solicitado por el docente. Si no aparece, selecciona «Otro»."
        self.fields["essay_type_other"].label = "Especifica el tipo de ensayo"
        self.fields["essay_type_other"].help_text = "Escribe el nombre del tipo indicado por el docente."
        self.fields["performed_on"].label = "Fecha de realización"
        self.fields["description"].label = "Descripción"
        if course:
            self.fields["scope"].queryset = course.sessions.filter(kind__in=["class", "reading"]).exclude(pk=self.instance.pk)
            if self.instance.pk:
                self.initial["scope"] = self.instance.scope_sessions.values_list("pk", flat=True)

    def clean(self):
        cleaned_data = super().clean()
        kind = cleaned_data.get("kind")
        scope = cleaned_data.get("scope")
        essay_type = cleaned_data.get("essay_type")
        essay_type_other = cleaned_data.get("essay_type_other", "").strip()
        if kind in {StudySession.Type.CLASS, StudySession.Type.PRACTICE, StudySession.Type.EXAM} and not cleaned_data.get("number"):
            self.add_error("number", "Indica un número mayor que cero para esta sesión.")
        if kind == StudySession.Type.TASK and not cleaned_data.get("description", "").strip():
            self.add_error("description", "Describe en qué consiste la tarea.")
        if self.instance.pk and kind != self.original_kind and (
                self.instance.files.exists() or self.instance.artifacts.exists() or self.instance.attempts.exists()):
            self.add_error("kind", "Esta sesión ya tiene materiales o resultados. Crea otra sesión para usar un tipo diferente.")
        if kind not in {StudySession.Type.PRACTICE, StudySession.Type.EXAM, StudySession.Type.TASK}:
            cleaned_data["scope"] = StudySession.objects.none()
        if kind in {StudySession.Type.PRACTICE, StudySession.Type.EXAM} and not scope:
            self.add_error("scope", "Selecciona al menos una sesión de clase o lectura para definir el alcance.")
        if kind == StudySession.Type.ESSAY and not essay_type:
            self.add_error("essay_type", "Selecciona el tipo de ensayo antes de guardar la sesión.")
        elif kind == StudySession.Type.ESSAY and essay_type == StudySession.EssayType.OTHER and not essay_type_other:
            self.add_error("essay_type_other", "Especifica el tipo de ensayo indicado por el docente.")
        elif kind != StudySession.Type.ESSAY:
            cleaned_data["essay_type"] = None
            cleaned_data["essay_type_other"] = ""
        elif essay_type != StudySession.EssayType.OTHER:
            cleaned_data["essay_type_other"] = ""
        return cleaned_data


class UploadForm(forms.ModelForm):
    category = forms.ChoiceField(label="Tipo de archivo")
    file = forms.FileField(label="Seleccionar archivo")

    class Meta:
        model = StudyFile
        fields = ["category", "file"]

    CATEGORIES_BY_SESSION = {
        StudySession.Type.CLASS: [
            (StudyFile.Category.TRANSCRIPT, "Transcripción de clase"),
            (StudyFile.Category.MATERIAL, "Material complementario"),
            (StudyFile.Category.SLIDE, "Diapositivas"),
            (StudyFile.Category.MODEL, "Modelo de práctica o examen del profesor"),
            (StudyFile.Category.MAP, "Mapa conceptual del alumno"),
        ],
        StudySession.Type.READING: [
            (StudyFile.Category.MATERIAL, "Material de lectura"),
            (StudyFile.Category.MAP, "Mapa conceptual del alumno"),
        ],
        StudySession.Type.PRACTICE: [
            (StudyFile.Category.MODEL, "Modelo de práctica del profesor"),
        ],
        StudySession.Type.EXAM: [
            (StudyFile.Category.MODEL, "Examen modelo del profesor"),
        ],
        StudySession.Type.ESSAY: [
            (StudyFile.Category.MATERIAL, "PDF de referencia"),
            (StudyFile.Category.DRAFT, "Borrador de ensayo en Word (.docx)"),
        ],
        StudySession.Type.TASK: [
            (StudyFile.Category.ASSIGNMENT, "Consigna del profesor (PDF)"),
            (StudyFile.Category.MATERIAL, "Material de apoyo"),
        ],
    }

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.fields["category"].choices = self.CATEGORIES_BY_SESSION.get(session.kind, []) if session else []
        if session and session.kind == StudySession.Type.READING:
            self.fields["file"].widget.attrs["accept"] = ".pdf,application/pdf"
        elif session and session.kind == StudySession.Type.ESSAY:
            self.fields["file"].widget.attrs["accept"] = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            self.fields["file"].widget.attrs["accept"] = ".pdf,.pptx,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.webp,.gif"

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        category = self.cleaned_data.get("category")
        suffix = Path(uploaded_file.name).suffix.lower()
        if uploaded_file.size > 20 * 1024 * 1024:
            raise forms.ValidationError("El archivo debe ocupar como máximo 20 MB.")
        if category == StudyFile.Category.MAP:
            from academico.infrastructure.images import image_mime_type
            header = uploaded_file.read(32)
            uploaded_file.seek(0)
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"} or not image_mime_type(header):
                raise forms.ValidationError("Carga tu mapa como imagen PNG, JPEG, GIF o WebP válida.")
            return uploaded_file
        if category == StudyFile.Category.TRANSCRIPT and suffix != ".txt":
            raise forms.ValidationError("La transcripción debe cargarse como archivo de texto .txt.")
        if category == StudyFile.Category.ASSIGNMENT and suffix != ".pdf":
            raise forms.ValidationError("La consigna del profesor debe cargarse en PDF.")
        if suffix not in {".pdf", ".pptx", ".docx", ".txt", ".md", ".csv"}:
            raise forms.ValidationError("Formato no permitido. Usa PDF, Word, PowerPoint o un archivo de texto.")
        if (self.session and self.session.kind == StudySession.Type.READING
                and not uploaded_file.name.lower().endswith(".pdf")):
            raise forms.ValidationError("Las sesiones de lectura deben cargarse en formato PDF.")
        if self.session and self.session.kind == StudySession.Type.ESSAY:
            suffix = uploaded_file.name.lower().rsplit(".", 1)[-1] if "." in uploaded_file.name else ""
            if category == StudyFile.Category.MATERIAL and suffix != "pdf":
                raise forms.ValidationError("Los documentos de referencia del ensayo deben cargarse en PDF.")
            if category == StudyFile.Category.DRAFT and suffix != "docx":
                raise forms.ValidationError("El borrador del ensayo debe cargarse como documento Word .docx.")
        return uploaded_file


class EssayQuestionForm(forms.Form):
    prompt = forms.CharField(
        max_length=2000,
        label="¿Qué quieres consultar sobre tu ensayo?",
        help_text="La respuesta se elaborará únicamente con los PDF de referencia cargados en esta sesión.",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Por ejemplo: ¿Qué argumentos de estos textos apoyan mi tesis?"}),
    )


class ExamGenerationForm(forms.Form):
    exam_type = forms.ChoiceField(choices=[
        ("multiple_choice", "Alternativas"),
        ("open_response", "Preguntas abiertas"),
    ], label="Tipo de examen")
    level = forms.ChoiceField(choices=[
        ("normal", "Normal"),
        ("advanced", "Avanzado"),
    ], label="Nivel")
    question_count = forms.IntegerField(
        min_value=3, max_value=15, initial=8, label="Cantidad de preguntas",
        help_text="Elige entre 3 y 15 preguntas.",
    )


class DeepSeekForm(forms.Form):
    base_url = forms.URLField(initial="https://api.deepseek.com")
    model = forms.CharField(max_length=80, initial="deepseek-chat")
    vision_model = forms.CharField(max_length=80, initial="deepseek-flash", required=False,
                                  label="Modelo para revisar imágenes", help_text="Debe admitir imágenes. Por defecto: deepseek-flash.")
    api_key = forms.CharField(required=False, widget=forms.PasswordInput(render_value=False),
                              help_text="Déjala vacía para conservar la clave guardada.")


class UserCreateForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    class Meta:
        model = get_user_model()
        fields = ["email", "first_name", "last_name", "password"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_password = self.instance.password
        for name, label in [("email", "Correo electrónico"), ("first_name", "Nombre"), ("last_name", "Apellido")]:
            self.fields[name].required = True
            self.fields[name].label = label
        if self.instance.pk:
            self.fields["password"].required = False
            self.fields["password"].help_text = "Déjala vacía para conservar la contraseña actual."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists() or User.objects.filter(username__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ese correo ya tiene una cuenta.")
        if self.instance.is_superuser and self.instance.email.lower() == "civangonzales@gmail.com" and email != "civangonzales@gmail.com":
            raise forms.ValidationError("La cuenta administradora debe conservar su correo.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        else:
            user.password = self.original_password
        if commit: user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Correo electrónico")

    def clean_username(self):
        email = self.cleaned_data["username"].strip().lower()
        user = get_user_model().objects.filter(email__iexact=email).first()
        return user.username if user else email
