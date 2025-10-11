import csv
from django.core.management.base import BaseCommand
from core.models import Student, Course
from django.db import transaction

class Command(BaseCommand):
    help = "Imports students from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file to import")

    def handle(self, *args, **options):
        file_path = options["csv_file"]
        created_count = 0
        updated_count = 0
        errors = []

        try:
            with open(file_path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                with transaction.atomic():
                    for row in reader:
                        try:
                            course = Course.objects.filter(id=row["course_id"]).first()

                            student, created = Student.objects.update_or_create(
                                studentId=row["studentId"],
                                defaults={
                                    "name": row["name"],
                                    "email": row["email"],
                                    "roles": row.get("roles", "student"),
                                    "priority_request": row["priority_request"].strip().lower() == "true",
                                    "priority": row["priority"].strip().lower() == "true",
                                    "course": course,
                                    "campus": row["campus"],
                                    "qrId": row["qrId"],
                                    "year_level": int(row["year_level"]),
                                },
                            )
                            if created:
                                created_count += 1
                            else:
                                updated_count += 1

                        except Exception as e:
                            errors.append(f"Row {row.get('studentId', 'N/A')}: {e}")
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Import completed"))
        self.stdout.write(f" - Created: {created_count}")
        self.stdout.write(f" - Updated: {updated_count}")
        if errors:
            self.stdout.write(self.style.WARNING(f" - Errors: {len(errors)}"))
            for err in errors:
                self.stdout.write(self.style.WARNING(f"   {err}"))
