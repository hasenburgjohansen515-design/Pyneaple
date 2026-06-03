<?php
// =========================================================
// 1. DATABASE CONNECTION DETAILS (FILL IN YOUR CREDENTIALS!)
// =========================================================
$servername = "sql306.infinityfree";         // e.g., 'sql306.infinityfree.com'
$username = "if0_40186534";            // Your database username
$password = "jVk4LoBbCas";            // Your database password (NOT your cPanel password)
$dbname = "if0_40186534_Pyneaple_shop";    // Your database name    

$conn = new mysqli($servername, $username, $password, $dbname);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$message = '';

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    // Sanitize user input
    $user = $conn->real_escape_string($_POST['username']);
    $email = $conn->real_escape_string($_POST['email']);
    $pass = $_POST['password'];

    // ⚠️ CRITICAL: HASH THE PASSWORD for secure storage!
    $hashed_password = password_hash($pass, PASSWORD_DEFAULT);

    // Use prepared statements for security
    $sql = "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("sss", $user, $email, $hashed_password);

    if ($stmt->execute()) {
        $message = "Registration successful! You can now log in.";
    } else {
        // Error will occur if username or email already exists
        // Error code 1062 is a duplicate entry error
        if ($conn->errno == 1062) {
             $message = "Error: That username or email is already registered.";
        } else {
             $message = "Error: " . $conn->error;
        }
    }
    $stmt->close();
}
$conn->close();
?>

<!DOCTYPE html>
<html>
<head>
    <title>Register - Pyneaple Shop</title>
    <link rel="stylesheet" href="styles.css"> 
</head>
<body>
    <div class="container">
        <h1>Create Your Account</h1>
        
        <?php if (!empty($message)) echo "<p style='text-align:center; color:#1e4000; font-weight:bold;'>$message</p>"; ?>
        
        <form method="POST" action="register.php" class="search-form" 
              style="flex-direction: column; max-width: 400px; margin: 20px auto; border: 1px solid #ced4da; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.05);">
            
            <input type="text" name="username" placeholder="Username" required 
                   style="margin-bottom: 15px; padding: 10px; border-radius: 5px; width: 100%; border: 1px solid #ced4da;">
            
            <input type="email" name="email" placeholder="Email" required 
                   style="margin-bottom: 15px; padding: 10px; border-radius: 5px; width: 100%; border: 1px solid #ced4da;">
            
            <input type="password" name="password" placeholder="Password" required 
                   style="margin-bottom: 20px; padding: 10px; border-radius: 5px; width: 100%; border: 1px solid #ced4da;">
                   
            <button type="submit" style="background-color: #ffb800; color: #343a40; border: none; padding: 12px; border-radius: 5px; cursor: pointer; font-weight: 600;">Register</button>
        </form>
    </div>
</body>
</html>