/**
 * Market page JavaScript functionality
 * Handles dynamic interactions for the farmer market management page
 */

document.addEventListener('DOMContentLoaded', function () {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize status update forms with AJAX
    initStatusUpdateForms();

    // Initialize search functionality
    initSearch();

    // Initialize product stock update
    initStockUpdate();

    // Initialize animations
    initAnimations();

    // Initialize real-time order notifications
    initOrderNotifications();

    // Initialize order highlighting
    highlightNewOrders();
});

/**
 * Initialize AJAX for order status updates
 */
function initStatusUpdateForms() {
    // Get all status update forms
    const statusForms = document.querySelectorAll('.status-update-form');

    statusForms.forEach((form) => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();

            const orderId = this.dataset.orderId;
            const statusSelect = this.querySelector('select[name="status"]');
            const newStatus = statusSelect.value;
            const submitButton = this.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;

            // Show loading state
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Memperbarui...';

            // Send AJAX request
            fetch(`/petani/market/order/${orderId}/update-ajax`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ status: newStatus }),
            })
                .then((response) => response.json())
                .then((data) => {
                    if (data.success) {
                        // Update status badge
                        const statusBadge = document.querySelector(`#order-status-${orderId}`);
                        if (statusBadge) {
                            statusBadge.innerHTML = data.status_badge;
                        }

                        // Show success message
                        showToast('Status pesanan berhasil diperbarui', 'success');

                        // Update row color based on new status
                        updateRowStatus(orderId, newStatus);
                    } else {
                        // Show error message
                        showToast(data.message || 'Gagal memperbarui status pesanan', 'danger');
                    }
                })
                .catch((error) => {
                    console.error('Error:', error);
                    showToast('Terjadi kesalahan saat memperbarui status pesanan', 'danger');
                })
                .finally(() => {
                    // Reset button state
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalButtonText;
                });
        });
    });
}

/**
 * Update row status class based on new status
 */
function updateRowStatus(orderId, newStatus) {
    const row = document.querySelector(`#order-row-${orderId}`);
    if (!row) return;

    // Remove all status classes
    row.classList.remove('table-warning', 'table-success', 'table-info', 'table-primary', 'table-danger', 'table-secondary');

    // Add appropriate class based on status
    switch (newStatus) {
        case 'pending':
            row.classList.add('table-warning');
            break;
        case 'paid':
            row.classList.add('table-success');
            break;
        case 'processed':
            row.classList.add('table-info');
            break;
        case 'shipped':
            row.classList.add('table-primary');
            break;
        case 'completed':
            row.classList.add('table-success');
            break;
        case 'cancelled':
            row.classList.add('table-danger');
            break;
        case 'expired':
            row.classList.add('table-secondary');
            break;
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Create toast container if it doesn't exist
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }

    // Create toast element
    const toastId = 'toast-' + Date.now();
    const toastHtml = `
        <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header bg-${type} text-white">
                <strong class="me-auto">Notifikasi</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;

    // Add toast to container
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);

    // Initialize and show toast
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    // Remove toast after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function () {
        toastElement.remove();
    });
}

/**
 * Initialize search functionality
 */
function initSearch() {
    // Product search
    const productSearchForm = document.getElementById('product-search-form');
    if (productSearchForm) {
        productSearchForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const searchInput = this.querySelector('input[name="product_search"]');
            const url = new URL(window.location.href);
            url.searchParams.set('product_search', searchInput.value);
            url.searchParams.set('product_page', '1'); // Reset to first page
            window.location.href = url.toString();
        });
    }

    // Order search
    const orderSearchForm = document.getElementById('order-search-form');
    if (orderSearchForm) {
        orderSearchForm.addEventListener('submit', function (e) {
            e.preventDefault();
            const searchInput = this.querySelector('input[name="order_search"]');
            const statusFilter = this.querySelector('select[name="order_status"]');
            const url = new URL(window.location.href);
            url.searchParams.set('order_search', searchInput.value);
            url.searchParams.set('order_status', statusFilter.value);
            url.searchParams.set('order_page', '1'); // Reset to first page
            window.location.href = url.toString();
        });
    }
}

/**
 * Initialize product stock update
 */
function initStockUpdate() {
    const stockUpdateForms = document.querySelectorAll('.stock-update-form');

    stockUpdateForms.forEach((form) => {
        form.addEventListener('submit', function (e) {
            e.preventDefault();

            const productId = this.dataset.productId;
            const stockInput = this.querySelector('input[name="stock"]');
            const newStock = stockInput.value;
            const currentStock = stockInput.getAttribute('data-current-stock') || '0';
            const submitButton = this.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;
            const productName = this.closest('.card').querySelector('.card-title')?.textContent || `Produk #${productId}`;

            // If stock is being reduced significantly, show confirmation dialog
            if (parseInt(newStock) < parseInt(currentStock) * 0.5) {
                showConfirmationDialog(`Anda akan mengurangi stok ${productName} lebih dari 50%. Apakah Anda yakin?`, () => updateProductStock(productId, newStock, submitButton, originalButtonText, productName));
                return;
            }

            // Otherwise, proceed with the update
            updateProductStock(productId, newStock, submitButton, originalButtonText, productName);
        });
    });
}

