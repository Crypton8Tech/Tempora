"""Import product images from temp_data into the database and generate placeholder."""

import os
import glob
from app.database import init_db, get_db_session
from app.models import Product, ProductImage


# Mapping: SKU -> (folder prefix in uploads, filename pattern)
IMAGE_MAP = {
    "rolex-day-date-001": "Rolex-Day-Date-36-Roman-Numerals-Reference-128238-0113",
    "rolex-gmt-master-2-001": "Rolex-GMT-Master-II-2024-RHE-Crop",
    "rolex-submariner-001": "Rolex-Submariner-126610LV-2023-WWG23-WIT-crop",
}

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "app", "static", "uploads")


def create_placeholder_svg():
    """Create a stylish placeholder SVG for products without images."""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">
  <defs>
    <radialGradient id="bg" cx="50%" cy="40%" r="70%">
      <stop offset="0%" style="stop-color:#1b1010"/>
      <stop offset="100%" style="stop-color:#0a0605"/>
    </radialGradient>
    <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#d4a84b"/>
      <stop offset="100%" style="stop-color:#ffe7c0"/>
    </linearGradient>
  </defs>
  <rect width="600" height="600" fill="url(#bg)"/>
  <rect x="1" y="1" width="598" height="598" fill="none" stroke="#d4a84b" stroke-opacity="0.15" stroke-width="2" rx="4"/>
  <!-- Diamond / luxury icon -->
  <g transform="translate(300,260)" opacity="0.25">
    <polygon points="0,-60 52,-20 32,40 -32,40 -52,-20" fill="none" stroke="url(#gold)" stroke-width="2"/>
    <polygon points="0,-60 52,-20 0,0 -52,-20" fill="none" stroke="url(#gold)" stroke-width="1.5" opacity="0.6"/>
    <line x1="-52" y1="-20" x2="52" y2="-20" stroke="url(#gold)" stroke-width="1" opacity="0.4"/>
    <line x1="0" y1="-60" x2="0" y2="40" stroke="url(#gold)" stroke-width="1" opacity="0.3"/>
    <line x1="-32" y1="40" x2="0" y2="-20" stroke="url(#gold)" stroke-width="1" opacity="0.3"/>
    <line x1="32" y1="40" x2="0" y2="-20" stroke="url(#gold)" stroke-width="1" opacity="0.3"/>
  </g>
  <text x="300" y="360" font-family="Georgia, serif" font-size="16" fill="#d4a84b" fill-opacity="0.35" text-anchor="middle" letter-spacing="6">TEMPORA</text>
  <text x="300" y="385" font-family="sans-serif" font-size="11" fill="#8a7a72" fill-opacity="0.5" text-anchor="middle" letter-spacing="2">ФОТО СКОРО</text>
</svg>'''
    path = os.path.join(UPLOADS_DIR, "placeholder.svg")
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"✅ Created placeholder at {path}")


def import_images():
    """Import images for Rolex watches into the database."""
    init_db()
    db = get_db_session()
    try:
        total_added = 0
        for sku, prefix in IMAGE_MAP.items():
            product = db.query(Product).filter(Product.sku == sku).first()
            if not product:
                print(f"⚠️  Product with SKU '{sku}' not found, skipping")
                continue

            # Check if product already has images
            existing_count = db.query(ProductImage).filter(ProductImage.product_id == product.id).count()
            if existing_count > 0:
                print(f"⏭  {sku}: already has {existing_count} images, skipping")
                continue

            # Find matching files
            pattern = os.path.join(UPLOADS_DIR, f"{prefix}*")
            files = sorted(glob.glob(pattern))

            if not files:
                print(f"⚠️  No files matching '{prefix}*' in uploads/")
                continue

            sort_order = 0
            for filepath in files:
                filename = os.path.basename(filepath)
                url = f"/static/uploads/{filename}"
                db.add(ProductImage(
                    product_id=product.id,
                    url=url,
                    sort_order=sort_order,
                ))
                sort_order += 1

            total_added += sort_order
            print(f"✅ {sku}: added {sort_order} images")

        db.commit()
        print(f"\n🎉 Total images imported: {total_added}")
    finally:
        db.close()


if __name__ == "__main__":
    create_placeholder_svg()
    import_images()
