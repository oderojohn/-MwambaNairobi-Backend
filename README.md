# MwambaNairobi-Backend

## POS Backend for a Small Liquor Shop & Bar

This backend is a Django + DRF POS system tailored for a small liquor shop with a bar. It supports product and stock management, sales, payments, customers, shifts, and open bar tabs (chits).

## Quick Start

1. Create a virtual environment and install dependencies.
2. Set environment variables.
3. Run migrations.
4. Seed starter liquor shop data.
5. Start the server.

## Environment Variables

Copy `.env.example` and adjust values as needed.

### Vercel + Neon

For Vercel deployment, set these project environment variables:

```bash
DEBUG=False
SECRET_KEY=your-production-secret-key
DATABASE_URL=postgresql://neondb_owner:npg_XE13DURrgaih@ep-empty-mud-amnh40nu-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
ALLOWED_HOSTS=.vercel.app,localhost,127.0.0.1,0.0.0.0,lecture-routers-ace-regulation.trycloudflare.com
```

After setting `DATABASE_URL`, run migrations against the deployed database.

## Seed Starter Data

Use the small shop catalog seeder:

```bash
python manage.py seed_small_liquor_bar
```

To update existing SKUs with the seed values:

```bash
python manage.py seed_small_liquor_bar --update-existing
```

## Useful Commands

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

If you already have data and want to add larger liquor catalogs, there are additional seed commands under `inventory/management/commands/`.

## Notes

- `chits` can be used for bar tabs by table number or walk-in customers.
- Payments support `cash`, `card`, `mpesa`, `bank_transfer`, and `split`.
