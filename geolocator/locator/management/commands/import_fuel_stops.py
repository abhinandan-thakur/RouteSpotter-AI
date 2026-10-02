from django.core.management.base import BaseCommand, CommandError

from locator.initGraph import import_fuel_stops
from locator.models import FuelStop


class Command(BaseCommand):
    help = "Import the assessment fuel-price CSV and optionally geocode its stops."

    def add_arguments(self, parser):
        parser.add_argument(
            "--geocode",
            action="store_true",
            help="Geocode each distinct US city/state once using Open-Meteo.",
        )
        parser.add_argument("--csv", dest="csv_path", help="Path to a fuel-price CSV file.")

    def handle(self, *args, **options):
        try:
            imported = import_fuel_stops(options["csv_path"], geocode=options["geocode"])
        except (OSError, KeyError, ValueError) as error:
            raise CommandError(f"Could not import fuel stops: {error}") from error

        geocoded = FuelStop.objects.filter(latitude__isnull=False, longitude__isnull=False).count()
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} fuel stops; {geocoded} have coordinates."))
        if options["geocode"] and geocoded < imported:
            self.stdout.write(self.style.WARNING("Some stops were not geocoded and will not be considered for routes."))
