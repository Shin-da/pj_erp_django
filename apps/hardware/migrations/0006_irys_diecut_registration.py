# Rebuild Irys jewellery templates so deploy/migrate fixes die-cut registration.
# Code-only pushes left production on offset_y=0 with fields crowded into the fold.

from django.db import migrations


def _mm(mm, dpi):
    return int(round(mm * dpi / 25.4))


def apply_irys_jewellery_layout(apps, schema_editor):
    LabelTemplate = apps.get_model("hardware", "LabelTemplate")
    LabelField = apps.get_model("hardware", "LabelField")

    dpi = 300
    # Baseline nudge so print lands on the die-cut (see media.IRYS_REGISTRATION_OFFSET_Y_300).
    offset_y = 55
    tail_w = _mm(50, dpi)
    face_w = _mm(25, dpi)
    face_h = _mm(13, dpi)
    width = tail_w + face_w
    height = face_h * 2
    tail_h = _mm(4, dpi)
    tail_y = (face_h - tail_h) // 2
    front_x, front_y = tail_w, 0
    back_x, back_y = tail_w, face_h

    field_rows = [
        ("subcategory", 70, tail_y + 6, 24, True, "C", max(80, tail_w - 100)),
        ("reference_id", front_x + 8, front_y + 6, 22, True, "L", face_w - 16),
        ("price_rated", front_x + 8, front_y + 38, 26, True, "C", face_w - 16),
        ("horizontal_line", front_x + 8, front_y + 74, 12, False, "L", face_w - 16),
        ("barcode_number", back_x + 8, back_y + 8, 22, True, "L", face_w - 16),
        ("barcode_image", back_x + 8, back_y + 34, 22, False, "L", face_w - 16),
        ("category_code", back_x + 8, back_y + 78, 16, False, "L", 60),
        ("company_name", back_x + 8, back_y + 96, 15, True, "C", face_w - 16),
    ]

    for tpl in LabelTemplate.objects.filter(media_profile="irys_standard"):
        tpl.dpi = dpi
        tpl.width_dots = width
        tpl.height_dots = height
        tpl.offset_x = 0
        tpl.offset_y = offset_y
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
        for order, (key, x, y, font, bold, align, box) in enumerate(field_rows):
            LabelField.objects.create(
                template_id=tpl.pk,
                field_key=key,
                static_text="",
                x=int(x),
                y=int(y),
                font_size=int(font),
                bold=bold,
                align=align,
                box_width=int(box),
                visible=True,
                order=order,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("hardware", "0005_irys_300dpi"),
    ]

    operations = [
        migrations.RunPython(apply_irys_jewellery_layout, noop),
    ]
