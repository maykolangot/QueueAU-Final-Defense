# core/management/commands/import_departments.py

import csv
from django.core.management.base import BaseCommand
from core.models import Department

class Command(BaseCommand):
    help = "Import departments from CSV with explicit IDs"

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the departments CSV file')

    def handle(self, *args, **kwargs):
        path = kwargs['csv_file']

        with open(path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                dept_id = int(row['id'])
                name = row['name'].strip()

                if Department.objects.filter(id=dept_id).exists():
                    self.stdout.write(self.style.WARNING(f"Skipped: Department ID {dept_id} already exists"))
                    continue

                Department.objects.create(id=dept_id, name=name)
                self.stdout.write(self.style.SUCCESS(f"Created: [{dept_id}] {name}"))
