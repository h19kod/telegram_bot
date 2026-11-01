from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []
    run_before = [("products", "0001_initial")]
    operations = [TrigramExtension()]
