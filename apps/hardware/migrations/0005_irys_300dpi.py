# Generated manually for Irys 300 DPI switch

from django.db import migrations, models


def _mm(mm, dpi):
    return int(round(mm * dpi / 25.4))


def forwards_rescale_to_300(apps, schema_editor):
    """Scale existing 203-DPI Irys layouts to 300 DPI so Zebra jewellery RFID
    printers place front/back on separate faces instead of compressing both
    into the top panel."""
    LabelTemplate = apps.get_model("hardware", "LabelTemplate")
    LabelField = apps.get_model("hardware", "LabelField")
    target = 300
    for tpl in LabelTemplate.objects.all():
        old = int(tpl.dpi or 203)
        # Irys canvas still at ~75×26 mm in 203-dot space even if dpi was
        # already edited inconsistently.
        looks_like_203_irys = (
            tpl.media_profile == "irys_standard"
            and tpl.width_dots <= 700
            and tpl.height_dots <= 240
        )
        if old == target and not looks_like_203_irys:
            continue
        if looks_like_203_irys and old == target:
            old = 203
        if old == target:
            continue
        ratio = target / old
        for f in LabelField.objects.filter(template_id=tpl.pk):
            f.x = int(round(f.x * ratio))
            f.y = int(round(f.y * ratio))
            f.font_size = max(8, int(round(f.font_size * ratio)))
            f.box_width = max(10, int(round(f.box_width * ratio)))
            f.save(update_fields=["x", "y", "font_size", "box_width"])
        tpl.dpi = target
        tpl.offset_x = int(round((tpl.offset_x or 0) * ratio))
        tpl.offset_y = int(round((tpl.offset_y or 0) * ratio))
        if tpl.media_profile == "irys_standard":
            tpl.width_dots = _mm(50, target) + _mm(25, target)
            tpl.height_dots = _mm(13, target) * 2
        else:
            tpl.width_dots = max(40, int(round(tpl.width_dots * ratio)))
            tpl.height_dots = max(40, int(round(tpl.height_dots * ratio)))
        tpl.save(
            update_fields=[
                "dpi",
                "width_dots",
                "height_dots",
                "offset_x",
                "offset_y",
            ]
        )


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hardware", "0004_label_print_offsets"),
    ]

    operations = [
        migrations.AlterField(
            model_name="labeltemplate",
            name="dpi",
            field=models.PositiveIntegerField(
                default=300,
                help_text="Must match the Zebra printer DPI (jewellery RFID units are usually 300). Wrong DPI compresses both faces into one panel.",
            ),
        ),
        migrations.AlterField(
            model_name="labeltemplate",
            name="width_dots",
            field=models.PositiveIntegerField(
                default=886,
                help_text="Label width in printer dots — matches the ZPL ^PW command. Irys Standard @ 300 DPI ≈ 886 (75 mm).",
            ),
        ),
        migrations.AlterField(
            model_name="labeltemplate",
            name="height_dots",
            field=models.PositiveIntegerField(
                default=308,
                help_text="Label height in printer dots (designer canvas). Continuous RFID stock does not emit ^LL. Irys @ 300 DPI ≈ 308 (26 mm).",
            ),
        ),
        migrations.RunPython(forwards_rescale_to_300, backwards_noop),
    ]
