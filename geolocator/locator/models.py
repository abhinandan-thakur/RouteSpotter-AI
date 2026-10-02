from django.db import models


class Location(models.Model):
    address = models.CharField(max_length=100)
    lattiude = models.FloatField()
    longitude = models.FloatField()

class Edge(models.Model):
    source = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="outgoing_edge")
    destination = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="incoming_edge")
    distance = models.FloatField()


class FuelStop(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    price_per_gallon = models.FloatField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"