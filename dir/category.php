<?php
session_start();
$servername = "sql306.infinityfree";
$username = "if0_40186534";
$password = "jVk4LoBbCas";
$dbname = "if0_40186534_Pyneaple_shop";

$conn = new mysqli($servername, $username, $password, $dbname);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

// Get category from URL
$category = isset($_GET['cat']) ? $conn->real_escape_string($_GET['cat']) : '';

$sql = "SELECT ID, Name, Price, Description, Image_URL FROM products";

if ($category != '') {
    $sql .= " WHERE Category LIKE '%{$category}%'";
}

$result = $conn->query($sql);
?>

<!DOCTYPE html>
<html>
<head>
    <title><?php echo ucfirst($category); ?> - Pyneaple Shop</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <header> <!-- You can copy the same header as index.php --> </header>

        <h1><?php echo ucfirst($category); ?> Products</h1>

        <?php
        if ($result && $result->num_rows > 0) {
            echo "<div class='product-grid'>";
            while($row = $result->fetch_assoc()) {
                echo "<a href='product.php?id=" . $row['ID'] . "' class='product-link'>";
                echo "<div class='product-item'>";
                if (!empty($row["Image_URL"])) {
                    echo "<img src='" . htmlspecialchars($row["Image_URL"]) . "' alt='" . htmlspecialchars($row["Name"]) . "' class='product-image'>";
                }
                echo "<div class='product-info'>";
                echo "<h2>" . htmlspecialchars($row["Name"]) . "</h2>";
                echo "<p>" . htmlspecialchars($row["Description"]) . "</p>";
                echo "<span class='price'>$" . number_format($row["Price"], 2) . "</span>";
                echo "<button class='add-to-cart-btn'>Add to Cart</button>";
                echo "</div></div></a>";
            }
            echo "</div>";
        } else {
            echo "<p>No products found in this category yet.</p>";
        }
        $conn->close();
        ?>
    </div>
    <script src="app.js"></script>
</body>
</html>
