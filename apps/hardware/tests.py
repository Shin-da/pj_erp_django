from django.test import TestCase

from apps.hardware.models import LabelField, LabelTemplate
from apps.hardware.saved_layouts import JEFFFFFFF, JEFFFFFFF_NAME, ensure_saved_templates


class SavedLabelLayoutTests(TestCase):
    def test_ensure_creates_jefffffff_with_colour_and_offsets(self):
        ensure_saved_templates()
        tpl = LabelTemplate.objects.get(name=JEFFFFFFF_NAME)
        self.assertEqual(tpl.category, "ANY")
        self.assertTrue(tpl.is_default)
        self.assertEqual(tpl.offset_x, -35)
        self.assertEqual(tpl.offset_y, 55)
        self.assertEqual(tpl.width_dots, 886)
        self.assertEqual(tpl.height_dots, 308)
        keys = list(tpl.fields.values_list("field_key", flat=True))
        self.assertEqual(keys, [row["field_key"] for row in JEFFFFFFF["fields"]])
        colour = tpl.fields.get(field_key="colour")
        self.assertEqual((colour.x, colour.y, colour.font_size, colour.box_width), (783, 47, 16, 90))

    def test_ensure_restores_fields_without_deleting_other_templates(self):
        other = LabelTemplate.objects.create(
            name="keep-me",
            category="JWL",
            media_profile="irys_standard",
        )
        LabelField.objects.create(template=other, field_key="stone", x=10, y=10, order=0)
        tpl = LabelTemplate.objects.get(name=JEFFFFFFF_NAME)
        tpl.fields.all().delete()
        ensure_saved_templates()
        self.assertEqual(LabelTemplate.objects.filter(name="keep-me").count(), 1)
        self.assertEqual(other.fields.count(), 1)
        self.assertEqual(LabelTemplate.objects.filter(name=JEFFFFFFF_NAME).count(), 1)
        self.assertEqual(LabelTemplate.objects.get(name=JEFFFFFFF_NAME).fields.count(), 9)
