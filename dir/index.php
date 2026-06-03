<?php
session_start(); // <<< IMPORTANT: Start the session for user login status

// =========================================================
// 1. DATABASE CONNECTION DETAILS (FILL IN YOUR CREDENTIALS!)
// =========================================================
$servername = "sql306.infinityfree";         // e.g., 'sql306.infinityfree.com'
$username = "if0_40186534";            // Your database username
$password = "jVk4LoBbCas";            // Your database password (NOT your cPanel password)
$dbname = "if0_40186534_Pyneaple_shop";     

$conn = new mysqli($servername, $username, $password, $dbname);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

// =========================================================
// 2. SQL QUERY LOGIC (Includes Search and Image_URL)
// =========================================================
$sql = "SELECT ID, Name, Price, Description, Image_URL FROM products"; 

if (isset($_GET['search_query']) && !empty($_GET['search_query'])) {
    
    // Sanitize user input to prevent SQL Injection
    $query = $conn->real_escape_string($_GET['search_query']);
    
    // Modify the SQL query to filter results
    $sql .= " WHERE Name LIKE '%{$query}%' OR Description LIKE '%{$query}%'";
}

$result = $conn->query($sql);
?>

<!DOCTYPE html>
<html>
<head>
    <title>Pyneaple</title>
    <link rel="stylesheet" href="styles.css"> 
    <link rel="icon" href="favicon.ico" type="image/x-icon"> 
</head>
<body>
    <div class="container">
        
        <header class="header-top-tier">
            
            <div class="header-logo">
                <a href="index.php">Pyne</a>
            </div>
            
            <form action="index.php" method="GET" class="search-form-header">
                <input type="text" name="search_query" placeholder="Search for products, brands, or deals...">
                <button type="submit">Search</button> 
            </form>

            <div class="header-controls">
                <?php 
                    // Non-functional placeholders for settings/language
                    echo "<a href='#' title='Settings'><i class='icon'>⚙️</i></a>";
                    echo "<a href='#' title='Language'><i class='icon'>🌐</i></a>";
                    
                    if (isset($_SESSION['username'])) {
                        // User is logged in
                        echo "<a href='#' title='Your Account' class='control-account'>Hi, " . htmlspecialchars($_SESSION['username']) . "</a>";
                        echo "<a href='logout.php' title='Log Out'><i class='icon'>➡️</i></a>";
                    } else {
                        // User is not logged in
                        echo "<a href='register.php' title='Create Account'>Register</a>";
                        echo "<a href='login.php' title='Log In'>Log In</a>";
                    }
                ?>
                <a href="#" title="Shopping Cart" class="control-cart"><i class="icon">🛒</i> Cart</a>
            </div>
        </header>

        <nav class="header-nav-tier">
            <a href="#">Daily Deals</a>
            <a href="#">Clothing</a>
            <a href="#">Gaming</a>
            <a href="#">Tools</a>
            <a href="#">Groceries</a>
            <a href="#">Electronics</a>
        </nav>
        
        <section class="header-image-tier">
            <div class="top-banner-placeholder" style="background-color: #6a994e;">
                <h2>Shop the Pyneaple Collection!</h2>
                <p>New arrivals and exclusive member deals inside.</p>
                <button class="banner-cta">Shop Now</button>
            </div>
            
            <div class="category-quick-links">
                <a href="#" class="quick-link-item" style="background-color: #fca311;">🍍 Fruits</a>
                <a href="#" class="quick-link-item" style="background-color: #e5989b;">👕 Apparel</a>
                <a href="#" class="quick-link-item" style="background-color: #0077b6;">🎮 Tech</a>
            </div>
        </section>
        
        <h1 style="visibility: hidden; height: 0; margin: 0;">Product Index</h1>
        
        <?php
        // 3. DISPLAY PRODUCTS
        if ($result && $result->num_rows > 0) {
            
            // OPEN THE GRID CONTAINER
            echo "<div class='product-grid'>";
            
            while($row = $result->fetch_assoc()) {
                
                // OPEN THE PRODUCT CARD (product-item)
                echo "<div class='product-item'>"; 

                    // IMAGE DISPLAY LOGIC
                    if (!empty($row["Image_URL"])) {
                        echo "<img src='" . htmlspecialchars($row["Image_URL"]) . "' alt='" . htmlspecialchars($row["Name"]) . "' class='product-image'>";
                    }
                
                    // WRAP THE TEXT CONTENT IN product-info
                    echo "<div class='product-info'>"; 
                        
                        echo "<h2>" . htmlspecialchars($row["Name"]) . "</h2>";
                        echo "<p>" . htmlspecialchars($row["Description"]) . "</p>";
                        echo "<span class='price'>$" . number_format($row["Price"], 2) . "</span>";
                        
                        // Add to Cart Button 
                        echo "<button class='add-to-cart-btn'>Add to Cart</button>";

                    echo "</div>"; // CLOSE product-info
                echo "</div>"; // CLOSE product-item
            }
            
            echo "</div>"; // CLOSE product-grid
            
        } else {
            // Displayed when no products are found (e.g., when search yields nothing)
            echo "<p>No products found yet. Start adding more!</p>";
        }

        $conn->close(); // Close the database connection
        ?>

    </div>
    <script src="app.js"></script>
</body>
</html>