/**
 * Update product stock via AJAX
 */
function updateProductStock(productId, newStock, submitButton, originalButtonText, productName) {
    // Show loading overlay
    showLoadingOverlay(`Memperbarui stok ${productName}...`);

    // Show loading state on button
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

    // Send AJAX request
    fetch(`/petani/market/product/${productId}/update-stock`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ stock: newStock }),
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error(`Server responded with status: ${response.status}`);
            }
            return response.json();
        })
        .then((data) => {
            if (data.success) {
                // Update stock display
                const stockDisplay = document.querySelector(`#product-stock-${productId}`);
                if (stockDisplay) {
                    stockDisplay.textContent = newStock;
                }

                // Update data-current-stock attribute
                const stockInput = document.querySelector(`form[data-product-id="${productId}"] input[name="stock"]`);
                if (stockInput) {
                    stockInput.setAttribute('data-current-stock', newStock);
                }

                // Show success message
                showToast(`Stok ${productName} berhasil diperbarui menjadi ${newStock}`, 'success');

                // Add highlight effect to the stock display
                if (stockDisplay) {
                    stockDisplay.classList.add('highlight-animation');
                    setTimeout(() => {
                        stockDisplay.classList.remove('highlight-animation');
                    }, 3000);
                }
            } else {
                // Show error message
                showToast(data.message || 'Gagal memperbarui stok produk', 'danger');
            }
        })
        .catch((error) => {
            console.error('Error:', error);
            showToast(`Terjadi kesalahan: ${error.message}`, 'danger');
        })
        .finally(() => {
            // Reset button state
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;

            // Hide loading overlay
            hideLoadingOverlay();
        });
}

/**
 * Initialize animations
 */
function initAnimations() {
    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.5s ease, transform 0.5s ease';

        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 * index);
    });
}

/**
 * Initialize real-time order notifications
 * Polls the server for new orders every 30 seconds
 */
