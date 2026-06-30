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

    # ── Display options ──────────────────────────────────────────
    decimal = fields.Integer('Decimal', default=2)
    is_divide = fields.Boolean('Divide')
    value = fields.Float('Value', default=1.0)

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
            rows.append({
                'name': node['dept'].name,
                'row_type': 'section' if has_children else 'line',
                'level': level,
                'path': node['path'],
            })
            if has_children:
                rows.extend(self._flatten_dept_tree(node['children']))
                rows.append({
                    'name': f"Total {node['dept'].name}",
                    'row_type': 'total',
                    'level': level,
                    'path': node['path'],
                })
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
        """
        pipe-separated ancestor keys for data-p attribute.
        Total rows include their OWN path so they collapse with their section.
        """
        path = row['path']
        rtype = row['row_type']
        end = len(path) + 1 if rtype == 'total' else len(path)
        prefixes = [path[:i] for i in range(1, end)]
        return '|'.join('d' + '-'.join(str(x) for x in p) for p in prefixes)

    # ────────────────────────────────────────────────────────────
    # Balance computation from Journal Items
    # ────────────────────────────────────────────────────────────

    def _sum_by_dept_path(self, path, d_from, d_to):
        params = [d_from, d_to, self.company_id.id]
        if len(path) == 1:
            conditions = 'aml.parent_department_id = %s'
            params.append(path[0])
        elif len(path) == 2:
            conditions = """
                aml.parent_department_id = %s
                AND (
                    aml.department_child_first  = %s
                 OR aml.department_child_sec    = %s
                 OR aml.department_child_third  = %s
                 OR aml.department_child_fourth = %s
                )
            """
            params += [path[0]] + [path[1]] * 4
        else:
            slot_sql = [
                'aml.parent_department_id',
                'aml.department_child_first',
                'aml.department_child_sec',
                'aml.department_child_third',
                'aml.department_child_fourth',
            ]
            conditions = ' AND '.join(f'{slot_sql[i]} = %s' for i in range(len(path)))
            params += list(path)

        query = f"""
            SELECT COALESCE(SUM(aml.balance), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.state      = 'posted'
               AND am.date BETWEEN %s AND %s
               AND am.company_id = %s
               AND {conditions}
        """
        self.env.cr.execute(query, params)
        val = self.env.cr.fetchone()[0] or 0.0
        if self.is_divide and self.value:
            val = val / self.value
        return val

    # ────────────────────────────────────────────────────────────
    # Report data
    # ────────────────────────────────────────────────────────────

    def get_report_data(self):
        dec = self.decimal or 2
        roots = self._build_dept_tree()
        dept_rows_tmpl = self._flatten_dept_tree(roots)

        def attach_balances(cols):
            rows = []
            for dr in dept_rows_tmpl:
                if dr['row_type'] == 'section':
                    rows.append({**dr, 'balances': []})
                else:
                    bals = [
                        round(self._sum_by_dept_path(dr['path'], d_from, d_to), dec)
                        for _, d_from, d_to in cols
                    ]
                    rows.append({**dr, 'balances': bals})
            return rows

        sections = []

        # 1. Yearly Data
        if self.year:
            prev_n = max(self.previous_year_number or 0, 0)
            cols = [(str(self.year - i), date(self.year - i, 1, 1), date(self.year - i, 12, 31))
                    for i in range(1 + prev_n)]
            pgs = [{'label': f'Actual  {self.year}', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years', 'span': prev_n})
            sections.append({
                'title': 'Yearly Data', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # 2. Quarterly Data
        if self.quarter and self.quarter_year:
            q, y = int(self.quarter[1]), self.quarter_year
            prev_n = max(self.previous_quarter_number or 0, 0)
            cols = []
            for i in range(1 + prev_n):
                qn, yr = q - i, y
                while qn < 1:
                    qn += 4; yr -= 1
                sm, sd, em, ed = _Q_DATES[f'Q{qn}']
                cols.append((f'Q{qn}/{yr}', date(yr, sm, sd), date(yr, em, ed)))
            pgs = [{'label': f'Actual  {self.quarter}/{self.quarter_year}', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Quarters', 'span': prev_n})
            sections.append({
                'title': 'Quarterly Data', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # 3. Current Year Quarterly
        if self.quarter_year:
            y = self.quarter_year
            cols = []
            for qn in range(1, 5):
                sm, sd, em, ed = _Q_DATES[f'Q{qn}']
                cols.append((f'Q{qn}', date(y, sm, sd), date(y, em, ed)))
            sections.append({
                'title': f'Current Year Quarterly  ({y})',
                'columns': cols,
                'period_groups': [{'label': str(y), 'span': 4}],
                'rows': attach_balances(cols),
                'header_style': 'single',
            })

        # 4. Monthly Report — same month, N previous years
        if self.month and self.month_year:
            m, y = int(self.month), self.month_year
            prev_n = max(self.previous_month_number or 0, 0)
            cols = []
            for i in range(1 + prev_n):
                yr = y - i
                last = calendar.monthrange(yr, m)[1]
                cols.append((f'{calendar.month_abbr[m]} {yr}', date(yr, m, 1), date(yr, m, last)))
            pgs = [{'label': f'Actual  {calendar.month_name[m]} {y}', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years', 'span': prev_n})
            sections.append({
                'title': 'Monthly Report', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # 5. As Of Month — YTD Jan → selected month
        if self.month and self.month_year:
            m, y = int(self.month), self.month_year
            prev_n = max(self.previous_month_number or 0, 0)
            cols = []
            for i in range(1 + prev_n):
                yr = y - i
                last = calendar.monthrange(yr, m)[1]
                cols.append((f'YTD {calendar.month_abbr[m]} {yr}', date(yr, 1, 1), date(yr, m, last)))
            pgs = [{'label': f'Actual  YTD {y}', 'span': 1}]
            if prev_n:
                pgs.append({'label': 'Previous Years YTD', 'span': prev_n})
            sections.append({
                'title': 'As Of Month  (YTD)', 'columns': cols,
                'period_groups': pgs, 'rows': attach_balances(cols),
                'header_style': 'actual_prev',
            })

        # 6. Current Year's Months
        if self.month_year:
            y = self.month_year
            cols = []
            for mn in range(1, 13):
                last = calendar.monthrange(y, mn)[1]
                cols.append((calendar.month_abbr[mn], date(y, mn, 1), date(y, mn, last)))
            sections.append({
                'title': f"Current Year's Months  ({y})",
                'columns': cols,
                'period_groups': [{'label': str(y), 'span': 12}],
                'rows': attach_balances(cols),
                'header_style': 'single',
            })

        return {'sections': sections, 'decimal': dec}

    # ────────────────────────────────────────────────────────────
    # Preview render
    # ────────────────────────────────────────────────────────────

    @api.depends(
        'year', 'year_sel', 'previous_year_number',
        'quarter', 'quarter_year', 'quarter_year_sel', 'previous_quarter_number',
        'month', 'month_year', 'month_year_sel', 'previous_month_number',
        'decimal', 'is_divide', 'value', 'company_id',
    )
    def _compute_report_preview(self):
        for rec in self:
            try:
                rec.report_preview_html = rec._render_full_preview()
            except Exception as e:
                rec.report_preview_html = (
                    f'<div style="color:#dc3545;padding:12px;">Preview error: {e}</div>'
                )

    _HDR_SINGLE = '#276749'
    _HDR_ACTUAL = '#1a56a0'
    _HDR_PREV   = '#4a5568'

    def _render_full_preview(self):
        roots = self._build_dept_tree()
        dept_rows_tmpl = self._flatten_dept_tree(roots)
        data = self.get_report_data()
        sections = data['sections']
        decimal = data['decimal']

        wrap = [
            '<div style="font-family:-apple-system,BlinkMacSystemFont,'
            '\'Segoe UI\',Roboto,sans-serif;font-size:13px;overflow-x:auto;">'
        ]

        # Report title
        wrap.append(
            '<div style="text-align:center;margin-bottom:16px;">'
            f'<div style="font-size:17px;font-weight:700;color:#1a202c;">{self.name}</div>'
            f'<div style="font-size:11px;color:#718096;margin-top:2px;">'
            f'{self.company_id.name}</div></div>'
        )

        if not roots:
            wrap.append(
                '<div style="text-align:center;padding:24px;color:#a0aec0;">'
                'No department mappings found for this company.<br/>'
                '<small>Go to Accounting &rarr; Data Mapping Config &rarr; Data Mapping</small>'
                '</div>'
            )
        elif not sections:
            # No period selected → show dept structure only (no data columns)
            wrap.append(self._render_dept_only_table(dept_rows_tmpl))
            wrap.append(
                '<p style="text-align:center;color:#a0aec0;font-size:11px;'
                'padding:8px 0 4px;">Select a period above to see financial data</p>'
            )
        else:
            for section in sections:
                wrap.append(self._render_section_with_tree(section, decimal))

        wrap.append('</div>')
        return ''.join(wrap)

    # ── Table: dept tree only (no data), arrows clickable ────────

    def _render_dept_only_table(self, dept_rows):
        p = ['<table style="width:100%;max-width:480px;border-collapse:collapse;'
             'margin:0 auto 12px;">']
        p.append(
            '<thead><tr style="background:#2d3748;color:#fff;">'
            '<th style="padding:10px 14px;text-align:left;font-size:12px;'
            'font-weight:700;">Department Structure</th></tr></thead>'
        )
        p.append('<tbody>')
        for row in dept_rows:
            p.append(self._dept_row_html(row, []))
        p.append('</tbody></table>')
        return ''.join(p)

    # ── Table: dept tree + period data columns ────────────────────

    def _render_section_with_tree(self, section, decimal):
        columns = section['columns']
        pgs     = section['period_groups']
        rows    = section['rows']
        style   = section.get('header_style', 'actual_prev')

        def fmt(b):
            return '{:,.{}f}'.format(b, decimal) if isinstance(b, (int, float)) else '—'

        def pg_bg(label):
            if style == 'single':
                return self._HDR_SINGLE
            return self._HDR_ACTUAL if ('Actual' in label or 'YTD' in label) else self._HDR_PREV

        ncols = len(columns)
        p = []

        # Section title (reflects selection)
        p.append(
            f'<div style="text-align:center;background:#1a202c;color:#fff;'
            f'font-size:13px;font-weight:700;padding:8px 14px;'
            f'border-radius:6px 6px 0 0;letter-spacing:0.04em;">'
            f'{section["title"]}</div>'
        )

        p.append('<table style="width:100%;border-collapse:collapse;'
                 'margin-bottom:24px;border:1px solid #cbd5e0;">')
        p.append('<thead>')

        if pgs and columns:
            # Row 1: group labels
            p.append(
                '<tr style="background:#2d3748;color:#fff;">'
                '<th rowspan="2" style="padding:8px 12px;text-align:left;'
                'font-size:12px;font-weight:700;vertical-align:bottom;'
                'min-width:220px;border-right:1px solid #4a5568;">'
                'Department</th>'
            )
            for pg in pgs:
                bg = pg_bg(pg['label'])
                p.append(
                    f'<th colspan="{pg["span"]}" style="padding:7px 6px;'
                    f'text-align:center;font-size:11px;font-weight:700;'
                    f'background:{bg};border-left:2px solid #718096;">'
                    f'{pg["label"]}</th>'
                )
            p.append('</tr>')

            # Row 2: period column labels
            p.append('<tr style="background:#3d4f63;color:#e2e8f0;">')
            ci = 0
            for pg in pgs:
                for j in range(pg['span']):
                    lbl = columns[ci][0] if ci < ncols else ''
                    bdr = 'border-left:2px solid #4a5568;' if j == 0 else 'border-left:1px solid #4a5568;'
                    p.append(
                        f'<th style="padding:5px 8px;text-align:right;'
                        f'font-size:10px;font-weight:600;{bdr}">{lbl}</th>'
                    )
                    ci += 1
            p.append('</tr>')
        else:
            p.append(
                '<tr style="background:#2d3748;color:#fff;">'
                '<th style="padding:10px 12px;text-align:left;">Department</th>'
                '<th style="padding:10px 12px;text-align:right;">Balance</th></tr>'
            )

        p.append('</thead><tbody>')

        for row in rows:
            p.append(self._dept_row_html(row, pgs, columns=columns, fmt_fn=fmt))

        p.append('</tbody></table>')
        return ''.join(p)

    # ── Single dept row HTML ──────────────────────────────────────

    def _dept_row_html(self, row, pgs, columns=None, fmt_fn=None):
        level = row.get('level', 0)
        rtype = row.get('row_type', 'line')
        bals  = row.get('balances', [])
        name  = row.get('name', '')
        path  = row.get('path', ())

        node_key = self._path_key(path)
        data_p   = self._row_data_p(row)
        dp_attr  = f' data-p="{data_p}"' if data_p else ''

        indent = level * 22
        has_data = bool(columns)

        def bal_cells():
            if not has_data:
                return ''
            cells = []
            ci = 0
            for pg in pgs:
                for j in range(pg['span']):
                    b = bals[ci] if ci < len(bals) else None
                    bdr = ('border-left:2px solid #cbd5e0;' if j == 0
                           else 'border-left:1px solid #e2e8f0;')
                    if b is None or b == '':
                        cells.append(f'<td style="text-align:right;padding:5px 8px;{bdr}">—</td>')
                    else:
                        color = '#c53030' if isinstance(b, (int, float)) and b < 0 else ''
                        col_s = f'color:{color};' if color else ''
                        cells.append(
                            f'<td style="text-align:right;padding:5px 8px;{col_s}{bdr}">'
                            f'{fmt_fn(b)}</td>'
                        )
                    ci += 1
            return ''.join(cells)

        # ── Section row (parent dept, expandable) ─────────────────
        if rtype == 'section':
            pl = 10 + indent
            arrow = (
                f'<span data-arrow="{node_key}" data-open="1" '
                f'onclick="bsiTgl(\'{node_key}\',this)" '
                f'style="cursor:pointer;color:#3182ce;font-size:11px;'
                f'display:inline-block;width:16px;text-align:center;'
                f'user-select:none;">&#9660;</span>'
            )
            colspan = '' if has_data else f' colspan="{1 + len(columns or [])}"'
            inner = (
                f'<tr{dp_attr} style="background:#e2e8f0;">'
                f'<td style="padding:7px 12px;padding-left:{pl}px;font-weight:700;'
                f'font-size:11px;text-transform:uppercase;letter-spacing:0.05em;'
                f'color:#2d3748;border-right:1px solid #cbd5e0;">'
                f'{arrow}&nbsp;{name}</td>'
            )
            if has_data:
                inner += bal_cells()
            inner += '</tr>'
            return inner

        # ── Leaf row (no children) ────────────────────────────────
        elif rtype == 'line':
            pl = 16 + indent
            arrow = (
                '<span style="color:#a0aec0;font-size:10px;display:inline-block;'
                'width:16px;text-align:center;">&#9658;</span>'
            )
            inner = (
                f'<tr{dp_attr} style="border-bottom:1px solid #edf2f7;background:#fff;">'
                f'<td style="padding:5px 12px;padding-left:{pl}px;color:#4a5568;'
                f'border-right:1px solid #e2e8f0;">'
                f'{arrow}&nbsp;{name}</td>'
            )
            if has_data:
                inner += bal_cells()
            else:
                inner += '<td></td>'
            inner += '</tr>'
            return inner

        # ── Total row ─────────────────────────────────────────────
        elif rtype == 'total':
            pl = 10 + indent

            def tot_cells():
                if not has_data:
                    return ''
                cells = []
                ci = 0
                for pg in pgs:
                    for j in range(pg['span']):
                        b = bals[ci] if ci < len(bals) else None
                        bdr = ('border-left:2px solid #a0aec0;' if j == 0
                               else 'border-left:1px solid #cbd5e0;')
                        if b is None:
                            cells.append(
                                f'<td style="text-align:right;padding:6px 8px;'
                                f'font-weight:700;{bdr}">—</td>'
                            )
                        else:
                            color = '#c53030' if isinstance(b, (int, float)) and b < 0 else '#1a202c'
                            cells.append(
                                f'<td style="text-align:right;padding:6px 8px;'
                                f'font-weight:700;color:{color};{bdr}">'
                                f'{fmt_fn(b)}</td>'
                            )
                        ci += 1
                return ''.join(cells)

            inner = (
                f'<tr{dp_attr} style="background:#f7fafc;border-top:2px solid #a0aec0;'
                f'border-bottom:2px solid #a0aec0;">'
                f'<td style="padding:6px 12px;padding-left:{pl}px;font-weight:700;'
                f'color:#1a202c;border-right:1px solid #e2e8f0;">{name}</td>'
            )
            if has_data:
                inner += tot_cells()
            else:
                inner += '<td></td>'
            inner += '</tr>'
            return inner

        return ''

    # ────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────

    def action_view_report(self):
        return self.env.ref(
            'moleac_dynamic_dashboard.action_report_bsi_dashboard'
        ).report_action(self)

    def action_download_xlsx(self):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(
                _("The 'xlsxwriter' library is required. Run: pip install xlsxwriter")
            )

        report = self.get_report_data()
        sections = report['sections']
        decimal  = report['decimal']
        num_fmt  = f'#,##0.{"0" * decimal}'
        max_data_cols = max(
            (len(s['columns']) for s in sections if s['columns']), default=1
        )

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        def f(**kw):
            return wb.add_format(kw)

        title_fmt = f(bold=True, font_size=15, align='center', valign='vcenter')
        sub_fmt   = f(font_size=11, align='center', italic=True, font_color='#6c757d')
        sec_title = f(bold=True, font_size=13, font_color='#c53030', align='center')
        hdr_act   = f(bold=True, bg_color='#1a56a0', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_prev  = f(bold=True, bg_color='#4a5568', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_sing  = f(bold=True, bg_color='#276749', font_color='#fff', border=1,
                      align='center', valign='vcenter', font_size=11)
        hdr_yr    = f(bold=True, bg_color='#3d4f63', font_color='#e2e8f0', border=1,
                      align='center', valign='vcenter', font_size=10)
        hdr_name  = f(bold=True, bg_color='#2d3748', font_color='#fff', border=1,
                      align='left', valign='vcenter', font_size=11)
        sec_row   = f(bold=True, bg_color='#e2e8f0', font_size=11, top=1, bottom=1)
        sec_r     = f(bold=True, bg_color='#e2e8f0', font_size=11, top=1, bottom=1, align='right')
        ln_lbl    = f(font_size=10)
        ln_num    = f(num_format=num_fmt, font_size=10, align='right')
        ln_neg    = f(num_format=num_fmt, font_size=10, align='right', font_color='#c53030')
        tot_lbl   = f(bold=True, bg_color='#f7fafc', top=2, bottom=2, font_size=10)
        tot_num   = f(bold=True, bg_color='#f7fafc', num_format=num_fmt, top=2, bottom=2,
                      align='right', font_size=10)
        tot_neg   = f(bold=True, bg_color='#f7fafc', num_format=num_fmt, top=2, bottom=2,
                      align='right', font_size=10, font_color='#c53030')

        ws   = wb.add_worksheet(self.name[:31])
        xrow = 0

        ws.merge_range(xrow, 0, xrow, max_data_cols, self.name, title_fmt)
        ws.set_row(xrow, 24); xrow += 1
        ws.merge_range(xrow, 0, xrow, max_data_cols, self.company_id.name, sub_fmt)
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
                    elif 'Actual' in g['label'] or 'YTD' in g['label']:
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
                indent = '  ' * level

                if rtype == 'section':
                    ws.write(xrow, 0, r['name'].upper(), sec_row)
                    for i in range(total_cols):
                        ws.write(xrow, i + 1, '', sec_r)
                elif rtype == 'line':
                    ws.write(xrow, 0, indent + r['name'], ln_lbl)
                    for i, b in enumerate(bals):
                        ws.write(xrow, i + 1, b, ln_neg if isinstance(b, (int, float)) and b < 0 else ln_num)
                elif rtype == 'total':
                    ws.write(xrow, 0, indent + r['name'], tot_lbl)
                    for i, b in enumerate(bals):
                        ws.write(xrow, i + 1, b, tot_neg if isinstance(b, (int, float)) and b < 0 else tot_num)
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
        config = self.env['bsi.dashboard.config'].browse(docids[0])
        report = config.get_report_data()
        return {
            'docs': [config],
            'config': config,
            'sections': report['sections'],
            'decimal': report['decimal'],
        }
