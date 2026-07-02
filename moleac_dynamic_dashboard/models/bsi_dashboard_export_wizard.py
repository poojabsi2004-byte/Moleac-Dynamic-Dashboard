# -*- coding: utf-8 -*-
from odoo import models, fields, api


class BsiDashboardExportWizard(models.TransientModel):
    _name        = 'bsi.dashboard.export.wizard'
    _description = 'Dashboard Export – Section Selector'

    config_id = fields.Many2one(
        'bsi.dashboard.config', string='Config',
        required=True, ondelete='cascade',
    )

    # ── Which sections exist for this config (computed, not stored) ─
    has_yearly            = fields.Boolean(compute='_compute_available')
    has_quarterly         = fields.Boolean(compute='_compute_available')
    has_current_quarterly = fields.Boolean(compute='_compute_available')
    has_monthly           = fields.Boolean(compute='_compute_available')
    has_as_of_month       = fields.Boolean(compute='_compute_available')
    has_current_months    = fields.Boolean(compute='_compute_available')

    @api.depends('config_id')
    def _compute_available(self):
        for rec in self:
            c = rec.config_id
            rec.has_yearly            = bool(c.year)
            rec.has_quarterly         = bool(c.quarter and c.quarter_year)
            rec.has_current_quarterly = bool(c.quarter_year)
            rec.has_monthly           = bool(c.month and c.month_year)
            rec.has_as_of_month       = bool(c.month and c.month_year)
            rec.has_current_months    = bool(c.month_year)

    # ── User selection (default = all available) ────────────────────
    sel_yearly            = fields.Boolean('Yearly Data',             default=True)
    sel_quarterly         = fields.Boolean('Quarterly Data',          default=True)
    sel_current_quarterly = fields.Boolean('Current Year Quarterly',  default=True)
    sel_monthly           = fields.Boolean('Monthly Report',          default=True)
    sel_as_of_month       = fields.Boolean('As Of Month',             default=True)
    sel_current_months    = fields.Boolean("Current Year's Months",   default=True)

    # ────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────

    def _selected_keys(self):
        """Return list of section_key values the user has ticked."""
        mapping = [
            ('sel_yearly',            'yearly'),
            ('sel_quarterly',         'quarterly'),
            ('sel_current_quarterly', 'current_quarterly'),
            ('sel_monthly',           'monthly'),
            ('sel_as_of_month',       'as_of_month'),
            ('sel_current_months',    'current_months'),
        ]
        return [key for field, key in mapping if getattr(self, field)]

    # ────────────────────────────────────────────────────────────────
    # Actions
    # ────────────────────────────────────────────────────────────────

    def action_print_pdf(self):
        selected = self._selected_keys()
        return self.env.ref(
            'moleac_dynamic_dashboard.action_report_bsi_dashboard'
        ).report_action(
            self.config_id,
            data={
                'selected_sections': selected,
                'config_id': self.config_id.id,
            },
        )

    def action_export_xlsx(self):
        selected = self._selected_keys()
        return self.config_id._do_generate_xlsx(selected_sections=selected)
