from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0005_productimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmaster",
            name="colour",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="size",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="quality",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="stone",
            field=models.CharField(
                blank=True,
                help_text="Legacy tblproduct_master.stone (often empty).",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="gold_weight",
            field=models.CharField(
                blank=True,
                help_text="Metal weight from tbljewellery_metal_details — printed as G-{value}.",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="diamond_weight",
            field=models.CharField(
                blank=True,
                help_text="Diamond carat/weight from tbljewellery_stone_details — printed as D-{value}.",
                max_length=40,
            ),
        ),
    ]
