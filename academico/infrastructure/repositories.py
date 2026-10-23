from academico.models import Cycle, Course, StudySession
from django.shortcuts import get_object_or_404


def cycles_for(user):
    return Cycle.objects.filter(owner=user).prefetch_related("courses__sessions")


def get_course_for_user(user, course_id):
    return get_object_or_404(Course.objects.select_related("cycle"), pk=course_id, cycle__owner=user)


def get_session_for_user(user, session_id):
    return get_object_or_404(StudySession.objects.select_related("course__cycle").prefetch_related("files", "artifacts", "attempts"),
        pk=session_id, course__cycle__owner=user
    )
