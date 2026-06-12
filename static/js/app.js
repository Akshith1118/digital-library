// Library Portal Application Logic

document.addEventListener('DOMContentLoaded', function () {
    // 1. Theme Toggle Management
    const themeToggleBtn = document.getElementById('theme-toggle');
    if (themeToggleBtn) {
        // Load initial theme state
        if (localStorage.getItem('theme') === 'dark' || 
            (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.body.classList.add('dark-mode');
            themeToggleBtn.innerHTML = '<span class="material-symbols-outlined">light_mode</span>';
        } else {
            document.body.classList.remove('dark-mode');
            themeToggleBtn.innerHTML = '<span class="material-symbols-outlined">dark_mode</span>';
        }

        // Toggle action
        themeToggleBtn.addEventListener('click', function () {
            if (document.body.classList.contains('dark-mode')) {
                document.body.classList.remove('dark-mode');
                localStorage.setItem('theme', 'light');
                themeToggleBtn.innerHTML = '<span class="material-symbols-outlined">dark_mode</span>';
            } else {
                document.body.classList.add('dark-mode');
                localStorage.setItem('theme', 'dark');
                themeToggleBtn.innerHTML = '<span class="material-symbols-outlined">light_mode</span>';
            }
        });
    }

    // 2. Sidebar Toggle Management
    const sidebarToggleBtn = document.getElementById('sidebar-toggle');
    const sidebar = document.querySelector('.sidebar');
    if (sidebarToggleBtn && sidebar) {
        sidebarToggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('show');
        });
    }

    // Close sidebar clicking outside on mobile viewports
    document.addEventListener('click', function (event) {
        if (sidebar && sidebar.classList.contains('show') && 
            !sidebar.contains(event.target) && 
            !sidebarToggleBtn.contains(event.target)) {
            sidebar.classList.remove('show');
        }
    });

    // 3. Simple Client-side Table Search filter
    const searchInputs = document.querySelectorAll('.table-search');
    searchInputs.forEach(input => {
        const targetTable = document.querySelector(input.dataset.targetTable);
        if (targetTable) {
            input.addEventListener('keyup', function () {
                const term = this.value.toLowerCase();
                const rows = targetTable.querySelectorAll('tbody tr');
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    if (text.includes(term)) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });
            });
        }
    });
});

// QR Scanner Simulation Action
function simulateQRScan(action, bookId) {
    alert(`Scanning QR Code for book ID: ${bookId}... Simulation successful! Proceeding with ${action}.`);
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = action === 'issue' ? `/admin/issue_qr/${bookId}` : `/admin/return_qr/${bookId}`;
    document.body.appendChild(form);
    form.submit();
}
