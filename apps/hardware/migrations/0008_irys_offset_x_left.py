# Nudge Irys print left (~1.5 mm at 300 DPI) for die-cut registration.

from django.db import migrations


def reapply_irys_sample(apps, schema_editor):
    from apps.hardware.media import irys_jewellery_sample_layout

    LabelTemplate = apps.get_model("hardware", "LabelTemplate")
    LabelField = apps.get_model("hardware", "LabelField")

    layout = irys_jewellery_sample_layout(300)

    for tpl in LabelTemplate.objects.filter(media_profile="irys_standard"):
        tpl.dpi = layout["dpi"]
        tpl.width_dots = layout["width_dots"]
        tpl.height_dots = layout["height_dots"]
        tpl.offset_x = layout["offset_x"]
        tpl.offset_y = layout["offset_y"]
        tpl.save(
            update_fields=[
                "dpi",
                "width_dots",
                "height_dots",
                "offset_x",
                "offset_y",
            ]
        )
        LabelField.objects.filter(template_id=tpl.pk).delete()
        for order, row in enumerate(layout["fields"]):
            LabelField.objects.create(
                template_id=tpl.pk,
                field_key=row["field_key"],
                static_text="",
                x=int(row["x"]),
                y=int(row["y"]),
                font_size=int(row["font_size"]),
                bold=bool(row["bold"]),
                align=row["align"],
                box_width=int(row["box_width"]),
                visible=True,
                order=order,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hardware", "0007_irys_sample_print_accurate"),
    ]

    operations = [
        migrations.RunPython(reapply_irys_sample, noop),
    ]
