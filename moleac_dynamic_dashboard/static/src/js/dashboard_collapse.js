/* BSI Dashboard — collapsible department tree */
(function () {
    'use strict';

    /**
     * Toggle expand/collapse of a department node.
     * @param {string} key   - The node's unique key (data-arrow attribute value)
     * @param {Element} arrow - The clicked arrow span element
     */
    window.bsiTgl = function (key, arrow) {
        var tbl = arrow.closest('table');
        var isOpen = arrow.getAttribute('data-open') === '1';

        if (isOpen) {
            // ── Collapse: hide ALL descendants ────────────────────────
            tbl.querySelectorAll('tr[data-p]').forEach(function (r) {
                var ps = r.getAttribute('data-p').split('|');
                if (ps.indexOf(key) >= 0) {
                    r.style.display = 'none';
                    // Reset any expanded child arrows so expand is clean later
                    var childArrow = r.querySelector('span[data-arrow]');
                    if (childArrow) {
                        childArrow.textContent = '▶';   // ▶
                        childArrow.setAttribute('data-open', '0');
                    }
                }
            });
            arrow.textContent = '▶';   // ▶
            arrow.setAttribute('data-open', '0');

        } else {
            // ── Expand: show only DIRECT children ────────────────────
            tbl.querySelectorAll('tr[data-p]').forEach(function (r) {
                var ps = r.getAttribute('data-p').split('|');
                // Only show rows whose immediate parent (last in list) = key
                if (ps[ps.length - 1] === key) {
                    r.style.display = '';
                }
            });
            arrow.textContent = '▼';   // ▼
            arrow.setAttribute('data-open', '1');
        }
    };
})();
