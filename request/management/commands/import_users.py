# core/management/commands/import_users.py

import csv
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import User


class Command(BaseCommand):
    help = "Import users from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to the users CSV file (with headers: id,name,email,windowNum,process_mode,verified,password,isAdmin,isOnline)"
        )

    def handle(self, *args, **options):
        path = options["csv_file"]

        try:
            with open(path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)

                required_fields = {'id', 'name', 'email', 'windowNum', 'process_mode', 'verified', 'password', 'isAdmin', 'isOnline'}
                if not required_fields.issubset(reader.fieldnames):
                    self.stdout.write(self.style.ERROR("❌ CSV must contain the correct headers."))
                    return

                for row in reader:
                    user_id = int(row['id'].strip())
                    name = row['name'].strip()
                    email = row['email'].strip()
                    password = make_password(row['password'].strip())
                    window_num = int(row['windowNum'].strip())
                    process_mode = row['process_mode'].strip()
                    verified = row['verified'].strip().lower() == 'true'
                    is_admin = row['isAdmin'].strip().lower() == 'true'
                    is_online = row['isOnline'].strip().lower() == 'true'

                    user, created = User.objects.update_or_create(
                        id=user_id,
                        defaults={
                            'name': name,
                            'email': email,
                            'password': password,
                            'windowNum': window_num,
                            'process_mode': process_mode,
                            'verified': verified,
                            'isAdmin': is_admin,
                            'isOnline': is_online,
                        }
                    )

                    msg = "✅ Created" if created else "🔄 Updated"
                    self.stdout.write(self.style.SUCCESS(f"{msg}: {user.name} (Window {user.windowNum})"))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ File not found: {path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
