from odoo import models, fields


class BsiMappingLine(models.Model):
    _name = 'bsi.mapping.line'
    _description = 'BSI Report Mapping Line'
    _order = 'sequence, id'

    config_id = fields.Many2one('bsi.dashboard.config', required=True, ondelete='cascade')
    sequence = fields.Integer('Seq', default=10)
    name = fields.Char('Label', required=True)
    row_type = fields.Selection([
        ('section', 'Section Header'),
        ('line', 'Line Item'),
        ('total', 'Total'),
        ('separator', 'Separator'),
    ], default='line', required=True, string='Row Type')
    indent_level = fields.Integer('Indent', default=0)
    negate = fields.Boolean(
        'Negate Sign',
        help="Flip the sign of balances (use for liabilities/equity which are credit-normal)",
    )
    account_group_ids = fields.Many2many(
        'account.group',
        'bsi_mapping_line_group_rel',
        'line_id', 'group_id',
        string='Account Groups',
    )
    account_ids = fields.Many2many(
        'account.account',
        'bsi_mapping_line_account_rel',
        'line_id', 'account_id',
        string='Accounts',
    )
