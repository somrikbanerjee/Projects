from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0003_location_support'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyActual',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.IntegerField()),
                ('month', models.IntegerField()),
                ('total_actual', models.DecimalField(decimal_places=2, max_digits=12)),
                ('source_file', models.CharField(blank=True, default='', max_length=255)),
                ('imported_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-year', '-month'],
                'unique_together': {('year', 'month')},
            },
        ),
        migrations.CreateModel(
            name='ActualSplit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(
                    choices=[
                        ('groceries', 'Groceries'), ('transport', 'Transport'),
                        ('food', 'Food'), ('healthcare', 'Healthcare'),
                        ('home', 'Home'), ('entertainment', 'Entertainment'),
                        ('subscriptions', 'Subscriptions'), ('shopping', 'Shopping'),
                        ('travel', 'Travel'), ('investment', 'Investment'),
                        ('emi', 'Loan EMI'), ('other', 'Other'),
                    ],
                    max_length=50,
                )),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('percentage', models.DecimalField(decimal_places=3, max_digits=6)),
                ('monthly_actual', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='actual_splits',
                    to='budget.monthlyactual',
                )),
            ],
            options={
                'ordering': ['category'],
                'unique_together': {('monthly_actual', 'category')},
            },
        ),
    ]
