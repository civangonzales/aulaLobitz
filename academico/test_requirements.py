import base64
import json
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.core import mail
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academico.application import services
from academico.forms import CycleForm, SessionForm, UploadForm, UserCreateForm
from academico.infrastructure import deepseek
from academico.models import AIArtifact, AIConfiguration, Course, Cycle, ExamAttempt, StudyFile, StudySession


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/a9sAAAAASUVORK5CYII=')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SpecificationRegressionTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)
        User = get_user_model()
        self.user = User.objects.create_user(username='student@example.com', email='student@example.com', password='a-safe-password', first_name='Ana', last_name='Pérez')
        self.other = User.objects.create_user(username='other@example.com', email='other@example.com', password='a-safe-password')
        self.admin = User.objects.create_superuser(username='civangonzales@gmail.com', email='civangonzales@gmail.com', password='admin-safe-password')
        self.cycle = Cycle.objects.create(owner=self.user, number='I', start_date='2026-03-01')
        self.course = Course.objects.create(cycle=self.cycle, code='BIO', name='Biología')
        self.session = StudySession.objects.create(course=self.course, kind='class', number=1, title='Células', performed_on='2026-03-02')
        self.transcript = StudyFile.objects.create(session=self.session, category='transcript', file=SimpleUploadedFile('clase.txt', 'Las células forman tejidos.'.encode()))
        self.client.force_login(self.user)

    def test_private_files_and_owner_scoped_routes_reject_other_students(self):
        response = self.client.get(self.transcript.url)
        self.assertEqual(response.status_code, 200)
        response.close()
        self.client.force_login(self.other)
        for url in [self.transcript.url, '/media/'+self.transcript.file.name,
                    reverse('session_detail', args=[self.session.pk]), reverse('course_edit', args=[self.course.pk])]:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(self.transcript.url).status_code, 302)

    def test_navigation_and_management_pages_render(self):
        for name, args in [('home', []), ('course_detail', [self.course.pk]), ('session_detail', [self.session.pk]),
                           ('session_edit', [self.session.pk]), ('cycle_edit', [self.cycle.pk]), ('course_edit', [self.course.pk])]:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('users')), 'Editar')
        self.assertContains(self.client.get(reverse('ai_settings')), 'Modelo para revisar imágenes')

    def test_map_upload_history_survives_file_deletion(self):
        self.client.post(reverse('upload_file', args=[self.session.pk]), {'category':'map','file':SimpleUploadedFile('mapa-historico.png',PNG)})
        item=self.session.files.get(category='map')
        self.client.post(reverse('delete_file',args=[item.pk]))
        self.assertContains(self.client.get(reverse('session_detail',args=[self.session.pk])), 'mapa-historico.png')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_email_token_changes_password_and_cannot_be_reused(self):
        self.client.logout()
        response = self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        link = re.search(r'https?://[^\s]+', mail.outbox[0].body).group()
        response = self.client.get(link)
        self.assertEqual(response.status_code, 302)
        response = self.client.post(response.url, {'new_password1': 'A-long-new-password-26!', 'new_password2': 'A-long-new-password-26!'})
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('A-long-new-password-26!'))
        self.assertContains(self.client.get(link), 'caducado')

    def test_email_login_is_case_insensitive_and_duplicate_accounts_are_rejected(self):
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': 'STUDENT@EXAMPLE.COM', 'password': 'a-safe-password'})
        self.assertEqual(response.status_code, 302)
        form = UserCreateForm({'email':'STUDENT@EXAMPLE.COM','first_name':'Otra','last_name':'Persona','password':'A-safe-long-password-26!'})
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_user_edit_preserves_password_and_admin_account_cannot_be_deleted(self):
        self.assertEqual(self.client.get(reverse('users')).status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('user_edit', args=[self.user.pk]), {'email':self.user.email,'first_name':'Ana María','last_name':'Pérez','password':''})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ana María')
        self.assertTrue(self.user.check_password('a-safe-password'))
        self.assertEqual(self.client.post(reverse('user_delete', args=[self.admin.pk])).status_code, 403)

    def test_edit_cycle_course_and_confirmed_cascade_deletion(self):
        response = self.client.post(reverse('cycle_edit', args=[self.cycle.pk]), {'number':'II','start_date':'2026-08-01'})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('course_edit', args=[self.course.pk]), {'code':'CIEN','name':'Ciencias'})
        self.assertEqual(response.status_code, 302)
        self.course.refresh_from_db()
        self.assertEqual(self.course.code, 'CIEN')
        duplicate = CycleForm({'number':'II','start_date':'2026-08-01'}, owner=self.user)
        self.assertFalse(duplicate.is_valid())
        url = reverse('course_delete', args=[self.course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(self.transcript.file.storage.exists(self.transcript.file.name))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url)
        self.assertFalse(StudySession.objects.filter(pk=self.session.pk).exists())
        self.assertFalse(self.transcript.file.storage.exists(self.transcript.file.name))

    def test_class_practice_exam_numbers_are_required_and_task_scope_is_optional(self):
        form = SessionForm({'kind':'class','title':'Sin número','performed_on':'2026-10-20'}, course=self.course)
        self.assertFalse(form.is_valid())
        self.assertIn('number', form.errors)
        form = SessionForm({'kind':'task','title':'Trabajo','description':'Analizar células','performed_on':'2026-10-20'}, course=self.course)
        self.assertTrue(form.is_valid(), form.errors)

    @patch('academico.application.services.deepseek.complete')
    def test_transcript_upload_automatically_creates_summary_and_map(self, complete):
        complete.return_value = json.dumps({'summary_markdown':'## Células','concept_map':{'title':'Células','nodes':[{'id':'1','label':'Células','parent_id':None,'link_label':None}]}})
        response = self.client.post(reverse('upload_file', args=[self.session.pk]), {'category':'transcript','file':SimpleUploadedFile('otra.txt',b'Contenido nuevo')})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.session.artifacts.filter(kind='summary_map').exists())
        self.assertTrue(self.session.artifacts.filter(kind='concept_map').exists())
        self.assertEqual(complete.call_count, 1)

    @patch('academico.application.services.deepseek.complete', side_effect=ValidationError('Fallo de conexión'))
    def test_failed_automatic_summary_keeps_uploaded_file_and_offers_retry(self, complete):
        response = self.client.post(reverse('upload_file', args=[self.session.pk]), {'category':'transcript','file':SimpleUploadedFile('conservado.txt',b'Contenido nuevo')}, follow=True)
        self.assertContains(response, 'archivo quedó guardado')
        self.assertTrue(self.session.files.filter(file__endswith='conservado.txt').exists())

    @patch('academico.application.services._extract_study_file', return_value='Las células forman tejidos.')
    @patch('academico.application.services.deepseek.complete', return_value='## Revisión\nFalta una frase de enlace.')
    def test_reading_accepts_map_images_and_preserves_multiple_reviews(self, complete, extract):
        reading = StudySession.objects.create(course=self.course, kind='reading',title='Lectura',performed_on='2026-10-20')
        StudyFile.objects.create(session=reading,category='material',file=SimpleUploadedFile('lectura.pdf',b'%PDF-1.4 contenido'))
        form = UploadForm({'category':'map'},{'file':SimpleUploadedFile('mapa.png',PNG)},session=reading)
        self.assertTrue(form.is_valid(), form.errors)
        item = form.save(commit=False)
        item.session = reading
        item.save()
        for _ in range(2):
            self.client.post(reverse('review_map',args=[item.pk]))
        self.assertEqual(reading.artifacts.filter(kind='map_review').count(),2)
        self.assertTrue(complete.call_args.kwargs['images'][0].startswith('data:image/png;base64,'))
        self.client.post(reverse('delete_file',args=[item.pk]))
        page = self.client.get(reverse('session_detail',args=[reading.pk]))
        self.assertContains(page,'Falta una frase de enlace.',count=2)
        self.assertContains(page,'mapa.png')

    @patch('academico.application.services._extract_study_file')
    @patch('academico.application.services.deepseek.complete', return_value='## Plan\nCompara los conceptos del curso.')
    def test_task_guidance_uses_assignment_attachments_and_selected_sessions(self, complete, extract):
        response = self.client.post(reverse('session_create',args=[self.course.pk]), {'kind':'task','title':'Análisis','description':'Comparar células','performed_on':'2026-10-20','scope':[self.session.pk]})
        self.assertEqual(response.status_code,302)
        task = self.course.sessions.get(kind='task')
        StudyFile.objects.create(session=task,category='assignment',file=SimpleUploadedFile('consigna.pdf',b'%PDF'))
        StudyFile.objects.create(session=task,category='material',file=SimpleUploadedFile('apoyo.txt',b'apoyo'))
        extract.side_effect = lambda item: {'assignment':'Comparar dos tipos de célula.','material':'Material adjunto.','transcript':'Texto de la clase seleccionada.'}[item.category]
        response = self.client.post(reverse('recommend_task',args=[task.pk]),follow=True)
        self.assertContains(response,'Compara los conceptos del curso.')
        prompt = complete.call_args.args[0]
        self.assertIn('Comparar dos tipos de célula.',prompt)
        self.assertIn('Material adjunto.',prompt)
        self.assertIn('Texto de la clase seleccionada.',prompt)
        self.assertIn('tareas universitarias',complete.call_args.kwargs['system_prompt'])
        self.assertContains(response,'Sesiones de apoyo')

    def test_task_requires_assignment_and_rejects_foreign_scope(self):
        task = StudySession.objects.create(course=self.course,kind='task',title='Tarea',description='Analizar',performed_on='2026-10-20')
        with self.assertRaises(ValidationError):
            services.generate_task_guidance(task)
        other_cycle=Cycle.objects.create(owner=self.other,number='I',start_date='2026-03-01')
        other_course=Course.objects.create(cycle=other_cycle,code='BIO',name='Ajeno')
        foreign=StudySession.objects.create(course=other_course,kind='class',title='Ajena',performed_on='2026-10-20')
        form=SessionForm({'kind':'task','title':'Tarea','description':'Analizar','performed_on':'2026-10-20','scope':[foreign.pk]},course=self.course)
        self.assertFalse(form.is_valid())

    def test_sources_budget_includes_later_documents(self):
        sources=[('primer.txt','A'*10000),('ultimo.txt','Un concepto clave al final.')]
        text=services._bounded_sources(sources,1200)
        self.assertIn('Un concepto clave al final.',text)
        self.assertIn('Fragmento recortado',text)

    @patch('academico.application.services.deepseek.complete')
    def test_exam_duration_excludes_time_spent_waiting_for_ai(self, complete):
        submitted=timezone.now()
        attempt=ExamAttempt.objects.create(session=self.session,exam_type='open_response',level='normal',started_at=submitted-timedelta(seconds=60),payload={'questions':[{'id':'q1','prompt':'Explica','reference_answer':'Células','rubric':['Un concepto']}]})
        with patch('academico.application.services.timezone.now',return_value=submitted) as clock:
            def grade(*args,**kwargs):
                clock.return_value=submitted+timedelta(seconds=45)
                return json.dumps({'results':[{'id':'q1','score_percent':80,'feedback':'Bien; falta detalle.','suggested_answer':'Las células forman tejidos.'}]})
            complete.side_effect=grade
            services.finish_exam_attempt(attempt,{'q1':'Mi respuesta'})
        self.assertEqual(attempt.duration_seconds,60)
        self.assertEqual(attempt.completed_at,submitted)

    @patch('academico.application.services.deepseek.complete',return_value='Respuesta inválida')
    def test_grading_failure_keeps_student_text_and_hides_answer_key(self, complete):
        attempt=ExamAttempt.objects.create(session=self.session,exam_type='open_response',level='normal',payload={'questions':[{'id':'q1','prompt':'Explica','reference_answer':'CLAVE_SECRETA','rubric':['Concepto']}]})
        response=self.client.post(reverse('exam_attempt_detail',args=[attempt.pk]),{'q1':'Mi respuesta escrita con cuidado.'})
        self.assertContains(response,'Mi respuesta escrita con cuidado.')
        self.assertNotContains(response,'CLAVE_SECRETA')
        attempt.refresh_from_db()
        self.assertIsNone(attempt.completed_at)

    @patch('academico.application.services.deepseek.complete')
    def test_invalid_scores_and_duplicate_results_are_not_saved(self, complete):
        attempt=ExamAttempt.objects.create(session=self.session,exam_type='open_response',level='normal',payload={'questions':[{'id':'q1','prompt':'Explica','reference_answer':'Células','rubric':['Concepto']}]})
        result={'id':'q1','score_percent':120,'feedback':'Comentario','suggested_answer':'Referencia'}
        for results in [[result],[{**result,'score_percent':50}]*2]:
            complete.return_value=json.dumps({'results':results})
            with self.assertRaises(ValidationError):
                services.finish_exam_attempt(attempt,{'q1':'Mi respuesta'})
            attempt.refresh_from_db()
            self.assertIsNone(attempt.completed_at)

    def test_vision_transport_sends_image_and_uses_vision_model(self):
        key=Fernet.generate_key().decode()
        config=AIConfiguration.objects.create(encrypted_api_key=Fernet(key.encode()).encrypt(b'test-key').decode(),model='text-model',vision_model='deepseek-flash')
        response=MagicMock()
        response.__enter__.return_value=response
        response.read.return_value=json.dumps({'choices':[{'message':{'content':'Revisión'}}]}).encode()
        with override_settings(DEEPSEEK_ENCRYPTION_KEY=key),patch('academico.infrastructure.deepseek.urlopen',return_value=response) as urlopen:
            deepseek.complete('Revisa el mapa',system_prompt='Instrucciones',images=['data:image/png;base64,'+base64.b64encode(PNG).decode()])
        body=json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body['model'],'deepseek-flash')
        self.assertEqual(body['messages'][0]['role'],'system')
        self.assertEqual(body['messages'][1]['content'][1]['type'],'image_url')
