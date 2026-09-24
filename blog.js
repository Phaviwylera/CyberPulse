/* ===========================================================
   CyberPulse — progressive enhancement layer.
   The post list is server-rendered, so the site works with
   JavaScript disabled; this file adds search, filtering,
   pagination, theming and reading-progress affordances.
   =========================================================== */
(function () {
    'use strict';

    var PAGE_SIZE = 12;

    /* ---------- Theme -------------------------------------------------- */
    function initTheme() {
        var btn = document.getElementById('theme-toggle');
        if (!btn) return;

        function apply(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            btn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
            try { localStorage.setItem('cp-theme', theme); } catch (e) { /* private mode */ }
        }

        btn.addEventListener('click', function () {
            var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            apply(next);
        });

        // Follow the OS if the user has not made an explicit choice.
        var mq = window.matchMedia('(prefers-color-scheme: dark)');
        var listener = function (ev) {
            var stored = null;
            try { stored = localStorage.getItem('cp-theme'); } catch (e) { /* noop */ }
            if (!stored) apply(ev.matches ? 'dark' : 'light');
        };
        if (mq.addEventListener) mq.addEventListener('change', listener);
        else if (mq.addListener) mq.addListener(listener);
    }

    /* ---------- Mobile navigation -------------------------------------- */
    function initNav() {
        var toggle = document.getElementById('nav-toggle');
        var nav = document.getElementById('site-nav');
        if (!toggle || !nav) return;

        if (window.matchMedia('(min-width: 721px)').matches) nav.hidden = false;

        function sync() {
            var collapsed = window.matchMedia('(max-width: 720px)').matches;
            nav.hidden = collapsed && toggle.getAttribute('aria-expanded') !== 'true';
        }

        toggle.addEventListener('click', function () {
            var open = toggle.getAttribute('aria-expanded') === 'true';
            toggle.setAttribute('aria-expanded', String(!open));
            nav.hidden = open;
        });

        window.addEventListener('resize', function () {
            if (window.matchMedia('(min-width: 721px)').matches) {
                nav.hidden = false;
                toggle.setAttribute('aria-expanded', 'false');
            } else {
                sync();
            }
        });
        sync();

        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
                toggle.setAttribute('aria-expanded', 'false');
                nav.hidden = true;
                toggle.focus();
            }
        });
    }

    /* ---------- Reading progress + back to top ------------------------- */
    function initScrollAffordances() {
        var bar = document.getElementById('progress-bar');
        var top = document.getElementById('back-to-top');
        if (!bar && !top) return;

        var ticking = false;
        function update() {
            ticking = false;
            var y = window.scrollY || document.documentElement.scrollTop;
            if (bar) {
                var doc = document.documentElement;
                var max = (doc.scrollHeight - doc.clientHeight) || 1;
                bar.style.width = Math.min(100, (y / max) * 100) + '%';
            }
            if (top) top.classList.toggle('is-visible', y > 600);
        }

        window.addEventListener('scroll', function () {
            if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
        }, { passive: true });
        update();

        if (top) {
            top.addEventListener('click', function () {
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });
        }
    }

    /* ---------- Copy-link share button --------------------------------- */
    function initCopyLinks() {
        document.querySelectorAll('[data-copy]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var url = btn.getAttribute('data-copy');
                var done = function () {
                    var original = btn.textContent;
                    btn.textContent = 'Copied ✓';
                    setTimeout(function () { btn.textContent = original; }, 1800);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(url).then(done).catch(function () { window.location.href = url; });
                } else {
                    var tmp = document.createElement('input');
                    document.body.appendChild(tmp);
                    tmp.value = url; tmp.select();
                    try { document.execCommand('copy'); done(); } catch (e) { /* noop */ }
                    document.body.removeChild(tmp);
                }
            });
        });
    }

    /* ---------- Search / filter / pagination --------------------------- */
    function initArchive() {
        var container = document.getElementById('post-list-container');
        var search = document.getElementById('search-input');
        if (!container) return;

        var featuredWrap = document.getElementById('featured-container');
        var featuredCard = featuredWrap ? featuredWrap.querySelector('.featured') : null;
        var loadMore = document.getElementById('load-more');
        var emptyState = document.getElementById('empty-state');
        var note = document.getElementById('result-note');
        var chips = Array.prototype.slice.call(document.querySelectorAll('.chip-row .chip'));

        // Cards on the home page and on category pages.
        var cards = Array.prototype.slice.call(container.querySelectorAll('.post-card'));
        var visible = PAGE_SIZE;
        var activeCategory = 'all';
        var term = '';

        // Keep the original copy so we can strip highlighting safely.
        cards.forEach(function (card) {
            var titleEl = card.querySelector('h3 a') || card.querySelector('h3');
            var excerptEl = card.querySelector('.excerpt');
            card._titleHTML = titleEl ? titleEl.innerHTML : '';
            card._excerptHTML = excerptEl ? excerptEl.innerHTML : '';
            card._title = (card.getAttribute('data-title') || '');
            card._summary = (card.getAttribute('data-summary') || '');
            card._tags = (card.getAttribute('data-tags') || '');
            card._category = (card.getAttribute('data-category') || '').toLowerCase();
        });

        function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

        function highlight(card, needle) {
            if (!needle) {
                var t = card.querySelector('h3 a') || card.querySelector('h3');
                var x = card.querySelector('.excerpt');
                if (t) t.innerHTML = card._titleHTML;
                if (x) x.innerHTML = card._excerptHTML;
                return;
            }
            var re = new RegExp('(' + escapeRe(needle) + ')', 'gi');
            [
                [card.querySelector('h3 a') || card.querySelector('h3'), card._titleHTML],
                [card.querySelector('.excerpt'), card._excerptHTML]
            ].forEach(function (pair) {
                var el = pair[0], original = pair[1];
                if (!el) return;
                // Replace inside text nodes only, so nested markup survives.
                el.innerHTML = original.replace(/(<[^>]+>)|([^<]+)/g, function (m, tag, text) {
                    return tag ? tag : text.replace(re, '<mark>$1</mark>');
                });
            });
        }

        function matches(card) {
            if (activeCategory !== 'all' && card._category !== activeCategory.toLowerCase()) return false;
            if (!term) return true;
            return card._title.indexOf(term) !== -1 ||
                   card._summary.indexOf(term) !== -1 ||
                   card._tags.indexOf(term) !== -1 ||
                   card._category.indexOf(term) !== -1;
        }

        function render() {
            var hits = cards.filter(matches);
            var shown = 0;

            cards.forEach(function (card) {
                var isHit = hits.indexOf(card) !== -1;
                var show = isHit && shown < visible;
                if (isHit) shown++;
                card.hidden = !show;
                highlight(card, show ? term : '');
            });

            // The featured card only makes sense on an unfiltered archive view.
            if (featuredCard) {
                var featuredHit = !term && activeCategory === 'all';
                featuredWrap.hidden = !featuredHit;
            }

            if (loadMore) loadMore.hidden = shown <= visible || hits.length <= visible;
            if (emptyState) emptyState.hidden = hits.length !== 0;

            if (note) {
                if (term || activeCategory !== 'all') {
                    var parts = [];
                    parts.push(hits.length + (hits.length === 1 ? ' dispatch' : ' dispatches'));
                    if (term) parts.push('matching “' + term + '”');
                    if (activeCategory !== 'all') parts.push('in ' + activeCategory);
                    note.textContent = parts.join(' ');
                } else {
                    note.textContent = '';
                }
            }
        }

        // --- Wire up the search field ----------------------------------
        if (search) {
            var debounce;
            search.addEventListener('input', function () {
                window.clearTimeout(debounce);
                debounce = window.setTimeout(function () {
                    term = search.value.trim().toLowerCase();
                    visible = PAGE_SIZE;
                    render();
                }, 120);
            });
            search.addEventListener('keydown', function (ev) {
                if (ev.key === 'Escape') { search.value = ''; term = ''; render(); }
            });
        }

        // --- Wire up the section chips ---------------------------------
        // On the home page (which holds every dispatch) chips filter in place.
        // On a section page, a chip pointing at a section we don't hold here
        // must behave as a normal link and navigate.
        var isHome = Boolean(featuredWrap);
        chips.forEach(function (chip) {
            chip.addEventListener('click', function (ev) {
                var filter = chip.getAttribute('data-filter');
                if (!filter) return;
                var wantAll = filter === 'all';
                var holdsSection = cards.some(function (c) {
                    return c._category === filter.toLowerCase();
                });
                if ((wantAll && !isHome) || (!wantAll && !holdsSection)) return; // navigate
                ev.preventDefault();
                activeCategory = wantAll ? 'all' : filter;
                visible = PAGE_SIZE;
                chips.forEach(function (c) {
                    var on = c === chip;
                    c.classList.toggle('is-active', on);
                    c.setAttribute('aria-pressed', String(on));
                });
                render();
                if (history.replaceState && isHome) {
                    history.replaceState(null, '',
                        activeCategory === 'all' ? window.location.pathname : '?section=' + encodeURIComponent(activeCategory));
                }
            });
        });

        // --- Load more --------------------------------------------------
        if (loadMore) {
            loadMore.addEventListener('click', function () {
                visible += PAGE_SIZE;
                render();
            });
        }

        // --- Deep links: ?q= (SearchAction) and ?section= --------------
        var params = new URLSearchParams(window.location.search);
        if (params.get('q') && search) {
            search.value = params.get('q');
            term = params.get('q').trim().toLowerCase();
        }
        if (params.get('section')) activeCategory = params.get('section');

        // Reflect any deep-linked section in the chip row.
        if (activeCategory !== 'all') {
            chips.forEach(function (c) {
                var on = (c.getAttribute('data-filter') || '').toLowerCase() === activeCategory.toLowerCase();
                c.classList.toggle('is-active', on);
                c.setAttribute('aria-pressed', String(on));
            });
        }

        render();
    }

    /* ---------- Boot --------------------------------------------------- */
    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        initTheme();
        initNav();
        initScrollAffordances();
        initCopyLinks();
        initArchive();
    });
})();
