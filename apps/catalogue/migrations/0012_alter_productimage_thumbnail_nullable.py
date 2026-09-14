from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0011_productimage_thumbnail"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productimage",
            name="thumbnail",
            field=models.FileField(
                blank=True,
                null=True,
                help_text="Small JPEG for lists/galleries; full camera file stays on ``image``.",
                upload_to="product_images/thumbs/%Y/%m/",
            ),
        ),
    ]
