<?php
$file = 'products.json';

if (!file_exists($file)) {
    file_put_contents($file, json_encode([]));
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $newProduct = [
        'id' => uniqid(),
        'title' => htmlspecialchars($_POST['title']),
        'price' => (float)$_POST['price'],
        'scraped_price' => (float)$_POST['scraped_price'],
        'regular_market_price' => (float)$_POST['regular_market_price'],
        'category' => htmlspecialchars($_POST['category']),
        'condition' => htmlspecialchars($_POST['condition']),
        'description' => htmlspecialchars($_POST['description']),
        'review_summary' => htmlspecialchars($_POST['review_summary']),
        'image_url' => '',
        'source_url' => 'Manual Entry',
        'scraped_at' => date('Y-m-d H:i:s')
    ];
    
    $currentData = json_decode(file_get_contents($file), true) ?: [];
    $currentData[] = $newProduct;
    file_put_contents($file, json_encode($currentData, JSON_PRETTY_PRINT));
}

$products = json_decode(file_get_contents($file), true) ?: [];
$products = array_reverse($products); 
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Database UI Extension</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f4f9; padding: 20px; }
        .container { display: flex; gap: 20px; max-width: 1200px; margin: auto; }
        .form-section, .list-section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-section { flex: 1; height: fit-content; }
        .list-section { flex: 2; max-height: 80vh; overflow-y: auto; }
        input, select, textarea { width: 100%; margin-bottom: 10px; padding: 8px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box;}
        button { background: #28a745; color: white; border: none; padding: 10px 15px; cursor: pointer; border-radius: 4px; width: 100%;}
        .product-card { border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 15px; background: #fafafa; padding: 15px; border-radius: 6px;}
        .tag { background: #007bff; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px;}
        .price-metrics { display: flex; gap: 15px; font-size: 0.9em; color: #555; margin-bottom: 10px;}
        .sell-price { color: #28a745; font-weight: bold; font-size: 1.2em;}
        .reviews { font-style: italic; color: #666; font-size: 0.9em; border-left: 3px solid #ccc; padding-left: 10px;}
    </style>
</head>
<body>

<div class="container">
    <div class="form-section">
        <h2>Add New Product</h2>
        <form method="POST">
            <input type="text" name="title" placeholder="Product Title" required>
            <div style="display:flex; gap:10px;">
                <input type="number" step="0.01" name="scraped_price" placeholder="Cost ($)" required>
                <input type="number" step="0.01" name="price" placeholder="Your Sale Price ($)" required>
            </div>
            <input type="number" step="0.01" name="regular_market_price" placeholder="Market Value ($)">
            
            <div style="display:flex; gap:10px;">
                <select name="category">
                    <option value="Furniture">Furniture</option>
                    <option value="Consoles">Consoles</option>
                    <option value="Appliances">Appliances</option>
                </select>
                <select name="condition">
                    <option value="New">New</option>
                    <option value="Used">Used</option>
                    <option value="Refurbished">Refurbished</option>
                </select>
            </div>

            <textarea name="description" placeholder="Product Specifications..." rows="3" required></textarea>
            <textarea name="review_summary" placeholder="Review Notes..." rows="2"></textarea>
            <button type="submit">Add to Database</button>
        </form>
    </div>

    <div class="list-section">
        <h2>Local Database Inventory</h2>
        <?php if (empty($products)): ?>
            <p>No products in the database yet.</p>
        <?php else: ?>
            <?php foreach ($products as $item): ?>
                <div class="product-card">
                    <h3 style="margin-top:0;"><?php echo $item['title']; ?> 
                        <span class="tag"><?php echo $item['category']; ?></span>
                        <span class="tag" style="background:#6c757d;"><?php echo $item['condition']; ?></span>
                    </h3>
                    
                    <div class="price-metrics">
                        <span class="sell-price">Sell: $<?php echo number_format($item['price'], 2); ?></span>
                        <span>Cost: $<?php echo number_format($item['scraped_price'] ?? 0, 2); ?></span>
                        <span>Market: $<?php echo number_format($item['regular_market_price'] ?? 0, 2); ?></span>
                    </div>

                    <p><strong>Specs:</strong> <?php echo $item['description']; ?></p>
                    
                    <?php if (!empty($item['review_summary'])): ?>
                        <p class="reviews">"<?php echo $item['review_summary']; ?>"</p>
                    <?php endif; ?>

                    <small>Source: <?php echo $item['source_url']; ?> | Added: <?php echo $item['scraped_at']; ?></small>
                </div>
            <?php endforeach; ?>
        <?php endif; ?>
    </div>
</div>

</body>
</html>