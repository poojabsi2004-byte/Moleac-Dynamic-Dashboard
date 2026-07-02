# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, fields

MONTH_SEL = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'),
    ('4', 'April'), ('5', 'May'), ('6', 'June'),
    ('7', 'July'), ('8', 'August'), ('9', 'September'),
    ('10', 'October'), ('11', 'November'), ('12', 'December'),
]

QUARTER_SEL = [('Q1', 'Q1'), ('Q2', 'Q2'), ('Q3', 'Q3'), ('Q4', 'Q4')]

SECTION_SEL = [
    ('yearly',           'Yearly Data'),
    ('quarterly',        'Quarterly Data'),
    ('current_quarterly','Current Year Quarterly'),
    ('monthly',          'Monthly Report'),
    ('as_of_month',      'As Of Month'),
    ('current_months',   "Current Year's Months"),
]


class BsiDashboardFilterTemplate(models.Model):
    _name        = 'bsi.dashboard.filter.template'
    _description = 'Dashboard Filter Template'
    _order       = 'name'

    name    = fields.Char('Template Name', required=True)
    section = fields.Selection(SECTION_SEL, 'Report Section', required=True)

    # ── Yearly ───────────────────────────────────────────────────
    year                 = fields.Integer('Year', default=lambda s: date.today().year)
    previous_year_number = fields.Integer('Previous Years', default=0)

    # ── Quarterly ────────────────────────────────────────────────
    quarter                 = fields.Selection(QUARTER_SEL, 'Quarter')
    quarter_year            = fields.Integer('Quarter Year', default=0)
    previous_quarter_number = fields.Integer('Previous Quarters', default=0)

    # ── Monthly ──────────────────────────────────────────────────
    month                = fields.Selection(MONTH_SEL, 'Month')
    month_year           = fields.Integer('Month Year', default=0)
    previous_month_number= fields.Integer('Previous Months', default=0)

    # ── Display ──────────────────────────────────────────────────
    decimal   = fields.Integer('Decimal', default=2)
    is_divide = fields.Boolean('Divide by Value')
    value     = fields.Float('Divide Value', default=1.0)