function initOrderNotifications() {
    // Store the last checked timestamp
    let lastChecked = new Date().toISOString();

    // Function to check for new orders
    function checkForNewOrders() {
        fetch(`/petani/market/check-new-orders?since=${encodeURIComponent(lastChecked)}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    // Update last checked timestamp
                    lastChecked = new Date().toISOString();

                    // If there are new orders, show notification and update UI
                    if (data.new_orders_count > 0) {
                        // Show notification
                        showToast(`Anda memiliki ${data.new_orders_count} pesanan baru!`, 'success');

                        // Play notification sound
                        playNotificationSound();

                        // Update the orders count in the UI
                        updateOrdersCount(data.pending_count, data.paid_count);

                        // If we have order data, update the orders table
                        if (data.orders && data.orders.length > 0) {
                            updateOrdersTable(data.orders);
                        } else {
                            // If we don't have order data, reload the page to show new orders
                            setTimeout(() => {
                                window.location.reload();
                            }, 3000);
                        }
                    }
                }
            })
            .catch((error) => {
                console.error('Error checking for new orders:', error);
            });
    }

    // Check for new orders every 30 seconds
    setInterval(checkForNewOrders, 30000);
}

/**
 * Play a notification sound
 */
function playNotificationSound() {
    // Create audio element
    const audio = new Audio('/static/sounds/notification.mp3');
    audio.volume = 0.5;
    audio.play().catch((e) => {
        console.log('Audio playback failed:', e);
    });
}

/**
 * Update the orders count in the UI
 */
function updateOrdersCount(pendingCount, paidCount) {
    // Update the pending orders count
    const pendingBadge = document.querySelector('.badge.bg-warning');
    if (pendingBadge) {
        pendingBadge.textContent = `${pendingCount} menunggu`;
    }

    // Update the paid orders count
    const paidBadge = document.querySelector('.badge.bg-success');
    if (paidBadge) {
        paidBadge.textContent = `${paidCount} dibayar`;
    }

    // Update the total orders count
    const totalOrdersElement = document.querySelector('.card-body h3');
    if (totalOrdersElement) {
        totalOrdersElement.textContent = (pendingCount + paidCount).toString();
    }
}

/**
 * Update the orders table with new orders
 */
function updateOrdersTable(orders) {
    const ordersTable = document.querySelector('.table tbody');
    if (!ordersTable) return;

    // Remove "no orders" message if it exists
    const noOrdersRow = ordersTable.querySelector('tr td[colspan="4"]');
    if (noOrdersRow) {
        noOrdersRow.parentElement.remove();
    }

    // Add new orders to the table
    orders.forEach((order) => {
        // Check if the order already exists in the table
        const existingRow = document.getElementById(`order-row-${order.id}`);
        if (existingRow) return;

        // Create new row for the order
        const newRow = document.createElement('tr');
        newRow.id = `order-row-${order.id}`;
        newRow.classList.add('table-bordered', 'border-success', 'new-order');

        // Set row HTML
        newRow.innerHTML = `
            <td>
                <div class="d-flex align-items-center">
                    <div class="me-3 text-center">
                        <div class="fw-bold">#${order.id}</div>
                        <small class="text-muted">${formatDate(order.created_at)}</small>
                    </div>
                    <div>
                        <div class="fw-bold">${order.buyer_name}</div>
                        <small class="text-muted">${order.items_count} item</small>
                    </div>
                </div>
            </td>
            <td class="fw-bold text-success">Rp ${order.total_amount}</td>
            <td>
                <span id="order-status-${order.id}" class="badge ${getStatusBadgeClass(order.status)}">
                    ${capitalizeFirstLetter(order.status)}
                </span>
            </td>
            <td>
                <div class="d-flex">
                    <button type="button" class="btn btn-sm btn-outline-green border-1 me-2"
                        data-bs-toggle="modal" data-bs-target="#orderModal${order.id}">
                        <i class="bi bi-eye"></i>
                    </button>
                    <form action="/petani/market/order/${order.id}/update" method="post" class="status-update-form d-flex"
                        data-order-id="${order.id}">
                        <select name="status" class="form-select form-select-sm me-1" style="width: 110px;">
                            ${getStatusOptions(order.status)}
                        </select>
                        <button type="submit" class="btn btn-sm btn-success border-1">
                            <i class="bi bi-check"></i>
                        </button>
                    </form>
                </div>
            </td>
        `;

        // Add the new row to the table
        ordersTable.prepend(newRow);

        // Initialize the status update form for the new row
        initStatusUpdateForm(newRow.querySelector('.status-update-form'));

        // Add animation to highlight the new row
        setTimeout(() => {
            newRow.classList.add('highlight-animation');
        }, 100);
    });
}

/**
 * Initialize a single status update form
 */
function initStatusUpdateForm(form) {
    if (!form) return;

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        const orderId = this.dataset.orderId;
        const statusSelect = this.querySelector('select[name="status"]');
        const newStatus = statusSelect.value;
        const submitButton = this.querySelector('button[type="submit"]');
        const originalButtonText = submitButton.innerHTML;

        // Show loading state
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Memperbarui...';

        // Send AJAX request
        fetch(`/petani/market/order/${orderId}/update-ajax`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify({ status: newStatus }),
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.success) {
                    // Update status badge
                    const statusBadge = document.querySelector(`#order-status-${orderId}`);
                    if (statusBadge) {
                        statusBadge.innerHTML = data.status_badge;
                    }

                    // Show success message
                    showToast('Status pesanan berhasil diperbarui', 'success');

                    // Update row color based on new status
                    updateRowStatus(orderId, newStatus);
                } else {
                    // Show error message
                    showToast(data.message || 'Gagal memperbarui status pesanan', 'danger');
                }
            })
            .catch((error) => {
                console.error('Error:', error);
                showToast('Terjadi kesalahan saat memperbarui status pesanan', 'danger');
            })
            .finally(() => {
                // Reset button state
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonText;
            });
    });
}

