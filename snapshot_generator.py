# snapshot_generator.py
import os
import csv

SAMPLE_DIR = "snapshots"
os.makedirs(SAMPLE_DIR, exist_ok=True)

samples = []

# Generate 10 sample HTML files
for i in range(1, 11):
    title = f"Example Product {i}"
    price = f"₹{999 + i * 50}"
    availability = "In stock" if i % 3 != 0 else "Out of stock"

    html_content = f"""
    <html>
      <head>
        <title>{title} — Buy Now</title>
        <meta property="og:title" content="{title}" />
      </head>
      <body>
        <div class="product">
          <h1 class="product-title">{title}</h1>
          <div id="pricing">
            <span class="price">{price}</span>
            <div class="availability" id="availability">{availability}</div>
          </div>
          <ul class="specs">
            <li>Color: Black</li>
            <li>Weight: {100 + i}g</li>
            <li>SKU: SKU{i:04d}</li>
          </ul>
        </div>
      </body>
    </html>
    """

    filename = f"product_{i}.html"
    file_path = os.path.join(SAMPLE_DIR, filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content.strip())

    samples.append({
        "filename": filename,
        "title_selector": "h1.product-title",
        "price_selector": "span.price",
        "availability_selector": "#availability"
    })

# Write CSV mapping file
csv_path = "sample_mappings.csv"
with open(csv_path, "w", newline='', encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=["filename", "title_selector", "price_selector", "availability_selector"])
    writer.writeheader()
    for row in samples:
        writer.writerow(row)

print("✅ Generated 10 sample product snapshots in 'snapshots/'")
print(f"✅ Created CSV mapping file: {csv_path}")
