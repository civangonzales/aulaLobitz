from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from functools import wraps
from pathlib import Path
import mimetypes
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
import json
from academico.application import services
from academico.forms import CycleForm, CourseForm, DeepSeekForm, EssayQuestionForm, ExamGenerationForm, SessionForm, UploadForm, UserCreateForm
from academico.infrastructure.repositories import cycles_for, get_course_for_user, get_session_for_user
from academico.models import AIArtifact, AIConfiguration, Cycle, Course, ExamAttempt, StudyFile, StudySession


def admin_required(view):
    @wraps(view)
    def checked(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_active and request.user.is_superuser and request.user.email.lower() == 'civangonzales@gmail.com'):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return checked


@login_required
def home(request):
    return render(request, "academico/home.html", {"cycles": cycles_for(request.user)})


@login_required
def cycle_edit(request, cycle_id):
    item = get_object_or_404(Cycle, pk=cycle_id, owner=request.user)
    form = CycleForm(request.POST or None, instance=item, owner=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Ciclo actualizado.')
        return redirect('home')
    return render(request, 'academico/form.html', {'form': form, 'title': 'Editar ciclo', 'cancel_url': '/'})


@login_required
def course_edit(request, course_id):
    item = get_course_for_user(request.user, course_id)
    form = CourseForm(request.POST or None, instance=item, cycle=item.cycle)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Curso actualizado.')
        return redirect('course_detail', course_id=item.pk)
    return render(request, 'academico/form.html', {'form': form, 'title': 'Editar curso'})


def _confirm_delete(request, item, cancel_url, success_url):
    from django.contrib.admin.utils import NestedObjects
    collector = NestedObjects(using='default')
    collector.collect([item])
    counts = [{'name': model._meta.verbose_name_plural, 'count': len(objects)} for model, objects in collector.data.items()]
    if request.method == 'POST':
        with transaction.atomic():
            item.delete()
        messages.success(request, 'Eliminación completada.')
        return redirect(success_url)
    return render(request, 'academico/confirm_delete.html', {'item': item, 'counts': counts, 'cancel_url': cancel_url})


@login_required
def cycle_delete(request, cycle_id):
    item = get_object_or_404(Cycle, pk=cycle_id, owner=request.user)
    return _confirm_delete(request, item, '/', '/')


@login_required
def course_delete(request, course_id):
    from django.urls import reverse
    item = get_course_for_user(request.user, course_id)
    return _confirm_delete(request, item, reverse('course_detail', args=[item.pk]), '/')


@login_required
def session_delete(request, session_id):
    from django.urls import reverse
    item = get_session_for_user(request.user, session_id)
    course_url = reverse('course_detail', args=[item.course_id])
    return _confirm_delete(request, item, reverse('session_detail', args=[item.pk]), course_url)


@login_required
@admin_required
def user_edit(request, user_id):
    from django.contrib.auth import update_session_auth_hash
    user = get_object_or_404(get_user_model(), pk=user_id)
    form = UserCreateForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        if user.pk == request.user.pk and form.cleaned_data.get('password'):
            update_session_auth_hash(request, user)
        messages.success(request, 'Usuario actualizado.')
        return redirect('users')
    return render(request, 'academico/form.html', {'form': form, 'title': 'Editar usuario'})


@login_required
@admin_required
def user_delete(request, user_id):
    from django.urls import reverse
    user = get_object_or_404(get_user_model(), pk=user_id)
    if user.pk == request.user.pk or user.email.lower() == 'civangonzales@gmail.com':
        raise PermissionDenied('La cuenta administradora no puede eliminarse.')
    return _confirm_delete(request, user, reverse('users'), reverse('users'))


@login_required
def view_file(request, file_id):
    item = get_object_or_404(StudyFile, pk=file_id, session__course__cycle__owner=request.user)
    return _file_response(item)


@login_required
def protected_media(request, file_path):
    item = get_object_or_404(StudyFile, file=file_path, session__course__cycle__owner=request.user)
    return _file_response(item)


def _file_response(item):
    try:
        stream = item.file.open('rb')
    except OSError as exc:
        raise Http404('El archivo ya no está disponible.') from exc
    suffix = Path(item.name).suffix.lower()
    inline = suffix in {'.pdf', '.txt', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
    content_type = 'text/plain; charset=utf-8' if suffix == '.txt' else mimetypes.guess_type(item.name)[0] or 'application/octet-stream'
    response = FileResponse(stream, as_attachment=not inline, filename=item.name, content_type=content_type)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_POST
def review_map(request, file_id):
    item = get_object_or_404(StudyFile.objects.select_related('session'), pk=file_id, session__course__cycle__owner=request.user)
    try:
        services.review_student_map(item)
        messages.success(request, 'Revisión del mapa guardada en el historial.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('session_detail', session_id=item.session_id)


@login_required
@require_POST
def recommend_task(request, session_id):
    item = get_session_for_user(request.user, session_id)
    try:
        services.generate_task_guidance(item)
        messages.success(request, 'Recomendación para la tarea generada.')
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect('session_detail', session_id=item.pk)


@login_required
def cycle_create(request):
    form = CycleForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        services.create_cycle(request.user, form.cleaned_data["number"], form.cleaned_data["start_date"])
        return redirect("home")
    return render(request, "academico/form.html", {"form": form, "title": "Nuevo ciclo"})


@login_required
def course_create(request, cycle_id):
    cycle = get_object_or_404(cycles_for(request.user), pk=cycle_id)
    form = CourseForm(request.POST or None, cycle=cycle)
    if request.method == "POST" and form.is_valid():
        services.create_course(cycle, form.cleaned_data["code"], form.cleaned_data["name"])
        return redirect("home")
    return render(request, "academico/form.html", {"form": form, "title": f"Curso · {cycle}"})


@login_required
def course_detail(request, course_id):
    course = get_course_for_user(request.user, course_id)
    return render(request, "academico/course.html", {"course": course})


@login_required
def session_create(request, course_id):
    course = get_course_for_user(request.user, course_id)
    form = SessionForm(request.POST or None, course=course)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False); item.course = course; item.save()
        item.scope_sessions.set(form.cleaned_data["scope"])
        return redirect("session_detail", session_id=item.id)
    return render(request, "academico/session_form.html", {"form": form, "title": f"Nueva sesión · {course.name}", "course": course})


@login_required
def session_edit(request, session_id):
    item = get_session_for_user(request.user, session_id)
    form = SessionForm(request.POST or None, instance=item, course=item.course)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        item.scope_sessions.set(form.cleaned_data["scope"])
        messages.success(request, "Sesión y alcance actualizados.")
        return redirect("session_detail", session_id=item.id)
    return render(request, "academico/session_form.html", {
        "form": form, "title": f"Editar sesión — {item.course.name}", "course": item.course,
        "session": item,
    })


@login_required
def session_detail(request, session_id):
    item = get_session_for_user(request.user, session_id)
    upload_form = UploadForm(session=item)
    summary = item.artifacts.filter(kind="summary_map").order_by("-created_at").first()
    map_artifact = item.artifacts.filter(kind="concept_map").order_by("-created_at").first()
    concept_tree = []
    if map_artifact:
        try:
            payload = json.loads(map_artifact.content)
            nodes = payload.get("nodes", [])
            by_id = {str(n.get("id")): {**n, "children": []} for n in nodes}
            roots = []
            for node in by_id.values():
                parent = node.get("parent_id")
                if parent is not None and str(parent) in by_id:
                    by_id[str(parent)]["children"].append(node)
                else:
                    roots.append(node)
            if len(roots) == 1:
                reachable = set()
                pending = [roots[0]]
                while pending:
                    node = pending.pop()
                    node_id = str(node.get("id"))
                    if node_id in reachable:
                        continue
                    reachable.add(node_id)
                    pending.extend(node["children"])
                if len(reachable) != len(by_id):
                    roots = []
            concept_tree = roots
        except (ValueError, TypeError, AttributeError):
            concept_tree = []
    essay_path = None
    essay_type_guidance = None
    essay_review = None
    essay_answers = []
    essay_draft = None
    essay_pdf_count = 0
    if item.kind == StudySession.Type.ESSAY:
        essay_path = item.artifacts.filter(kind="essay_path").order_by("-created_at").first()
        essay_type_guidance = item.artifacts.filter(kind="essay_type_guidance").order_by("-created_at").first()
        essay_review = item.artifacts.filter(kind="essay_review").order_by("-created_at").first()
        essay_draft = item.files.filter(category=StudyFile.Category.DRAFT).first()
        essay_pdf_count = sum(
            1 for study_file in item.files.filter(category=StudyFile.Category.MATERIAL)
            if study_file.file.name.lower().endswith(".pdf")
        )
        answer_artifacts = list(item.artifacts.filter(kind="essay_answer").order_by("-created_at")[:20])
        for artifact in reversed(answer_artifacts):
            try:
                answer = json.loads(artifact.content)
                essay_answers.append({**answer, "created_at": artifact.created_at})
            except (ValueError, TypeError):
                continue
    map_reviews = []
    for artifact in item.artifacts.filter(kind='map_review').order_by('-created_at'):
        metadata = artifact.metadata
        map_reviews.append({"artifact": artifact, "file_name": metadata.get('file_name', 'Mapa'),
                            "uploaded_at": parse_datetime(metadata.get('uploaded_at', ''))})
    map_uploads = {f.pk: {'file': f, 'name': f.name, 'uploaded_at': f.uploaded_at} for f in item.files.all() if f.category == StudyFile.Category.MAP}
    for artifact in item.artifacts.filter(kind='map_upload').order_by('-created_at'):
        metadata = artifact.metadata
        map_uploads.setdefault(metadata.get('file_id'), {'file': None, 'name': metadata.get('file_name', 'Mapa'), 'uploaded_at': artifact.created_at})
    task_guidance = item.artifacts.filter(kind='task_guidance').order_by('-created_at').first()
    current_signature = services.context_signature(item)
    displayed_artifacts = [a for a in (summary, essay_path, essay_review, task_guidance) if a]
    results_stale = any(a.metadata.get('context_signature') != current_signature for a in displayed_artifacts)
    return render(request, "academico/session.html", {"session": item, "upload_form": upload_form,
                  "summary": summary, "concept_tree": concept_tree,
                  "concept_title": json.loads(map_artifact.content).get("title", "Mapa conceptual") if map_artifact and concept_tree else "Mapa conceptual",
                  "exam_form": ExamGenerationForm(),
                  "attempts": item.attempts.order_by("-created_at"),
                  "essay_path": essay_path, "essay_type_guidance": essay_type_guidance,
                  "essay_review": essay_review,
                  "essay_answers": essay_answers,
                  "essay_draft": essay_draft, "essay_pdf_count": essay_pdf_count,
                  "essay_question_form": EssayQuestionForm(), "map_reviews": map_reviews,
                  "task_guidance": task_guidance, "results_stale": results_stale, "map_uploads": sorted(map_uploads.values(), key=lambda entry: entry['uploaded_at'], reverse=True),
                  "task_has_assignment": item.files.filter(category=StudyFile.Category.ASSIGNMENT).exists()})


@login_required
@require_POST
def upload_file(request, session_id):
    item = get_session_for_user(request.user, session_id)
    form = UploadForm(request.POST, request.FILES, session=item)
    if form.is_valid():
        file_item = form.save(commit=False); file_item.session = item; file_item.save()
        if item.kind == StudySession.Type.ESSAY and file_item.category == StudyFile.Category.DRAFT:
            for previous in item.files.filter(category=StudyFile.Category.DRAFT).exclude(pk=file_item.pk):
                previous.file.delete(save=False)
                previous.delete()
        messages.success(request, f"Archivo cargado: {file_item.file.name.rsplit('/', 1)[-1]}")
        if file_item.category == StudyFile.Category.MAP:
            AIArtifact.objects.create(session=item, kind='map_upload', content='', metadata={'file_id': file_item.pk, 'file_name': file_item.name, 'uploaded_at': file_item.uploaded_at.isoformat()})
        should_summarize = (item.kind == StudySession.Type.CLASS and file_item.category == StudyFile.Category.TRANSCRIPT
                            or item.kind == StudySession.Type.READING and file_item.category == StudyFile.Category.MATERIAL)
        if should_summarize:
            try:
                services.generate_session_summary(item)
                messages.success(request, 'Resumen y mapa conceptual generados automáticamente.')
            except ValidationError as exc:
                messages.warning(request, 'El archivo quedó guardado. No se pudo generar el resumen: ' + ' '.join(exc.messages) + ' Puedes reintentarlo con el botón de resumen.')
    else:
        errors = " ".join(message for field_errors in form.errors.values() for message in field_errors)
        messages.error(request, errors or "Selecciona un archivo y una categoría válida.")
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def delete_file(request, file_id):
    item = get_object_or_404(StudyFile, pk=file_id, session__course__cycle__owner=request.user)
    sid = item.session_id
    item.file.delete(save=False)
    item.delete()
    return redirect("session_detail", session_id=sid)


@login_required
@require_POST
def make_summary(request, session_id):
    item = get_session_for_user(request.user, session_id)
    try:
        services.generate_session_summary(item)
        messages.success(request, "Resumen y mapa conceptual generados desde los materiales de esta sesión.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def recommend_essay_path(request, session_id):
    item = get_session_for_user(request.user, session_id)
    try:
        services.generate_essay_path(item)
        messages.success(request, "Recomendación del proceso de ensayo generada.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def recommend_essay_type(request, session_id):
    item = get_session_for_user(request.user, session_id)
    try:
        services.recommend_essay_type(item)
        messages.success(request, "Orientación para elegir el tipo de ensayo generada.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def ask_essay_question(request, session_id):
    item = get_session_for_user(request.user, session_id)
    form = EssayQuestionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Escribe una consulta de hasta 2000 caracteres.")
        return redirect("session_detail", session_id=item.id)
    try:
        services.answer_essay_question(item, form.cleaned_data["prompt"])
        messages.success(request, "Consulta respondida usando los PDF de referencia de esta sesión.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def review_essay_draft(request, session_id):
    item = get_session_for_user(request.user, session_id)
    try:
        services.review_essay(item)
        messages.success(request, "Revisión del borrador generada según el tipo de ensayo elegido.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("session_detail", session_id=item.id)


@login_required
@require_POST
def start_exam(request, session_id):
    item = get_session_for_user(request.user, session_id)
    if item.kind not in {StudySession.Type.CLASS, StudySession.Type.READING,
                         StudySession.Type.PRACTICE, StudySession.Type.EXAM}:
        messages.error(request, "Los exámenes se pueden generar desde una sesión de clase, lectura, práctica o examen.")
        return redirect("session_detail", session_id=item.id)
    form = ExamGenerationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Revisa el tipo, nivel y cantidad de preguntas del examen.")
        return redirect("session_detail", session_id=item.id)
    try:
        attempt = services.generate_exam(
            item,
            form.cleaned_data["exam_type"],
            form.cleaned_data["level"],
            form.cleaned_data["question_count"],
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("session_detail", session_id=item.id)
    return redirect("exam_attempt_detail", attempt_id=attempt.id)


@login_required
def exam_attempt_detail(request, attempt_id):
    from django.utils import timezone

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("session__course__cycle"),
        pk=attempt_id,
        session__course__cycle__owner=request.user,
    )
    if not attempt.completed_at and not attempt.started_at:
        ExamAttempt.objects.filter(pk=attempt.pk, started_at__isnull=True).update(started_at=timezone.now())
        attempt.refresh_from_db()
    if request.method == "POST" and not attempt.completed_at:
        answers = {question["id"]: request.POST.get(question["id"], "")
                   for question in attempt.payload.get("questions", [])}
        try:
            services.finish_exam_attempt(attempt, answers)
            messages.success(request, "Examen entregado y guardado en tu bitácora.")
            return redirect("exam_attempt_detail", attempt_id=attempt.id)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    questions = attempt.payload.get("questions", [])
    if not attempt.completed_at:
        questions = [
            {**{key: question[key] for key in ("id", "prompt", "options") if key in question},
             'submitted_answer': request.POST.get(question['id'], ''),
             'selected_option': int(request.POST[question['id']]) if request.POST.get(question['id'], '').isdigit() else None}
            for question in questions
        ]
    minutes, seconds = divmod(attempt.duration_seconds, 60)
    return render(request, "academico/exam_attempt.html", {
        "attempt": attempt,
        "questions": questions,
        "duration_label": f"{minutes} min {seconds} s",
        "exam_title": attempt.payload.get("title", "Examen"),
        "exam_instructions": attempt.payload.get("instructions", "Responde todas las preguntas."),
        "started_at": timezone.localtime(attempt.started_at or attempt.created_at),
    })


@login_required
@admin_required
def users(request):
    User = get_user_model()
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save(); user.is_staff = False; user.is_superuser = False; user.save()
            messages.success(request, "Alumno creado.")
            return redirect("users")
    else: form = UserCreateForm()
    return render(request, "academico/users.html", {"form": form, "users": User.objects.all().order_by("email")})


@login_required
@admin_required
def ai_settings(request):
    instance = AIConfiguration.objects.filter(pk=1).first()
    form = DeepSeekForm(request.POST or None, initial={"base_url": instance.base_url if instance else "https://api.deepseek.com",
                         "model": instance.model if instance else "deepseek-chat", "vision_model": instance.vision_model if instance else "deepseek-flash"})
    if request.method == "POST" and form.is_valid():
        try:
            services.save_deepseek_config(form.cleaned_data["base_url"], form.cleaned_data["model"], form.cleaned_data["api_key"], form.cleaned_data['vision_model'])
            messages.success(request, "Configuración guardada cifrada en el servidor.")
            return redirect("ai_settings")
        except Exception as exc:
            messages.error(request, str(exc))
    return render(request, "academico/ai_settings.html", {"form": form, "configured": bool(instance and instance.encrypted_api_key)})


@login_required
@admin_required
@require_POST
def test_ai(request):
    from academico.infrastructure.deepseek import complete
    try:
        result = complete("Responde solo: conexión correcta.")
        messages.success(request, result[:250])
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("ai_settings")
