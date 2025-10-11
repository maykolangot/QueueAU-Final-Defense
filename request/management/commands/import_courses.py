# core/management/commands/import_courses.py

import csv
from django.core.management.base import BaseCommand
from core.models import Department, Course

class Command(BaseCommand):
    help = "Import courses from a CSV file. Each course must reference a valid department_id."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_file",
            type=str,
            help="Path to the courses CSV file (with 'id', 'name', and 'department_id' columns)"
        )

    def handle(self, *args, **options):
        path = options["csv_file"]

        try:
            with open(path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)

                if not all(field in reader.fieldnames for field in ('id', 'name', 'department_id')):
                    self.stdout.write(self.style.ERROR("CSV must contain 'id', 'name', and 'department_id' headers"))
                    return

                for row in reader:
                    course_id = int(row['id'].strip())
                    course_name = row['name'].strip()
                    dept_id = int(row['department_id'].strip())

                    department = Department.objects.filter(id=dept_id).first()
                    if not department:
                        self.stdout.write(self.style.WARNING(
                            f"❌ Department ID {dept_id} not found. Skipping course '{course_name}'."
                        ))
                        continue

                    course, created = Course.objects.get_or_create(
                        id=course_id,
                        defaults={'name': course_name, 'department': department}
                    )

                    if not created:
                        self.stdout.write(self.style.WARNING(
                            f"⚠️ Course ID {course_id} already exists. Skipping."
                        ))
                    else:
                        self.stdout.write(self.style.SUCCESS(
                            f"✅ Created: {course.name} in {department.name}"
                        ))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"❌ File not found: {path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Unexpected error: {e}"))
