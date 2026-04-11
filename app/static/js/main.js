/* ── TemporaShop — Main JavaScript ────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
    initHeader();
    initMobileMenu();
    initScrollAnimations();
});

/* ── Sticky header with scroll effect ────────────────────────────────── */
function initHeader() {
    const header = document.getElementById('siteHeader');
    if (!header) return;
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const y = window.scrollY;
        if (y > 50) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
        lastScroll = y;
    }, { passive: true });
}

/* ── Mobile menu toggle ──────────────────────────────────────────────── */
function initMobileMenu() {
    const burger = document.getElementById('burgerBtn');
    const menu = document.getElementById('mobileMenu');
    const overlay = document.getElementById('mobileOverlay');

    if (!burger || !menu || !overlay) return;

    function toggle() {
        burger.classList.toggle('active');
        menu.classList.toggle('active');
        overlay.classList.toggle('active');
        document.body.style.overflow = menu.classList.contains('active') ? 'hidden' : '';
    }

    burger.addEventListener('click', toggle);
    overlay.addEventListener('click', toggle);
}

/* ── Scroll-triggered animations ─────────────────────────────────────── */
function initScrollAnimations() {
    const els = document.querySelectorAll('.animate-on-scroll');
    if (!els.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, i) => {
            if (entry.isIntersecting) {
                // Stagger animation
                setTimeout(() => {
                    entry.target.classList.add('visible');
                }, i * 80);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    els.forEach(el => observer.observe(el));
}
