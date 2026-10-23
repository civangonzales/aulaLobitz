import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from academico.application import services
from academico.forms import SessionForm, UploadForm
from academico.infrastructure import deepseek as deepseek_client
from academico.models import AIArtifact, AIConfiguration, Course, Cycle, ExamAttempt, StudyFile, StudySession


class DeepSeekSkillTransportTests(TestCase):
    def test_all_application_skills_load_from_markdown_files(self):
        for skill_name, expected_text in [
            ("academic_summary", "summary_markdown"),
            ("concept_maps", "link_label"),
            ("essays", "Tipos de ensayo"),
            ("exam_creation", "JSON"),
            ("open_answer_evaluation", "score_percent"),
        ]:
            with self.subTest(skill=skill_name):
                self.assertIn(expected_text, services._load_skill(skill_name))

    def test_skill_is_sent_as_system_message_and_task_as_user_message(self):
        encryption_key = Fernet.generate_key().decode()
        cipher = Fernet(encryption_key.encode())
        AIConfiguration.objects.create(encrypted_api_key=cipher.encrypt(b"api-key-de-prueba").decode())
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "respuesta"}}],
        }).encode()

        with override_settings(DEEPSEEK_ENCRYPTION_KEY=encryption_key):
            with patch("academico.infrastructure.deepseek.urlopen", return_value=response) as urlopen:
                result = deepseek_client.complete("datos de la tarea", system_prompt="instrucciones del skill")

        self.assertEqual(result, "respuesta")
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["messages"], [
            {"role": "system", "content": "instrucciones del skill"},
            {"role": "user", "content": "datos de la tarea"},
        ])


class ExamWorkflowTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.settings_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.settings_override.enable()
        self.user = get_user_model().objects.create_user(
            username="alumno@example.com", email="alumno@example.com", password="password-segura"
        )
        self.cycle = Cycle.objects.create(owner=self.user, number="2026-I", start_date="2026-03-01")
        self.course = Course.objects.create(cycle=self.cycle, code="BIO", name="Biología")
        self.session = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.CLASS, number=1,
            title="Introducción a la biología", performed_on="2026-03-02",
        )
        StudyFile.objects.create(
            session=self.session,
            category=StudyFile.Category.TRANSCRIPT,
            file=SimpleUploadedFile("clase.txt", "La célula es la unidad básica de los seres vivos.".encode()),
        )

    def tearDown(self):
        self.settings_override.disable()
        self.temp_media.cleanup()

    def test_session_page_exposes_type_and_level_choices(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/sessions/{self.session.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generar examen con IA")
        self.assertContains(response, "Alternativas")
        self.assertContains(response, "Preguntas abiertas")
        self.assertContains(response, "Normal")
        self.assertContains(response, "Avanzado")

    @patch("academico.application.services.deepseek.complete")
    def test_student_can_start_take_and_review_an_exam(self, complete):
        complete.return_value = json.dumps({
            "title": "Control de biología", "instructions": "Elige la respuesta correcta.",
            "questions": [
                {"prompt": f"Pregunta {i}", "options": ["A", "B", "C", "D"],
                 "correct_answer": 0, "explanation": "La alternativa A responde correctamente."}
                for i in range(1, 4)
            ],
        })
        self.client.force_login(self.user)

        response = self.client.post(reverse("start_exam", args=[self.session.pk]), {
            "exam_type": ExamAttempt.Type.MULTIPLE_CHOICE,
            "level": ExamAttempt.Level.NORMAL,
            "question_count": 3,
        })
        self.assertEqual(response.status_code, 302)
        attempt = ExamAttempt.objects.get(session=self.session)
        response = self.client.get(reverse("exam_attempt_detail", args=[attempt.pk]))
        self.assertContains(response, "Pregunta 1")
        self.assertNotContains(response, "La alternativa A responde correctamente.")

        response = self.client.post(reverse("exam_attempt_detail", args=[attempt.pk]), {
            "q1": "0", "q2": "1", "q3": "0",
        })
        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.completed_at)
        self.assertEqual(attempt.score, "67%")
        response = self.client.get(reverse("exam_attempt_detail", args=[attempt.pk]))
        self.assertContains(response, "La alternativa A responde correctamente.")

    @patch("academico.application.services.deepseek.complete")
    @patch("academico.application.services._extract_study_file", return_value="Contenido de la lectura en PDF.")
    def test_reading_pdf_is_used_for_summary_and_concept_map(self, extract, complete):
        reading = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.READING,
            title="Lectura complementaria", performed_on="2026-03-03",
        )
        StudyFile.objects.create(
            session=reading,
            category=StudyFile.Category.MATERIAL,
            file=SimpleUploadedFile("lectura.pdf", b"contenido PDF de prueba"),
        )
        complete.return_value = json.dumps({
            "summary_markdown": "## Resumen de la lectura",
            "concept_map": {"title": "Lectura", "nodes": [
                {"id": "1", "label": "Concepto", "parent_id": None},
            ]},
        })

        artifact = services.generate_session_summary(reading)

        self.assertEqual(extract.call_count, 1)
        self.assertIn("Contenido de la lectura en PDF.", complete.call_args.args[0])
        self.assertIn("mapas conceptuales", complete.call_args.kwargs["system_prompt"])
        self.assertIn("link_label", complete.call_args.kwargs["system_prompt"])
        self.assertIn("resumen acad\u00e9mico", complete.call_args.kwargs["system_prompt"].lower())
        self.assertEqual(artifact.kind, "concept_map")

    @patch("academico.application.services.deepseek.complete")
    def test_concept_map_generation_rejects_relationship_without_link_phrase(self, complete):
        complete.return_value = json.dumps({
            "summary_markdown": "## Resumen",
            "concept_map": {"title": "Biología", "nodes": [
                {"id": "root", "label": "Células", "parent_id": None, "link_label": None},
                {"id": "child", "label": "Tejidos", "parent_id": "root"},
            ]},
        })

        with self.assertRaises(ValidationError):
            services.generate_session_summary(self.session)

        self.assertFalse(self.session.artifacts.exists())

    @patch("academico.application.services.deepseek.complete")
    def test_multiple_choice_exam_is_scored_and_saved_to_logbook(self, complete):
        complete.return_value = json.dumps({
            "title": "Control de biología",
            "instructions": "Selecciona una alternativa.",
            "questions": [
                {"prompt": f"Pregunta {i}", "options": ["A", "B", "C", "D"],
                 "correct_answer": answer, "explanation": "Explicación breve."}
                for i, answer in enumerate([0, 1, 2], 1)
            ],
        })

        attempt = services.generate_exam(self.session, ExamAttempt.Type.MULTIPLE_CHOICE,
                                         ExamAttempt.Level.ADVANCED, question_count=3)
        self.assertIn("Nivel avanzado", complete.call_args.args[0])
        self.assertIn("alternativas", complete.call_args.args[0].lower())
        self.assertIn("creaci\u00f3n de ex\u00e1menes", complete.call_args.kwargs["system_prompt"].lower())

        completed = services.finish_exam_attempt(attempt, {"q1": "0", "q2": "0", "q3": "2"})

        self.assertEqual(completed.score, "67%")
        self.assertIsNotNone(completed.completed_at)
        self.assertGreaterEqual(completed.duration_seconds, 0)
        self.assertTrue(completed.payload["questions"][0]["is_correct"])
        self.assertEqual(completed.payload["questions"][1]["student_answer"], 0)

    @patch("academico.application.services.deepseek.complete")
    def test_open_exam_is_graded_with_feedback_and_suggested_answer(self, complete):
        complete.side_effect = [
            json.dumps({
                "title": "Desarrollo",
                "instructions": "Responde con tus palabras.",
                "questions": [
                    {"prompt": "Explica la función de la célula.",
                     "reference_answer": "Es la unidad básica estructural y funcional.",
                     "rubric": ["Unidad estructural", "Unidad funcional"]},
                ],
            }),
            json.dumps({"results": [{
                "id": "q1", "score_percent": 50, "feedback": "Falta explicar su función.",
                "suggested_answer": "Es la unidad estructural y funcional de los seres vivos.",
            }]}),
        ]

        attempt = services.generate_exam(self.session, ExamAttempt.Type.OPEN_RESPONSE,
                                         ExamAttempt.Level.NORMAL, question_count=1)
        completed = services.finish_exam_attempt(attempt, {"q1": "Es una unidad de los seres vivos."})

        question = completed.payload["questions"][0]
        self.assertEqual(completed.score, "50%")
        self.assertEqual(question["score_percent"], 50)
        self.assertIn("Falta explicar", question["feedback"])
        self.assertIn("unidad estructural", question["suggested_answer"])
        self.assertEqual(complete.call_count, 2)
        self.assertIn(
            "evaluaci\u00f3n de respuestas abiertas",
            complete.call_args_list[1].kwargs["system_prompt"].lower(),
        )

    @patch("academico.application.services.deepseek.complete", return_value="no es JSON")
    def test_invalid_ai_exam_is_not_saved(self, _complete):
        with self.assertRaises(ValidationError):
            services.generate_exam(self.session, ExamAttempt.Type.MULTIPLE_CHOICE,
                                   ExamAttempt.Level.NORMAL, question_count=3)
        self.assertEqual(ExamAttempt.objects.count(), 0)

    @patch("academico.application.services._extract_study_file")
    @patch("academico.application.services.deepseek.complete")
    def test_essay_path_questions_and_review_use_selected_type_and_pdf_sources(self, complete, extract):
        essay = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.ESSAY, title="Ensayo de biodiversidad",
            essay_type=StudySession.EssayType.ARGUMENTATIVE, performed_on="2026-03-04",
        )
        StudyFile.objects.create(
            session=essay, category=StudyFile.Category.MATERIAL,
            file=SimpleUploadedFile("fuente.pdf", b"PDF de referencia"),
        )
        StudyFile.objects.create(
            session=essay, category=StudyFile.Category.DRAFT,
            file=SimpleUploadedFile("borrador.docx", b"Documento Word"),
        )
        extract.side_effect = lambda item: (
            "Fuente PDF sobre biodiversidad." if item.category == StudyFile.Category.MATERIAL
            else "Borrador: la biodiversidad debe protegerse."
        )
        complete.side_effect = [
            "## Pasos para el ensayo",
            "La fuente.pdf aporta evidencia sobre biodiversidad.",
            "## Revisión\nLa tesis es clara.",
        ]
        self.client.force_login(self.user)
        detail_url = reverse("session_detail", args=[essay.pk])
        page = self.client.get(detail_url)
        self.assertContains(page, "Recomendar el camino para este ensayo")
        self.assertContains(page, "Consultar al profesor de ensayo")
        self.assertContains(page, "Revisar ensayo con IA")
        self.assertContains(page, "fuente.pdf")

        response = self.client.post(reverse("recommend_essay_path", args=[essay.pk]))
        self.assertRedirects(response, detail_url)
        response = self.client.post(reverse("ask_essay_question", args=[essay.pk]), {
            "prompt": "¿Qué evidencia apoya mi tesis?",
        })
        self.assertRedirects(response, detail_url)
        response = self.client.post(reverse("review_essay_draft", args=[essay.pk]))
        self.assertRedirects(response, detail_url)

        essay.refresh_from_db()
        self.assertEqual(essay.artifacts.filter(kind="essay_path").count(), 1)
        self.assertEqual(essay.artifacts.filter(kind="essay_answer").count(), 1)
        self.assertEqual(essay.artifacts.filter(kind="essay_review").count(), 1)
        question_prompt = complete.call_args_list[1].args[0]
        review_prompt = complete.call_args_list[2].args[0]
        essay_skill = complete.call_args_list[0].kwargs["system_prompt"]
        self.assertIn("Argumentativo", question_prompt)
        self.assertIn("Fuente PDF sobre biodiversidad", question_prompt)
        self.assertNotIn("La célula", question_prompt)
        self.assertIn("Argumentativo", review_prompt)
        self.assertIn("Borrador: la biodiversidad", review_prompt)
        self.assertIn("Fuente PDF sobre biodiversidad", review_prompt)
        self.assertIn("Tipos de ensayo", essay_skill)
        self.assertIn("Revisión bibliográfica", essay_skill)
        self.assertEqual(complete.call_args_list[1].kwargs["system_prompt"], essay_skill)
        self.assertEqual(complete.call_args_list[2].kwargs["system_prompt"], essay_skill)

        page = self.client.get(detail_url)
        self.assertContains(page, "Pasos para el ensayo")
        self.assertContains(page, "¿Qué evidencia apoya mi tesis?")
        self.assertContains(page, "La tesis es clara.")

    def test_essay_reference_must_be_pdf_and_word_draft_replaces_previous(self):
        essay = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.ESSAY, title="Ensayo de prueba",
            essay_type=StudySession.EssayType.EXPOSITIVE, performed_on="2026-03-04",
        )
        invalid_reference = UploadForm(
            {"category": StudyFile.Category.MATERIAL},
            {"file": SimpleUploadedFile("fuente.txt", b"texto")}, session=essay,
        )
        self.assertFalse(invalid_reference.is_valid())
        self.assertIn("file", invalid_reference.errors)

        self.client.force_login(self.user)
        upload_url = reverse("upload_file", args=[essay.pk])
        self.client.post(upload_url, {
            "category": StudyFile.Category.MATERIAL,
            "file": SimpleUploadedFile("fuente.pdf", b"PDF"),
        })
        self.client.post(upload_url, {
            "category": StudyFile.Category.DRAFT,
            "file": SimpleUploadedFile("borrador-1.docx", b"Word v1"),
        })
        first_draft = essay.files.get(category=StudyFile.Category.DRAFT)
        first_storage_path = Path(self.temp_media.name) / first_draft.file.name
        self.client.post(upload_url, {
            "category": StudyFile.Category.DRAFT,
            "file": SimpleUploadedFile("borrador-2.docx", b"Word v2"),
        })

        drafts = essay.files.filter(category=StudyFile.Category.DRAFT)
        self.assertEqual(drafts.count(), 1)
        self.assertEqual(Path(drafts.first().file.name).name, "borrador-2.docx")
        self.assertFalse(first_storage_path.exists())

    @patch("academico.application.services._extract_study_file", return_value="La consigna compara dos enfoques.")
    @patch("academico.application.services.deepseek.complete", return_value="## Recomendación\nEnsayo comparativo")
    def test_student_can_request_guidance_to_choose_essay_type(self, complete, _extract):
        essay = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.ESSAY, title="Ensayo sin tipo definido",
            essay_type=StudySession.EssayType.UNSURE, performed_on="2026-03-04",
            description="Comparar dos enfoques del curso.",
        )
        StudyFile.objects.create(
            session=essay, category=StudyFile.Category.MATERIAL,
            file=SimpleUploadedFile("consigna.pdf", b"PDF con consigna"),
        )
        self.client.force_login(self.user)
        detail_url = reverse("session_detail", args=[essay.pk])
        page = self.client.get(detail_url)
        self.assertContains(page, "Ayúdame a elegir el tipo de ensayo")
        self.assertContains(page, "Recomendar el camino para este ensayo", count=0)

        response = self.client.post(reverse("recommend_essay_type", args=[essay.pk]))
        self.assertRedirects(response, detail_url)
        essay.refresh_from_db()
        self.assertEqual(essay.essay_type, StudySession.EssayType.UNSURE)
        self.assertEqual(essay.artifacts.filter(kind="essay_type_guidance").count(), 1)
        self.assertIn("La consigna compara dos enfoques", complete.call_args.args[0])
        self.assertIn("recomendar un tipo", complete.call_args.kwargs["system_prompt"])
        page = self.client.get(detail_url)
        self.assertContains(page, "Ensayo comparativo")


class SessionScopeAndUploadTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="scope@example.com", email="scope@example.com", password="password-segura"
        )
        self.cycle = Cycle.objects.create(owner=self.user, number="2026-II", start_date="2026-08-01")
        self.course = Course.objects.create(cycle=self.cycle, code="HIS", name="Historia")
        self.outside_course = Course.objects.create(cycle=self.cycle, code="ART", name="Arte")
        self.class_session = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.CLASS, number=1,
            title="Clase 1", performed_on="2026-08-02",
        )
        self.reading_session = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.READING,
            title="Lectura 1", performed_on="2026-08-03",
        )
        self.practice = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.PRACTICE, number=1,
            title="Práctica 1", performed_on="2026-08-04",
        )
        self.practice.scope_sessions.set([self.class_session])

    def test_practice_upload_only_accepts_a_practice_model(self):
        choices = dict(UploadForm(session=self.practice).fields["category"].choices)
        self.assertEqual(list(choices), [StudyFile.Category.MODEL])
        self.assertIn("Modelo de práctica", choices[StudyFile.Category.MODEL])

        transcript = UploadForm({"category": StudyFile.Category.TRANSCRIPT},
                                {"file": SimpleUploadedFile("clase.txt", b"contenido")},
                                session=self.practice)
        self.assertFalse(transcript.is_valid())
        self.assertIn("category", transcript.errors)

    def test_exam_upload_is_labeled_as_exam_model_and_class_keeps_transcripts(self):
        exam = StudySession.objects.create(
            course=self.course, kind=StudySession.Type.EXAM, number=1,
            title="Examen 1", performed_on="2026-08-05",
        )
        exam_choices = dict(UploadForm(session=exam).fields["category"].choices)
        class_choices = dict(UploadForm(session=self.class_session).fields["category"].choices)
        self.assertIn("Examen modelo", exam_choices[StudyFile.Category.MODEL])
        self.assertIn(StudyFile.Category.TRANSCRIPT, class_choices)

    def test_reading_upload_requires_a_pdf(self):
        pdf_form = UploadForm(
            {"category": StudyFile.Category.MATERIAL},
            {"file": SimpleUploadedFile("lectura.pdf", b"PDF de prueba")},
            session=self.reading_session,
        )
        text_form = UploadForm(
            {"category": StudyFile.Category.MATERIAL},
            {"file": SimpleUploadedFile("lectura.txt", b"texto")},
            session=self.reading_session,
        )
        self.assertEqual(pdf_form.fields["file"].widget.attrs["accept"], ".pdf,application/pdf")
        self.assertTrue(pdf_form.is_valid(), pdf_form.errors)
        self.assertFalse(text_form.is_valid())
        self.assertIn("file", text_form.errors)

        self.client.force_login(self.user)
        page = self.client.get(reverse("session_detail", args=[self.reading_session.pk]))
        self.assertContains(page, 'accept=".pdf,application/pdf"')
        self.assertContains(page, "La sesión de lectura recibe archivos PDF")
        response = self.client.post(
            reverse("upload_file", args=[self.reading_session.pk]),
            {"category": StudyFile.Category.MATERIAL,
             "file": SimpleUploadedFile("lectura.txt", b"texto")},
            follow=True,
        )
        self.assertContains(response, "Las sesiones de lectura deben cargarse en formato PDF")

    def test_practice_scope_requires_class_or_reading_from_same_course(self):
        data = {
            "kind": StudySession.Type.PRACTICE,
            "number": "2",
            "title": "Práctica 2",
            "performed_on": "2026-08-06",
            "description": "",
        }
        missing_scope = SessionForm(data, course=self.course)
        self.assertFalse(missing_scope.is_valid())
        self.assertIn("scope", missing_scope.errors)

        selected = SessionForm({**data, "scope": [self.reading_session.pk]}, course=self.course)
        self.assertTrue(selected.is_valid(), selected.errors)

        outside_class = StudySession.objects.create(
            course=self.outside_course, kind=StudySession.Type.CLASS,
            title="Clase ajena", performed_on="2026-08-02",
        )
        cross_course = SessionForm({**data, "scope": [outside_class.pk]}, course=self.course)
        self.assertFalse(cross_course.is_valid())

    def test_scope_can_be_changed_from_session_details(self):
        self.client.force_login(self.user)
        create_page = self.client.get(reverse("session_create", args=[self.course.pk]))
        self.assertEqual(create_page.status_code, 200)
        self.assertContains(create_page, "data-scope-panel")
        self.assertContains(create_page, "Clase · Clase 1 · N.º 1")
        self.assertContains(create_page, "Lectura · Lectura 1 · N.º sin asignar")

        detail = self.client.get(reverse("session_detail", args=[self.practice.pk]))
        self.assertContains(detail, "Editar Sesión")
        self.assertNotContains(detail, "Cambiar alcance")
        self.assertContains(detail, "Modelo de práctica del profesor")
        self.assertNotContains(detail, '<option value="transcript">')

        edit_page = self.client.get(reverse("session_edit", args=[self.practice.pk]))
        self.assertContains(edit_page, "Clase · Clase 1 · N.º 1")
        self.assertContains(edit_page, "Lectura · Lectura 1 · N.º sin asignar")
        self.assertRegex(edit_page.content.decode(),
                         r'name="scope" value="%s"[^>]*checked' % self.class_session.pk)
        self.assertContains(edit_page, 'value="2026-08-04"')
        self.assertContains(edit_page, "Tipo de sesión")

        response = self.client.post(reverse("session_edit", args=[self.practice.pk]), {
            "kind": StudySession.Type.PRACTICE,
            "number": "1",
            "title": "Práctica 1",
            "performed_on": "2026-08-04",
            "description": "",
            "scope": [self.reading_session.pk],
        })
        self.assertRedirects(response, reverse("session_detail", args=[self.practice.pk]))
        self.assertQuerySetEqual(
            self.practice.scope_sessions.order_by("pk"),
            [self.reading_session],
        )

    def test_essay_creation_requires_and_persists_essay_type(self):
        self.client.force_login(self.user)
        create_url = reverse("session_create", args=[self.course.pk])
        page = self.client.get(create_url)
        self.assertContains(page, 'data-essay-type-panel')
        self.assertContains(page, 'data-essay-type-detail-panel')
        self.assertContains(page, "Tipo de ensayo")
        self.assertContains(page, "Argumentativo")

        data = {
            "kind": StudySession.Type.ESSAY,
            "number": "",
            "title": "Ensayo sobre biodiversidad",
            "performed_on": "2026-08-10",
            "description": "",
        }
        response = self.client.post(create_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Selecciona el tipo de ensayo antes de guardar la sesión.")
        self.assertFalse(StudySession.objects.filter(title=data["title"]).exists())

        response = self.client.post(create_url, {
            **data,
            "essay_type": StudySession.EssayType.ARGUMENTATIVE,
        })
        essay = StudySession.objects.get(title=data["title"])
        self.assertRedirects(response, reverse("session_detail", args=[essay.pk]))
        self.assertEqual(essay.essay_type, StudySession.EssayType.ARGUMENTATIVE)
        detail = self.client.get(reverse("session_detail", args=[essay.pk]))
        self.assertContains(detail, "Tipo de ensayo: Argumentativo")
        self.assertContains(detail, 'name="prompt"')
        self.assertContains(detail, "Consultar sobre el ensayo")
        self.assertContains(detail, "Carga al menos un PDF de referencia para habilitar la consulta.")
        self.assertContains(detail, "Revisar ensayo con IA")

        edit = self.client.get(reverse("session_edit", args=[essay.pk]))
        self.assertContains(edit, 'name="essay_type"')
        self.assertContains(edit, 'value="argumentative" selected')

        other_data = {
            **data,
            "title": "Ensayo dialéctico",
            "essay_type": StudySession.EssayType.OTHER,
        }
        missing_custom_type = SessionForm(other_data, course=self.course)
        self.assertFalse(missing_custom_type.is_valid())
        self.assertIn("essay_type_other", missing_custom_type.errors)

        other_form = SessionForm({**other_data, "essay_type_other": "Dialéctico"}, course=self.course)
        self.assertTrue(other_form.is_valid(), other_form.errors)
        other_essay = other_form.save(commit=False)
        other_essay.course = self.course
        other_essay.save()
        self.assertEqual(other_essay.essay_type_display, "Dialéctico")

    def test_concept_map_has_its_own_horizontal_scroll_region(self):
        AIArtifact.objects.create(
            session=self.reading_session,
            kind="concept_map",
            content=json.dumps({"title": "Mapa", "nodes": [
                {"id": "root", "label": "Raíz", "parent_id": None},
                {"id": "child", "label": "Rama", "parent_id": "root", "link_label": "se compone de"},
            ]}),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("session_detail", args=[self.reading_session.pk]))

        self.assertContains(response, 'class="map-scroll"')
        self.assertContains(response, 'aria-label="Mapa conceptual desplazable"')
        self.assertContains(response, "Desplázate horizontalmente dentro del mapa")
        self.assertContains(response, "se compone de")
