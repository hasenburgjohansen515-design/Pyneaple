/**
 * APP.JS - Pyneaple Shop Interactive Enhancements
 * Adds visual feedback to product cards when hovered or tapped.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Select all product cards using the class defined in styles.css
    const productItems = document.querySelectorAll('.product-item');

    // Exit if no products are on the page
    if (productItems.length === 0) {
        return;
    }

    productItems.forEach(item => {
        // --- 1. Mouse Hover Effects (Desktop) ---
        // 'mouseenter' is triggered when the mouse moves onto the element.
        item.addEventListener('mouseenter', () => {
            // The 'is-hovering' class is defined in styles.css to apply a lifted state (transform: translateY)
            item.classList.add('is-hovering');
        });

        // 'mouseleave' is triggered when the mouse moves off the element.
        item.addEventListener('mouseleave', () => {
            item.classList.remove('is-hovering');
        });

        // --- 2. Touch Effects (Mobile/Tablet) ---
        // 'touchstart' provides a visual cue for users on touch devices.
        item.addEventListener('touchstart', (e) => {
            // Prevent event from interfering with potential scrolling
            e.stopPropagation(); 
            
            // Remove 'is-hovering' from all other items first 
            productItems.forEach(otherItem => {
                if (otherItem !== item) {
                    otherItem.classList.remove('is-hovering');
                }
            });
            
            // Toggle the hover effect on the tapped item. 
            // This makes the card "pop" on the first tap, and then often requires a second tap to close or link to activate.
            item.classList.toggle('is-hovering'); 
        }, { passive: true }); // Use passive listener for better scroll performance
    });
});