/**
 * Get status options for select dropdown
 */
function getStatusOptions(currentStatus) {
    const statuses = ['pending', 'paid', 'processed', 'shipped', 'completed', 'cancelled'];
    return statuses.map((status) => `<option value="${status}" ${status === currentStatus ? 'selected' : ''}>${capitalizeFirstLetter(status)}</option>`).join('');
}

/**
 * Get badge class for order status
 */
function getStatusBadgeClass(status) {
    switch (status) {
        case 'pending':
            return 'bg-warning';
        case 'paid':
            return 'bg-success';
        case 'processed':
            return 'bg-info';
        case 'shipped':
            return 'bg-primary';
        case 'completed':
            return 'bg-success';
        case 'cancelled':
            return 'bg-danger';
        case 'expired':
            return 'bg-secondary';
        default:
            return 'bg-secondary';
    }
}

/**
 * Format date for display
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}/${date.getFullYear()}`;
}

/**
 * Capitalize first letter of a string
 */
function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

/**
 * Show loading overlay
 */
function showLoadingOverlay(message = 'Memproses...') {
    const overlay = document.getElementById('loading-overlay');
    const messageElement = document.getElementById('loading-message');

    if (overlay && messageElement) {
        messageElement.textContent = message;
        overlay.classList.remove('d-none');
    }
}

/**
 * Hide loading overlay
 */
function hideLoadingOverlay() {
    const overlay = document.getElementById('loading-overlay');

    if (overlay) {
        overlay.classList.add('d-none');
    }
}

/**
 * Show confirmation dialog
 */
function showConfirmationDialog(message, confirmCallback) {
    const modal = document.getElementById('confirmationModal');
    const messageElement = document.getElementById('confirmationMessage');
    const confirmButton = document.getElementById('confirmButton');

    if (modal && messageElement && confirmButton) {
        // Set message
        messageElement.textContent = message;

        // Set confirm button action
        confirmButton.onclick = function () {
            // Hide modal
            bootstrap.Modal.getInstance(modal).hide();

            // Execute callback
            if (typeof confirmCallback === 'function') {
                confirmCallback();
            }
        };

        // Show modal
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    } else {
        // Fallback to confirm dialog if modal elements not found
        if (confirm(message)) {
            confirmCallback();
        }
    }
}

/**
 * Highlight new orders in the table
 */
function highlightNewOrders() {
    // Get all order rows
    const orderRows = document.querySelectorAll('tr[id^="order-row-"]');

    // Add highlight class to paid orders
    orderRows.forEach((row) => {
        const statusBadge = row.querySelector('.badge');
        if (statusBadge && statusBadge.textContent.trim() === 'Paid') {
            row.classList.add('highlight-animation');
        }
    });
}
