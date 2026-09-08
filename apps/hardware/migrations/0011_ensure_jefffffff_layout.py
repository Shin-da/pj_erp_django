# Upsert the operator-saved jefffffff layout. Unlike 0006–0009 this does
# not delete fields on other Irys templates.

from django.db import migrations


def ensure_jefffffff(apps, schema_editor):
    from apps.hardware.saved_layouts import ensure_saved_templates

    LabelTemplate = apps.get_model("hardware", "LabelTemplate")
    LabelField = apps.get_model("hardware", "LabelField")
    ensure_saved_templates(LabelTemplate, LabelField)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hardware", "0010_labelprintlog"),
    ]

    operations = [
        migrations.RunPython(ensure_jefffffff, noop),
    ]
