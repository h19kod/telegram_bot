from django.db import migrations

GOVERNORATES = [
    ("BGD", "بغداد", "Baghdad"),
    ("BSR", "البصرة", "Basra"),
    ("NIN", "نينوى", "Nineveh"),
    ("ERB", "أربيل", "Erbil"),
    ("SUL", "السليمانية", "Sulaymaniyah"),
    ("DHK", "دهوك", "Duhok"),
    ("KRK", "كركوك", "Kirkuk"),
    ("NJF", "النجف", "Najaf"),
    ("KRB", "كربلاء", "Karbala"),
    ("BBL", "بابل", "Babil"),
    ("ANB", "الأنبار", "Anbar"),
    ("DYL", "ديالى", "Diyala"),
    ("SLD", "صلاح الدين", "Saladin"),
    ("WST", "واسط", "Wasit"),
    ("QAD", "القادسية", "Al-Qadisiyah"),
    ("MTH", "المثنى", "Muthanna"),
    ("DHQ", "ذي قار", "Dhi Qar"),
    ("MYS", "ميسان", "Maysan"),
    ("HLB", "حلبجة", "Halabja"),
]


def seed(apps, schema_editor):
    Governorate = apps.get_model("businesses", "Governorate")
    for i, (code, ar, en) in enumerate(GOVERNORATES):
        Governorate.objects.update_or_create(
            code=code, defaults={"name_ar": ar, "name_en": en, "sort_order": i}
        )


class Migration(migrations.Migration):
    dependencies = [("businesses", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
