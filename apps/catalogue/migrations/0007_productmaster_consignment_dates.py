from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0006_product_tag_attributes"),
    ]

    operations = [
        migrations.AddField(
            model_name="productmaster",
            name="product_type",
            field=models.CharField(
                choices=[("purchased", "Purchased"), ("consignment", "Consignment")],
                db_index=True,
                default="purchased",
                help_text="tblproduct_master.product_type. Consignment lots keep a due_date for return/settle reminders.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="purchase_date",
            field=models.DateField(
                blank=True,
                help_text="tblproduct_master.purchase_date — when the lot was taken in.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="productmaster",
            name="due_date",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="tblproduct_master.due_date — consignment return/settle-by date. Warn only; stock is not returned automatically.",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="productmaster",
            index=models.Index(
                fields=["product_type", "due_date"],
                name="catalogue_pm_consign_due",
            ),
        ),
    ]
