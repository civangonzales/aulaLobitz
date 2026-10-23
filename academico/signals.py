from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from academico.models import StudyFile


@receiver(post_delete, sender=StudyFile)
def delete_stored_file(sender, instance, **kwargs):
    storage, name = instance.file.storage, instance.file.name
    if name:
        transaction.on_commit(lambda: storage.delete(name))
