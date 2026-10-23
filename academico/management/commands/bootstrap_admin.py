import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the initial aulaLobitz superuser from environment variables."

    def add_arguments(self, parser):
        parser.add_argument('--reset-password', action='store_true', help='Replace the existing administrator password explicitly.')

    def handle(self, *args, **options):
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "civangonzales@gmail.com").strip().lower()
        if email != 'civangonzales@gmail.com':
            raise CommandError('La única cuenta administradora es civangonzales@gmail.com.')
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        if not password:
            raise CommandError("Set BOOTSTRAP_ADMIN_PASSWORD before running this command.")
        User = get_user_model()
        user, created = User.objects.get_or_create(username=email, defaults={"email": email, "first_name": "Iván", "last_name": "Gonzales"})
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        if created or options['reset_password']:
            user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(("Created" if created else "Updated") + f" superuser {email}"))
