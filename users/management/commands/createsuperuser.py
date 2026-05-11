"""
Custom createsuperuser command for NewsPulse.

Allows creating a superuser with either email or phone number.
If only phone is provided, a placeholder email is generated.
"""

from django.contrib.auth.management.commands import createsuperuser
from django.core.management import CommandError


class Command(createsuperuser.Command):
    help = "Create a superuser with either email or phone number."

    def handle(self, *args, **options):
        database = options.get("database")
        username = options.get("username")
        email = options.get("email")
        password = options.get("password")
        interactive = options.get("interactive")

        if interactive:
            email, phone = self._prompt_identifier()
        else:
            if not email and not username:
                raise CommandError(
                    "You must provide either --email or --username (phone will be None)."
                )
            if not email:
                phone = None
            else:
                phone = None

        if not password and interactive:
            password = self._get_password()

        User = self.get_user_model()
        superuser = User.objects.super_manager(database).create_superuser(
            email=email,
            phone=phone,
            password=password,
            **{"username": username or (email or "").split("@")[0]},
        )

        self.stdout.write(self.style.SUCCESS("Superuser created successfully."))

    def _prompt_identifier(self):
        """Prompt user for email or phone number."""
        email = None
        phone = None

        email = self.get_input_data(
            self.email_field,
            email,
            lambda v: v.strip() if v else None,
        )

        if not email:
            phone = self.get_input_data(
                self.phone_field,
                phone,
                lambda v: v.strip() if v else None,
            )

        if not email and not phone:
            raise CommandError(
                "You must provide at least an email or a phone number."
            )

        return email, phone

    def get_input_data(self, field_name, current_value, validator):
        """Get input from user for a field, allowing empty input."""
        message = f"{field_name} (leave blank to skip): "
        value = input(message)
        value = validator(value)
        return value

    def _get_password(self):
        """Prompt for password twice."""
        while True:
            password = input("Password: ")
            password2 = input("Password (again): ")
            if password == password2:
                return password
            self.stderr.write("Error: Your passwords didn't match.")
