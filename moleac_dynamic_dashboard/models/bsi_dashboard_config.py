import io
import base64
import calendar
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError

MONTH_SEL = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December'),
]

QUARTER_SEL = [('Q1', 'Q1'), ('Q2', 'Q2'), ('Q3', 'Q3'), ('Q4', 'Q4')]

_Q_DATES = {
    'Q1': (1, 1, 3, 31),
    'Q2': (4, 1, 6, 30),
    'Q3': (7, 1, 9, 30),
    'Q4': (10, 1, 12, 31),
}


class BsiDashboardConfig(models.Model):
    _name = 'bsi.dashboard.config'
    _description = 'BSI Dynamic Dashboard'
    _rec_name = 'name'

    name = fields.Char(required=True, default='Product Development Report')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company, required=True)

    # ── Year period ──────────────────────────────────────────────
    year = fields.Integer('Year', default=lambda s: date.today().year)
    year_sel = fields.Selection(
        selection='_year_choices', string='Year',
        compute='_compute_year_sels', inverse='_set_year_sel', store=False,
    )
    previous_year_number = fields.Integer('Previous Years', default=0)

    # ── Quarter period ───────────────────────────────────────────
    quarter = fields.Selection(QUARTER_SEL, 'Quarter')
    quarter_year = fields.Integer('Quarter Year', default=0)
    quarter_year_sel = fields.Selection(
        selection='_year_choices', string='Quarter Year',
        compute='_compute_year_sels', inverse='_set_quarter_year_sel', store=False,
    )
    previous_quarter_number = fields.Integer('Previous Quarters', default=0)

    # ── Month period ─────────────────────────────────────────────
    month = fields.Selection(MONTH_SEL, 'Month')
    month_year = fields.Integer('Month Year', default=0)
    month_year_sel = fields.Selection(
        selection='_year_choices', string='Month Year',
        compute='_compute_year_sels', inverse='_set_month_year_sel', store=False,
    )
    previous_month_number = fields.Integer('Previous Years', default=0)

    # ── Report section filter ────────────────────────────────────
    active_section = fields.Selection([
        ('all',              'All Sections'),
        ('yearly',           'Yearly Data'),
        ('quarterly',        'Quarterly Data'),
        ('current_quarterly','Current Year Quarterly'),
        ('monthly',          'Monthly Report'),
        ('as_of_month',      'As Of Month'),
        ('current_months',   "Current Year's Months"),
    ], 'Show Section', default='all')

    filter_template_id = fields.Many2one(
        'bsi.dashboard.filter.template', 'Filter Template',
        ondelete='set null',
    )

    # ── Collapse state (persisted so PDF/XLSX respect it) ────────
    # Comma-separated path keys of sections the user has closed, e.g. "d12,d12-45"
    expanded_paths = fields.Text('Expanded Paths', default='')

    # ── Display options ──────────────────────────────────────────
    decimal = fields.Integer('Decimal', default=0)
    value = fields.Float('Divide By', default=1000.0)

    # ── Unified preview (dept tree + data, with clickable arrows) ─
    report_preview_html = fields.Html(
        'Report Preview',
        compute='_compute_report_preview',
        sanitize=False,
        store=False,
    )

    # ────────────────────────────────────────────────────────────
    # Year-dropdown helpers
    # ────────────────────────────────────────────────────────────

    @api.model
    def _year_choices(self):
        cur = date.today().year
        return [(str(y), str(y)) for y in range(cur - 20, cur + 6)]

    @api.depends('year', 'quarter_year', 'month_year')
    def _compute_year_sels(self):
        for r in self:
            r.year_sel = str(r.year) if r.year else False
            r.quarter_year_sel = str(r.quarter_year) if r.quarter_year else False
            r.month_year_sel = str(r.month_year) if r.month_year else False

    def _set_year_sel(self):
        for r in self:
            r.year = int(r.year_sel) if r.year_sel else 0

    def _set_quarter_year_sel(self):
        for r in self:
            r.quarter_year = int(r.quarter_year_sel) if r.quarter_year_sel else 0

    def _set_month_year_sel(self):
        for r in self:
            r.month_year = int(r.month_year_sel) if r.month_year_sel else 0

    # ────────────────────────────────────────────────────────────
    # Filter Template — apply saved preset to this config
    # ────────────────────────────────────────────────────────────

    def action_apply_template(self):
        for rec in self:
            t = rec.filter_template_id
            if not t:
                return
            vals = {
                'active_section':          t.section,
                'decimal':                 t.decimal,
                'value':                   t.value,
            }
            # Copy whichever filter fields are relevant for the template's section
            if t.section == 'yearly':
                vals.update({'year': t.year, 'previous_year_number': t.previous_year_number})
            elif t.section in ('quarterly', 'current_quarterly'):
                vals.update({
                    'quarter':                  t.quarter,
                    'quarter_year':             t.quarter_year,
                    'previous_quarter_number':  t.previous_quarter_number,
                })
            elif t.section in ('monthly', 'as_of_month'):
                vals.update({
                    'month':                t.month,
                    'month_year':           t.month_year,
                    'previous_month_number':t.previous_month_number,
                })
            elif t.section == 'current_months':
                vals.update({'month_year': t.month_year})
            rec.write(vals)

    # ────────────────────────────────────────────────────────────
    # Collapse state — persisted so PDF/XLSX respect it
    # ────────────────────────────────────────────────────────────

    def toggle_collapsed_path(self, key, collapsing):
        """
        Called from JS after the user clicks ▶/▼.
        Default state is ALL COLLAPSED, so we track what's been OPENED.
        collapsing=False → user just opened  the section → add key to expanded set
        collapsing=True  → user just closed  the section → remove key from expanded set
        """
        for rec in self:
            expanded = set(filter(None, (rec.expanded_paths or '').split(',')))
            if collapsing:
                expanded.discard(key)
            else:
                expanded.add(key)
            rec.write({'expanded_paths': ','.join(sorted(expanded))})

    def _get_visible_rows(self, rows):
        """
        Return only rows that are visible given the user's expand state.
        Default is ALL COLLAPSED, so only root rows (no parent) are visible
        unless the user has explicitly expanded their ancestor chain.
        """
        expanded = set(filter(None, (self.expanded_paths or '').split(',')))
        result = []
        for row in rows:
            path = row.get('path', ())
            if len(path) <= 1:
                # Root-level rows are always included
                result.append(row)
            else:
                # Visible only if every ancestor in the chain has been expanded
                all_open = all(
                    self._path_key(path[:i]) in expanded
                    for i in range(1, len(path))
                )
                if all_open:
                    result.append(row)
        return result

    # ────────────────────────────────────────────────────────────
    # Department tree — built from data.mapping (fast, no SQL)
    # ────────────────────────────────────────────────────────────

    def _build_dept_tree(self):
        mappings = self.env['data.mapping'].search([
            ('company_id', '=', self.company_id.id),
            ('parent_department_id', '!=', False),
        ])
        slot_fields = [
            'parent_department_id',
            'department_child_first',
            'department_child_sec',
            'department_child_third',
            'department_child_fourth',
        ]
        roots = {}
        for m in mappings:
            path_depts = []
            for sf in slot_fields:
                d = getattr(m, sf, False)
                if d:
                    path_depts.append(d)
                else:
                    break
            if not path_depts:
                continue
            parent = path_depts[0]
            if parent.id not in roots:
                roots[parent.id] = {'dept': parent, 'path': (parent.id,), 'children': {}}
            current = roots[parent.id]
            for d in path_depts[1:]:
                if d.id not in current['children']:
                    current['children'][d.id] = {
                        'dept': d,
                        'path': current['path'] + (d.id,),
                        'children': {},
                    }
                current = current['children'][d.id]
        return roots

    def _flatten_dept_tree(self, nodes):
        rows = []
        for node_id in sorted(nodes, key=lambda nid: nodes[nid]['dept'].sequence):
            node = nodes[node_id]
            has_children = bool(node['children'])
            level = len(node['path']) - 1
            # Root-level depts (level 0) always show as section rows so they
            # appear bold/uppercase even when they have no child departments.
            is_section = has_children or level == 0
            rows.append({
                'name': node['dept'].name,
                'row_type': 'section' if is_section else 'line',
                'level': level,
                'path': node['path'],
            })
            if has_children:
                rows.extend(self._flatten_dept_tree(node['children']))
        return rows

    # ────────────────────────────────────────────────────────────
    # Helpers for collapse JS attributes
    # ────────────────────────────────────────────────────────────

    @staticmethod
    def _path_key(path):
        """Unique HTML-safe key for a dept path tuple."""
        return 'd' + '-'.join(str(i) for i in path)

    @staticmethod
    def _row_data_p(row):
        """pipe-separated ancestor keys for data-p attribute."""
        path = row['path']
        prefixes = [path[:i] for i in range(1, len(path))]
        return '|'.join('d' + '-'.join(str(x) for x in p) for p in prefixes)

    # ────────────────────────────────────────────────────────────
    # Balance computation from Journal Items (bsi_sgd_amount)
    # ────────────────────────────────────────────────────────────

    def _fetch_dept_amounts(self, d_from, d_to):
        """
        Single SQL per period: fetches bsi_sgd_amount from posted journal items.
        Uses aml.date and aml.company_id (same as moleac_advance_dashboard).

        Returns:
          parent_totals  {parent_id: float}   — sum per parent dept
          child_totals   {(parent_id, child_id): float}  — sum per (parent, child)
        """
        self.env.cr.execute("""
            WITH ji AS (
                SELECT
                    aml.parent_department_id  AS pid,
                    aml.department_child_first AS c1,
                    aml.department_child_sec   AS c2,
                    aml.department_child_third  AS c3,
                    aml.department_child_fourth AS c4,
                    aml.bsi_sgd_amount          AS amt
                FROM account_move_line  aml
                JOIN account_move       am  ON am.id = aml.move_id
               WHERE aml.date         BETWEEN %s AND %s
                 AND aml.company_id   = %s
                 AND am.state         = 'posted'
                 AND aml.parent_department_id IS NOT NULL
            )
            SELECT pid, NULL::int AS cid, COALESCE(SUM(amt), 0) FROM ji GROUP BY pid
            UNION ALL
            SELECT pid, c1 AS cid, COALESCE(SUM(amt), 0) FROM ji WHERE c1 IS NOT NULL GROUP BY pid, c1
            UNION ALL
            SELECT pid, c2 AS cid, COALESCE(SUM(amt), 0) FROM ji WHERE c2 IS NOT NULL GROUP BY pid, c2
            UNION ALL
            SELECT pid, c3 AS cid, COALESCE(SUM(amt), 0) FROM ji WHERE c3 IS NOT NULL GROUP BY pid, c3
            UNION ALL
            SELECT pid, c4 AS cid, COALESCE(SUM(amt), 0) FROM ji WHERE c4 IS NOT NULL GROUP BY pid, c4
        """, (d_from, d_to, self.company_id.id))

        parent_totals = {}
        child_totals  = {}
        for pid, cid, total in self.env.cr.fetchall():
            amt = float(total or 0.0)
            if cid is None:
                parent_totals[pid] = parent_totals.get(pid, 0.0) + amt
            else:
                key = (pid, cid)
                child_totals[key] = child_totals.get(key, 0.0) + amt

        return parent_totals, child_totals

    def _lookup_amount(self, path, parent_totals, child_totals):
        """Look up pre-fetched amount for a dept path.

        The SQL always keys child rows by (root_parent_id, child_dept_id)
        because parent_department_id on aml is always the root level.
        So for any depth we use path[0] (root) and path[-1] (leaf).
        """
        if len(path) == 1:
            return parent_totals.get(path[0], 0.0)
        elif len(path) >= 2:
            return child_totals.get((path[0], path[-1]), 0.0)
        return 0.0

    # ────────────────────────────────────────────────────────────
    # Report data
    # ────────────────────────────────────────────────────────────

    def get_report_data(self, all_sections=False):
        dec = self.decimal if self.decimal is not None and self.decimal >= 0 else 2
        roots = self._build_dept_tree()
        dept_rows_tmpl = self._flatten_dept_tree(roots)

        def attach_balances(cols):
            # One DB query per period column (much faster than per dept×period)
            period_data = []
            for _lbl, d_from, d_to in cols:
                pt, ct = self._fetch_dept_amounts(d_from, d_to)
                period_data.append((pt, ct))

            rows = []
            for dr in dept_rows_tmpl:
                bals = []
                for pt, ct in period_data:
                    raw = self._lookup_amount(dr['path'], pt, ct)
                    if self.value and self.value != 0 and self.value != 1:
                        raw = raw / self.value
                    bals.append(round(raw, dec))

                if dr['row_type'] == 'section':
                    # Section header shows its own total (same as Total row below)
                    # so the user can see the group sum at a glance
                    rows.append({**dr, 'balances': bals})
                else:
                    rows.append({**dr, 'balances': bals})
            return rows

        sections = []

        # ── 1. Yearly Data ────────────────────────────────────────────
        if self.year:
            prev_n = max(self.previous_year_number or 0, 0)
            cols = [(str(self.year - i),
                     date(self.year - i, 1, 1),
                     date(self.year - i, 12, 31))
                    for i in range(1 + prev_n)]
            # "Current Year" always refers to the selected year, not today's year
            pgs = [{'label': 'Current Year', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years', 'span': prev_n})
            sections.append({
                'section_key': 'yearly',
                'title': 'Yearly Data', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # ── 2. Quarterly Data ─────────────────────────────────────────
        if self.quarter and self.quarter_year:
            q = self.quarter
            y = self.quarter_year
            prev_n = max(self.previous_quarter_number or 0, 0)
            sm, sd, em, ed = _Q_DATES[q]
            cols = [
                (f'{q}/{y - i}', date(y - i, sm, sd), date(y - i, em, ed))
                for i in range(1 + prev_n)
            ]
            # "Current Quarter" always refers to the selected quarter/year
            pgs = [{'label': 'Current Quarter', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years', 'span': prev_n})
            sections.append({
                'section_key': 'quarterly',
                'title': 'Quarterly Data', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # ── 3. Current Year Quarterly ─────────────────────────────────
        if self.quarter_year:
            y = self.quarter_year
            prev_n = max(self.previous_quarter_number or 0, 0)
            cols = []
            pgs  = []
            for yr in range(y, y - (1 + prev_n), -1):
                for qn in range(4, 0, -1):
                    sm, sd, em, ed = _Q_DATES[f'Q{qn}']
                    cols.append((f'Q{qn}/{yr}', date(yr, sm, sd), date(yr, em, ed)))
                # First year in loop = selected year → "Current Year"; rest → actual year
                pgs.append({'label': 'Current Year' if yr == y else str(yr), 'span': 4})
            sections.append({
                'section_key': 'current_quarterly',
                'title': f'Current Year Quarterly  ({y})',
                'columns': cols,
                'period_groups': pgs,
                'rows': attach_balances(cols),
                'header_style': 'single',
            })

        # ── 4. Monthly Report ─────────────────────────────────────────
        if self.month and self.month_year:
            m, y = int(self.month), self.month_year
            prev_n = max(self.previous_month_number or 0, 0)
            cols = []
            for i in range(1 + prev_n):
                yr   = y - i
                last = calendar.monthrange(yr, m)[1]
                cols.append((
                    f'{calendar.month_abbr[m]} {yr}',
                    date(yr, m, 1), date(yr, m, last),
                ))
            # "Current Month" always refers to the selected month/year
            pgs = [{'label': 'Current Month', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years', 'span': prev_n})
            sections.append({
                'section_key': 'monthly',
                'title': 'Monthly Report', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # ── 5. As Of Month (YTD) ──────────────────────────────────────
        if self.month and self.month_year:
            m, y = int(self.month), self.month_year
            prev_n = max(self.previous_month_number or 0, 0)
            cols = []
            for i in range(1 + prev_n):
                yr   = y - i
                last = calendar.monthrange(yr, m)[1]
                cols.append((
                    f'{m}M{yr}',
                    date(yr, 1, 1), date(yr, m, last),
                ))
            pgs = [{'label': 'Current YTD', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years YTD', 'span': prev_n})
            sections.append({
                'section_key': 'as_of_month',
                'title': 'As Of Month  (YTD)', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # ── 6. Current Year's Months ──────────────────────────────────
        if self.month_year:
            y    = self.month_year
            cols = []
            for mn in range(1, 13):
                last = calendar.monthrange(y, mn)[1]
                cols.append((
                    f'{calendar.month_abbr[mn]}{y}',
                    date(y, mn, 1), date(y, mn, last),
                ))
            sections.append({
                'section_key': 'current_months',
                'title': f"Current Year's Months  ({y})",
                'columns': cols,
                'period_groups': [{'label': 'Current Year', 'span': 12}],
                'rows': attach_balances(cols),
                'header_style': 'single',
            })

        # ── Apply active_section filter (preview only, skipped for export) ──
        if not all_sections:
            sel = self.active_section or 'all'
            if sel != 'all':
                sections = [s for s in sections if s.get('section_key') == sel]

        return {'sections': sections, 'decimal': dec}

    # ────────────────────────────────────────────────────────────
    # Preview render
    # ────────────────────────────────────────────────────────────

    @api.depends(
        'year', 'year_sel', 'previous_year_number',
        'quarter', 'quarter_year', 'quarter_year_sel', 'previous_quarter_number',
        'month', 'month_year', 'month_year_sel', 'previous_month_number',
        'decimal', 'value', 'company_id',
    )
    def _compute_report_preview(self):
        for rec in self:
            try:
                rec.report_preview_html = rec._render_full_preview()
            except Exception as e:
                rec.report_preview_html = (
                    f'<div style="color:#dc3545;padding:12px;">Preview error: {e}</div>'
                )

    # ── Design palette — light / muted / silent ────────────────────
    _C_ACT   = '#4A6FA5'   # actual period accent (muted slate-blue)
    _C_PRV   = '#7A8FA6'   # previous period (muted blue-gray)
    _C_GRN   = '#4E8068'   # quarterly single (muted sage)
    _C_H1_BG = '#E8EDF5'   # group header row bg — actual
    _C_H1_TX = '#1E3A5F'   # group header row text — actual
    _C_H2_BG = '#EEF2F7'   # group header row bg — previous
    _C_H2_TX = '#4A5E73'   # group header row text — previous
    _C_COL   = '#F2F5FA'   # column-label row bg
    _C_COL_T = '#6B7A8D'   # column-label row text
    _C_L0_BG = '#EBF0F8'   # level-0 parent row bg
    _C_L1_BG = '#F4F7FB'   # level-1 child section row bg
    _C_ROW_A = '#FFFFFF'   # leaf row — even
    _C_ROW_B = '#FAFBFD'   # leaf row — odd
    _C_TOT   = '#E2EAF4'   # total row bg
    _C_BDR   = '#D6DFE9'   # main border
    _C_BDR_L = '#ECF0F5'   # lighter border (inside rows)
    _C_TXT   = '#1F2937'   # primary text
    _C_TXT_S = '#4B5563'   # secondary text
    _C_NEG   = '#B91C1C'   # negative amount

    def _render_full_preview(self):
        roots = self._build_dept_tree()
        dept_rows_tmpl = self._flatten_dept_tree(roots)
        data = self.get_report_data()
        sections = data['sections']
        decimal  = data['decimal']

        font = ("font-family:-apple-system,BlinkMacSystemFont,"
                "'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;"
                "font-size:12.5px;color:#1F2937;")

        wrap = [f'<div style="{font}overflow-x:auto;padding:2px 0;">']

        if not roots:
            wrap.append(
                f'<div style="text-align:center;padding:32px;color:#9CA3AF;'
                f'border:1px dashed {self._C_BDR};border-radius:8px;background:#FAFBFD;">'
                f'<div style="font-size:13px;font-weight:600;color:{self._C_TXT_S};">'
                f'No department mappings found</div>'
                f'<div style="font-size:11px;margin-top:6px;">'
                f'Go to Accounting &#8594; Data Mapping Config &#8594; Data Mapping</div>'
                f'</div>'
            )
        elif not sections:
            wrap.append(self._render_dept_only_table(dept_rows_tmpl))
            wrap.append(
                f'<div style="text-align:center;color:#9CA3AF;font-size:11px;'
                f'padding:6px 0 2px;">Configure a period above to display financial data</div>'
            )
        else:
            for i, section in enumerate(sections):
                if i > 0:
                    wrap.append(f'<div style="height:16px;"></div>')
                wrap.append(self._render_section_with_tree(section, decimal))

        wrap.append('</div>')
        return ''.join(wrap)

    # ── Dept-only table (no data columns) ─────────────────────────

    def _render_dept_only_table(self, dept_rows):
        p = [
            f'<table style="width:100%;max-width:500px;border-collapse:collapse;'
            f'margin:0 auto 12px;border:1px solid {self._C_BDR};border-radius:8px;'
            f'overflow:hidden;">'
            f'<thead><tr style="background:{self._C_H1_BG};">'
            f'<th style="padding:10px 16px;text-align:left;font-size:11.5px;'
            f'font-weight:700;color:{self._C_H1_TX};letter-spacing:0.04em;">'
            f'Department Structure</th>'
            f'</tr></thead><tbody>'
        ]
        for row in dept_rows:
            p.append(self._dept_row_html(row, []))
        p.append('</tbody></table>')
        return ''.join(p)

    # ── Section table: dept tree + period columns ──────────────────

    def _render_section_with_tree(self, section, decimal):
        columns = section['columns']
        pgs     = section['period_groups']
        rows    = section['rows']
        style   = section.get('header_style', 'actual_prev')
        ncols   = len(columns)

        def fmt(b):
            return '{:,.{}f}'.format(b, decimal) if isinstance(b, (int, float)) else '—'

        def pg_colors(idx):
            if style == 'single':
                return self._C_H1_BG, self._C_H1_TX
            return (self._C_H1_BG, self._C_H1_TX) if idx == 0 else (self._C_H2_BG, self._C_H2_TX)

        p = []

        # ── Section title ────────────────────────────────────────
        p.append(
            f'<div style="padding:7px 14px;background:#F7F9FC;'
            f'border:1px solid {self._C_BDR};border-bottom:none;'
            f'border-radius:6px 6px 0 0;">'
            f'<span style="font-size:11px;font-weight:700;color:{self._C_TXT_S};'
            f'letter-spacing:0.07em;text-transform:uppercase;">'
            f'{section["title"]}</span></div>'
        )

        # ── Table ─────────────────────────────────────────────────
        p.append(
            f'<div style="overflow-x:auto;border:1px solid {self._C_BDR};'
            f'border-radius:0 0 6px 6px;">'
            f'<table style="width:100%;border-collapse:collapse;">'
            f'<thead>'
        )

        # Row 1 — period group labels
        p.append(
            f'<tr>'
            f'<th rowspan="2" style="padding:9px 16px;text-align:left;'
            f'font-size:11px;font-weight:700;color:{self._C_TXT};'
            f'vertical-align:bottom;min-width:230px;'
            f'background:{self._C_COL};'
            f'border-right:1px solid {self._C_BDR};'
            f'white-space:nowrap;">Department</th>'
        )
        for idx, pg in enumerate(pgs):
            bg, tx = pg_colors(idx)
            p.append(
                f'<th colspan="{pg["span"]}" style="padding:8px 10px;'
                f'text-align:center;font-size:10.5px;font-weight:700;'
                f'color:{tx};background:{bg};'
                f'border-left:1px solid {self._C_BDR};'
                f'letter-spacing:0.05em;white-space:nowrap;">'
                f'{pg["label"]}</th>'
            )
        p.append('</tr>')

        # Row 2 — individual column labels
        p.append(f'<tr style="background:{self._C_COL};">')
        ci = 0
        for idx, pg in enumerate(pgs):
            for j in range(pg['span']):
                lbl = columns[ci][0] if ci < ncols else ''
                bdr = (f'border-left:1px solid {self._C_BDR};' if j == 0
                       else f'border-left:1px solid {self._C_BDR_L};')
                p.append(
                    f'<th style="padding:5px 10px;text-align:right;'
                    f'font-size:10px;font-weight:600;color:{self._C_COL_T};'
                    f'{bdr}white-space:nowrap;">{lbl}</th>'
                )
                ci += 1
        p.append('</tr>')

        p.append('</thead><tbody>')
        for row in rows:
            p.append(self._dept_row_html(row, pgs, columns=columns, fmt_fn=fmt))
        p.append('</tbody></table></div>')
        return ''.join(p)

    # ── Single dept row ────────────────────────────────────────────

    def _dept_row_html(self, row, pgs, columns=None, fmt_fn=None):
        level    = row.get('level', 0)
        rtype    = row.get('row_type', 'line')
        bals     = row.get('balances', [])
        name     = row.get('name', '')
        path     = row.get('path', ())
        has_data = bool(columns)

        node_key = self._path_key(path)
        data_p   = self._row_data_p(row)
        dp_attr  = f' data-p="{data_p}"' if data_p else ''

        # Use 0 when the record hasn't been saved yet (NewId object, not int)
        rec_id = self.id if isinstance(self.id, int) else 0

        indent = level * 18

        # Dept IDs for drill-down links
        root_id = path[0] if path else 0
        leaf_id = path[-1] if path else 0

        def _num_cell(b, first_in_group, bold=False, bg='', d_from='', d_to=''):
            bdr = (f'border-left:1px solid {self._C_BDR};' if first_in_group
                   else f'border-left:1px solid {self._C_BDR_L};')
            bg_s = f'background:{bg};' if bg else ''
            fw   = 'font-weight:600;' if bold else ''
            # Build drill-down data attributes when we have a saved record and dates
            if rec_id and d_from and d_to:
                link = (f' onclick="bsiOpenJI(this)" '
                        f'data-cfg="{rec_id}" data-from="{d_from}" data-to="{d_to}" '
                        f'data-root="{root_id}" data-leaf="{leaf_id}" '
                        f'title="Click to view journal items"')
                cursor = 'cursor:pointer;'
            else:
                link = ''
                cursor = ''
            if b is None or b == '':
                return (f'<td{link} style="text-align:right;padding:5px 10px;'
                        f'color:#9CA3AF;{bdr}{bg_s}{fw}{cursor}">—</td>')
            col_s = f'color:{self._C_NEG};' if isinstance(b, (int, float)) and b < 0 else ''
            hover = f'text-decoration:underline dotted;' if link else ''
            return (f'<td{link} style="text-align:right;padding:5px 10px;'
                    f'{col_s}{bdr}{bg_s}{fw}{cursor}{hover}">{fmt_fn(b)}</td>')

        def _data_cells(bold=False, bg=''):
            if not has_data:
                return ''
            cells = []
            ci = 0
            for pg in pgs:
                for j in range(pg['span']):
                    b = bals[ci] if ci < len(bals) else None
                    # Extract date range from columns tuple (label, d_from, d_to)
                    d_from = str(columns[ci][1]) if columns and ci < len(columns) else ''
                    d_to   = str(columns[ci][2]) if columns and ci < len(columns) else ''
                    cells.append(_num_cell(b, j == 0, bold=bold, bg=bg,
                                          d_from=d_from, d_to=d_to))
                    ci += 1
            return ''.join(cells)

        # Rows with a parent start hidden; root rows are always visible
        is_child  = bool(data_p)
        hide_style = 'display:none;' if is_child else ''

        # ── Parent / section row ────────────────────────────────────
        if rtype == 'section':
            pl     = 10 + indent
            lvl_bg = self._C_L0_BG if level == 0 else self._C_L1_BG
            arrow  = (
                f'<span data-arrow="{node_key}" data-open="0" '
                f'onclick="bsiTgl(\'{node_key}\',this,{rec_id})" '
                f'style="cursor:pointer;color:{self._C_ACT};font-size:10px;'
                f'display:inline-block;width:14px;text-align:center;'
                f'user-select:none;">&#9654;</span>'
            )
            name_td = (
                f'<td style="padding:7px 14px 7px {pl}px;font-weight:700;'
                f'font-size:11px;text-transform:uppercase;letter-spacing:0.06em;'
                f'color:{self._C_TXT};border-right:1px solid {self._C_BDR};'
                f'background:{lvl_bg};white-space:nowrap;">'
                f'{arrow}&nbsp;{name}</td>'
            )
            return (
                f'<tr{dp_attr} style="{hide_style}background:{lvl_bg};">'
                f'{name_td}{_data_cells(bold=True, bg=lvl_bg)}</tr>'
            )

        # ── Leaf / data row ─────────────────────────────────────────
        elif rtype == 'line':
            pl     = 12 + indent
            row_bg = self._C_ROW_A if level % 2 == 0 else self._C_ROW_B
            dash   = (
                f'<span style="color:{self._C_BDR_L};display:inline-block;'
                f'width:14px;text-align:center;">–</span>'
            )
            name_td = (
                f'<td style="padding:4px 14px 4px {pl}px;color:{self._C_TXT_S};'
                f'border-right:1px solid {self._C_BDR_L};'
                f'border-bottom:1px solid {self._C_BDR_L};background:{row_bg};">'
                f'{dash}&nbsp;{name}</td>'
            )
            return (
                f'<tr{dp_attr} style="{hide_style}background:{row_bg};">'
                f'{name_td}{_data_cells(bg=row_bg)}</tr>'
            )

        # ── Total row ───────────────────────────────────────────────
        elif rtype == 'total':
            pl  = 10 + indent
            name_td = (
                f'<td style="padding:6px 14px 6px {pl}px;font-weight:700;'
                f'font-size:11px;color:{self._C_TXT};background:{self._C_TOT};'
                f'border-right:1px solid {self._C_BDR};'
                f'border-top:1px solid {self._C_BDR};'
                f'border-bottom:1px solid {self._C_BDR};">{name}</td>'
            )
            return (
                f'<tr{dp_attr} style="{hide_style}background:{self._C_TOT};">'
                f'{name_td}{_data_cells(bold=True, bg=self._C_TOT)}</tr>'
            )

        return ''

    # ────────────────────────────────────────────────────────────
    # Drill-down: open journal items for a cell click
    # ────────────────────────────────────────────────────────────

    def action_open_journal_items(self, date_from_str, date_to_str, root_dept_id, leaf_dept_id):
        """
        Return an act_window action for account.move.line filtered by
        the clicked cell's period and department path.
        Called from JS via RPC when user clicks a value cell.
        """
        domain = [
            ('date', '>=', date_from_str),
            ('date', '<=', date_to_str),
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
            ('parent_department_id', '=', root_dept_id),
        ]
        if leaf_dept_id and leaf_dept_id != root_dept_id:
            # leaf can appear in any of the 4 child-dept slot fields
            domain += [
                '|', '|', '|',
                ('department_child_first',  '=', leaf_dept_id),
                ('department_child_sec',    '=', leaf_dept_id),
                ('department_child_third',  '=', leaf_dept_id),
                ('department_child_fourth', '=', leaf_dept_id),
            ]
        return {
            'type': 'ir.actions.act_window',
            'name': 'Journal Items',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
            'target': 'current',
            'context': {'create': False},
        }

    # ────────────────────────────────────────────────────────────
    # Actions — generate ALL sections directly (no wizard)
    # ────────────────────────────────────────────────────────────

    def action_export_all_pdf(self):
        """Print PDF with every configured section — no wizard."""
        return self.env.ref(
            'moleac_dynamic_dashboard.action_report_bsi_dashboard'
        ).report_action(
            self,
            data={'config_id': self.id},
        )

    def action_export_all_xlsx(self):
        """Download XLSX with every configured section — no wizard."""
        return self._do_generate_xlsx(selected_sections=None)

    # ────────────────────────────────────────────────────────────
    # Actions — open export wizard (selective)
    # ────────────────────────────────────────────────────────────

    def action_view_report(self):
        return self._open_export_wizard('pdf')

    def action_download_xlsx(self):
        return self._open_export_wizard('xlsx')

    def _open_export_wizard(self, export_type):
        wizard = self.env['bsi.dashboard.export.wizard'].create({
            'config_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'bsi.dashboard.export.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_export_type': export_type},
        }

    # ────────────────────────────────────────────────────────────
    # XLSX generation (called by wizard)
    # ────────────────────────────────────────────────────────────

    def _do_generate_xlsx(self, selected_sections=None):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(
                _("The 'xlsxwriter' library is required. Run: pip install xlsxwriter")
            )

        report   = self.get_report_data()
        sections = report['sections']
        decimal  = report['decimal']

        # Filter by wizard selection + collapse state
        if selected_sections:
            sections = [s for s in sections if s.get('section_key') in selected_sections]
        for section in sections:
            section['rows'] = self._get_visible_rows(section['rows'])

        num_fmt = f'#,##0.{"0" * decimal}'
        max_data_cols = max(
            (len(s['columns']) for s in sections if s['columns']), default=1
        )

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        def f(**kw):
            return wb.add_format(kw)

        title_fmt = f(bold=True, font_size=15, align='center', valign='vcenter')
        sub_fmt   = f(font_size=11, align='center', italic=True, font_color='#6c757d')
        sec_title = f(bold=True, font_size=12, font_color='#1E3A5F',
                      align='left', bg_color='#EBF0F8', top=1, bottom=1)
        hdr_act   = f(bold=True, bg_color='#4A6FA5', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_prev  = f(bold=True, bg_color='#7A8FA6', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_sing  = f(bold=True, bg_color='#4E8068', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_yr    = f(bold=True, bg_color='#F2F5FA', font_color='#6B7A8D', border=1,
                      align='center', valign='vcenter', font_size=10)
        hdr_name  = f(bold=True, bg_color='#EEF2F7', font_color='#1F2937', border=1,
                      align='left', valign='vcenter', font_size=11)
        sec_row   = f(bold=True, bg_color='#EBF0F8', font_size=10,
                      font_color='#1F2937', top=1, bottom=1, text_wrap=False)
        sec_r     = f(bold=True, bg_color='#EBF0F8', font_size=10,
                      font_color='#1F2937', top=1, bottom=1, align='right')
        ln_lbl    = f(font_size=10, font_color='#374151')
        ln_num    = f(num_format=num_fmt, font_size=10, align='right')
        ln_neg    = f(num_format=num_fmt, font_size=10, align='right', font_color='#B91C1C')
        tot_lbl   = f(bold=True, bg_color='#E2EAF4', top=1, bottom=1,
                      font_size=10, font_color='#1F2937')
        tot_num   = f(bold=True, bg_color='#E2EAF4', num_format=num_fmt,
                      top=1, bottom=1, align='right', font_size=10)
        tot_neg   = f(bold=True, bg_color='#E2EAF4', num_format=num_fmt,
                      top=1, bottom=1, align='right', font_size=10, font_color='#B91C1C')

        ws   = wb.add_worksheet(self.name[:31])
        xrow = 0

        ws.merge_range(xrow, 0, xrow, max_data_cols, self.name, title_fmt)
        ws.set_row(xrow, 24); xrow += 1
        ws.merge_range(xrow, 0, xrow, max_data_cols,
                       f'{self.company_id.name}  |  Amounts in SGD', sub_fmt)
        ws.set_row(xrow, 18); xrow += 2

        for section in sections:
            if not section['rows']:
                continue
            columns    = section['columns']
            pg         = section['period_groups']
            rows       = section['rows']
            style      = section.get('header_style', 'actual_prev')
            total_cols = len(columns) if columns else 1

            ws.merge_range(xrow, 0, xrow, max_data_cols, section['title'], sec_title)
            ws.set_row(xrow, 20); xrow += 1

            if pg and columns:
                ws.merge_range(xrow, 0, xrow + 1, 0, 'Department', hdr_name)
                xcol = 1
                for g in pg:
                    col_end = xcol + g['span'] - 1
                    if style == 'single':
                        fu = hdr_sing
                    elif xcol == 1:
                        fu = hdr_act
                    else:
                        fu = hdr_prev
                    if g['span'] > 1:
                        ws.merge_range(xrow, xcol, xrow, col_end, g['label'], fu)
                    else:
                        ws.write(xrow, xcol, g['label'], fu)
                    xcol = col_end + 1
                ws.set_row(xrow, 18); xrow += 1
                for i, col in enumerate(columns):
                    ws.write(xrow, i + 1, col[0], hdr_yr)
                ws.set_row(xrow, 16); xrow += 1
            else:
                ws.write(xrow, 0, 'Department', hdr_name)
                ws.write(xrow, 1, 'Balance', hdr_yr)
                ws.set_row(xrow, 18); xrow += 1

            for r in rows:
                level  = r.get('level', 0)
                rtype  = r['row_type']
                bals   = r.get('balances', [])
                indent = '   ' * level

                if rtype == 'section':
                    ws.write(xrow, 0, indent + r['name'].upper(), sec_row)
                    for i, b in enumerate(bals):
                        ws.write(xrow, i + 1, b,
                                 sec_r if not (isinstance(b, (int, float)) and b < 0) else
                                 f(bold=True, bg_color='#EBF0F8', top=1, bottom=1,
                                   align='right', font_color='#B91C1C', num_format=num_fmt))
                elif rtype == 'line':
                    ws.write(xrow, 0, indent + r['name'], ln_lbl)
                    for i, b in enumerate(bals):
                        ws.write(xrow, i + 1, b,
                                 ln_neg if isinstance(b, (int, float)) and b < 0 else ln_num)
                elif rtype == 'total':
                    ws.write(xrow, 0, indent + r['name'], tot_lbl)
                    for i, b in enumerate(bals):
                        ws.write(xrow, i + 1, b,
                                 tot_neg if isinstance(b, (int, float)) and b < 0 else tot_num)
                xrow += 1

            xrow += 1

        ws.set_column(0, 0, 44)
        for i in range(max_data_cols):
            ws.set_column(i + 1, i + 1, 16)

        wb.close()

        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'{self.name}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class ReportBsiDashboard(models.AbstractModel):
    _name = 'report.moleac_dynamic_dashboard.report_bsi_dashboard'
    _description = 'BSI Dashboard Report Parser'

    @api.model
    def _get_report_values(self, docids, data=None):
        # When triggered from the export wizard (TransientModel), the web
        # client may not include the record ID in the download URL, so
        # docids can be [].  We fall back to config_id stored in data.
        if docids:
            config_id = docids[0]
        else:
            config_id = (data or {}).get('config_id')
        if not config_id:
            raise UserError(_("No dashboard configuration specified for the report."))
        config   = self.env['bsi.dashboard.config'].browse(config_id)
        report   = config.get_report_data()
        sections = report['sections']

        selected = (data or {}).get('selected_sections')
        if selected:
            sections = [s for s in sections if s.get('section_key') in selected]

        for section in sections:
            section['rows'] = config._get_visible_rows(section['rows'])

        return {
            'docs': [config],
            'config': config,
            'sections': sections,
            'decimal': report['decimal'],
        }
