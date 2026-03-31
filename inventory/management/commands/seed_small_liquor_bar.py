from decimal import Decimal

from django.core.management.base import BaseCommand

from inventory.models import Category, Product


class Command(BaseCommand):
    help = "Seed a small liquor shop & bar starter catalog (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing products with matching SKU.",
        )

    def handle(self, *args, **options):
        update_existing = options["update_existing"]

        categories = [
            ("Beer & Cider", "Local and imported beers plus ciders"),
            ("Wine", "Red, white, and sparkling wines"),
            ("Spirits", "Whiskey, vodka, gin, rum, brandy, and tequila"),
            ("Ready-to-Drink", "Canned and bottled premixed drinks"),
            ("Mixers & Soda", "Tonic, soda, and cocktail mixers"),
            ("Water & Soft Drinks", "Still and sparkling water plus soft drinks"),
            ("Snacks", "Bar snacks and quick bites"),
        ]

        category_map = {}
        for name, description in categories:
            category, _ = Category.objects.get_or_create(
                name=name, defaults={"description": description}
            )
            category_map[name] = category

        products = [
            {
                "sku": "BEER-001",
                "name": "Lager 500ml",
                "category": "Beer & Cider",
                "cost_price": Decimal("120.00"),
                "selling_price": Decimal("180.00"),
                "stock_quantity": 48,
                "description": "Crisp lager, 500ml bottle",
            },
            {
                "sku": "BEER-002",
                "name": "Cider 330ml",
                "category": "Beer & Cider",
                "cost_price": Decimal("140.00"),
                "selling_price": Decimal("220.00"),
                "stock_quantity": 36,
                "description": "Apple cider, 330ml bottle",
            },
            {
                "sku": "WINE-001",
                "name": "House Red Wine 750ml",
                "category": "Wine",
                "cost_price": Decimal("700.00"),
                "selling_price": Decimal("1100.00"),
                "stock_quantity": 18,
                "description": "Medium-bodied red wine, 750ml",
            },
            {
                "sku": "WINE-002",
                "name": "House White Wine 750ml",
                "category": "Wine",
                "cost_price": Decimal("680.00"),
                "selling_price": Decimal("1050.00"),
                "stock_quantity": 18,
                "description": "Crisp white wine, 750ml",
            },
            {
                "sku": "SPRT-001",
                "name": "Whiskey 750ml",
                "category": "Spirits",
                "cost_price": Decimal("1200.00"),
                "selling_price": Decimal("1800.00"),
                "stock_quantity": 12,
                "description": "Blended whiskey, 750ml",
            },
            {
                "sku": "SPRT-002",
                "name": "Vodka 750ml",
                "category": "Spirits",
                "cost_price": Decimal("1100.00"),
                "selling_price": Decimal("1700.00"),
                "stock_quantity": 12,
                "description": "Premium vodka, 750ml",
            },
            {
                "sku": "SPRT-003",
                "name": "Gin 750ml",
                "category": "Spirits",
                "cost_price": Decimal("1150.00"),
                "selling_price": Decimal("1750.00"),
                "stock_quantity": 12,
                "description": "London dry gin, 750ml",
            },
            {
                "sku": "RTD-001",
                "name": "Rum Cola 330ml Can",
                "category": "Ready-to-Drink",
                "cost_price": Decimal("160.00"),
                "selling_price": Decimal("240.00"),
                "stock_quantity": 24,
                "description": "Premixed rum & cola, 330ml",
            },
            {
                "sku": "RTD-002",
                "name": "Gin Tonic 330ml Can",
                "category": "Ready-to-Drink",
                "cost_price": Decimal("170.00"),
                "selling_price": Decimal("260.00"),
                "stock_quantity": 24,
                "description": "Premixed gin & tonic, 330ml",
            },
            {
                "sku": "MIX-001",
                "name": "Tonic Water 500ml",
                "category": "Mixers & Soda",
                "cost_price": Decimal("80.00"),
                "selling_price": Decimal("130.00"),
                "stock_quantity": 24,
                "description": "Classic tonic water, 500ml",
            },
            {
                "sku": "MIX-002",
                "name": "Soda Water 500ml",
                "category": "Mixers & Soda",
                "cost_price": Decimal("70.00"),
                "selling_price": Decimal("120.00"),
                "stock_quantity": 24,
                "description": "Soda water, 500ml",
            },
            {
                "sku": "SOFT-001",
                "name": "Still Water 500ml",
                "category": "Water & Soft Drinks",
                "cost_price": Decimal("40.00"),
                "selling_price": Decimal("80.00"),
                "stock_quantity": 48,
                "description": "Still water, 500ml",
            },
            {
                "sku": "SOFT-002",
                "name": "Cola 500ml",
                "category": "Water & Soft Drinks",
                "cost_price": Decimal("70.00"),
                "selling_price": Decimal("120.00"),
                "stock_quantity": 36,
                "description": "Cola soft drink, 500ml",
            },
            {
                "sku": "SNK-001",
                "name": "Salted Peanuts 100g",
                "category": "Snacks",
                "cost_price": Decimal("60.00"),
                "selling_price": Decimal("100.00"),
                "stock_quantity": 40,
                "description": "Roasted salted peanuts, 100g",
            },
            {
                "sku": "SNK-002",
                "name": "Potato Chips 60g",
                "category": "Snacks",
                "cost_price": Decimal("50.00"),
                "selling_price": Decimal("90.00"),
                "stock_quantity": 40,
                "description": "Classic potato chips, 60g",
            },
        ]

        created_count = 0
        updated_count = 0
        for product in products:
            category = category_map[product.pop("category")]
            defaults = {**product, "category": category}
            defaults["wholesale_price"] = defaults.get(
                "wholesale_price",
                (defaults["cost_price"] * Decimal("0.90")).quantize(Decimal("0.01")),
            )

            obj, created = Product.objects.get_or_create(
                sku=defaults["sku"], defaults=defaults
            )

            if created:
                created_count += 1
            elif update_existing:
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded liquor shop starter data: {created_count} created, {updated_count} updated."
            )
        )
