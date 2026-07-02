/* BSI Dashboard — collapsible department tree + cell drill-down */
(function () {
    'use strict';

    // ── Open journal items when user clicks a value cell ─────────────
    window.bsiOpenJI = function (cell) {
        var cfg  = parseInt(cell.getAttribute('data-cfg'))  || 0;
        var from = cell.getAttribute('data-from') || '';
        var to   = cell.getAttribute('data-to')   || '';
        var root = parseInt(cell.getAttribute('data-root')) || 0;
        var leaf = parseInt(cell.getAttribute('data-leaf')) || 0;

        if (!cfg || !from || !to) return;

        fetch('/web/dataset/call_kw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: Date.now(),
                method: 'call',
                params: {
                    model:  'bsi.dashboard.config',
                    method: 'action_open_journal_items',
                    args:   [[cfg], from, to, root, leaf],
                    kwargs: {},
                },
            }),
        })
        .then(function (r) { return r.json(); })
        .then(function (resp) {
            if (!resp.result) return;
            var action = resp.result;
            // Odoo v19 OWL action service (WOWL debug)
            try {
                var dbg = odoo.__WOWL_DEBUG__;
                if (dbg && dbg.root && dbg.root.env &&
                    dbg.root.env.services && dbg.root.env.services.action) {
                    dbg.root.env.services.action.doAction(action);
                    return;
                }
            } catch (e) {}
            // Fallback: find any mounted OWL app and use its env
            try {
                var apps = odoo.__apps__ || [];
                for (var i = 0; i < apps.length; i++) {
                    var svc = apps[i].env && apps[i].env.services &&
                              apps[i].env.services.action;
                    if (svc) { svc.doAction(action); return; }
                }
            } catch (e) {}
            // Last resort: navigate via URL action param
            window.location.href = '/odoo/action-' + (action.id || '');
        })
        .catch(function (e) { console.error('BSI drill-down error:', e); });
    };

    // ── Toggle dept collapse ─────────────────────────────────────────

    window.bsiTgl = function (key, arrow, recId) {
        var tbl    = arrow.closest('table');
        var isOpen = arrow.getAttribute('data-open') === '1';

        if (isOpen) {
            // Collapse: hide ALL descendants
            tbl.querySelectorAll('tr[data-p]').forEach(function (r) {
                var ps = r.getAttribute('data-p').split('|');
                if (ps.indexOf(key) >= 0) {
                    r.style.display = 'none';
                    var childArrow = r.querySelector('span[data-arrow]');
                    if (childArrow) {
                        childArrow.textContent = '▶';
                        childArrow.setAttribute('data-open', '0');
                    }
                }
            });
            arrow.textContent = '▶';
            arrow.setAttribute('data-open', '0');

        } else {
            // Expand: show only DIRECT children
            tbl.querySelectorAll('tr[data-p]').forEach(function (r) {
                var ps = r.getAttribute('data-p').split('|');
                if (ps[ps.length - 1] === key) {
                    r.style.display = '';
                }
            });
            arrow.textContent = '▼';
            arrow.setAttribute('data-open', '1');
        }

        // Persist state to server (fire-and-forget)
        if (recId) {
            var collapsing = isOpen;
            fetch('/web/dataset/call_kw', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    id: Date.now(),
                    method: 'call',
                    params: {
                        model: 'bsi.dashboard.config',
                        method: 'toggle_collapsed_path',
                        args: [[recId], key, collapsing],
                        kwargs: {},
                    },
                }),
            }).catch(function () {});
        }
    };

})();
