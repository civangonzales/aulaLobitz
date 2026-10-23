from django.core.exceptions import ValidationError


def validate_course_code(code: str) -> str:
    code = (code or "").strip().upper()
    if not code or len(code) > 4:
        raise ValidationError("El código del curso debe tener entre 1 y 4 caracteres.")
    return code


def permitted_session_scope(session, selected_ids):
    """Only allow practice/exam scope to reference class or reading sessions of the same course."""
    allowed = session.course.sessions.filter(kind__in=["class", "reading"], id__in=selected_ids)
    if allowed.count() != len(set(selected_ids)):
        raise ValidationError("El alcance solo puede incluir clases o lecturas del mismo curso.")
    return allowed
