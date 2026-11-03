# -*- coding: utf-8 -*-
from datetime import date

from odoo import fields, models


class HrLeaveReconciliationWizard(models.TransientModel):
    _name = 'hr.leave.reconciliation.wizard'
    _description = 'Yıllık İzin Mutabakat Sihirbazı'

    def _default_holiday_status(self):
        return self.env['hr.leave.type'].search([
            ('company_id', 'in', [self.env.company.id, False]),
            '|', ('name', 'ilike', 'annual'), ('name', 'ilike', 'yıllık'),
        ], limit=1)

    employee_id = fields.Many2one(
        'hr.employee', string='Personel', required=True)
    holiday_status_id = fields.Many2one(
        'hr.leave.type', string='İzin Türü', required=True,
        default=_default_holiday_status)
    year = fields.Integer(
        string='Yıl', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    reconciliation_date = fields.Date(
        string='Mutabakat Tarihi', required=True,
        default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', readonly=True)

    def _get_year_bounds(self):
        self.ensure_one()
        return date(self.year, 1, 1), date(self.year, 12, 31)

    def _get_year_allocations(self):
        self.ensure_one()
        year_start, year_end = self._get_year_bounds()
        return self.env['hr.leave.allocation'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', year_end),
            '|', ('date_to', '=', False), ('date_to', '>=', year_start),
        ])

    def _get_year_leaves(self):
        self.ensure_one()
        year_start, year_end = self._get_year_bounds()
        return self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', year_end),
            '|', ('request_date_to', '=', False),
            ('request_date_to', '>=', year_start),
        ], order='request_date_from')

    def _get_carryover(self):
        """Seçilen yıla devreden bakiye: yıla girerken hâlâ geçerli olan eski
        tahsislerin, kendi geçerlilik penceresinde kullanılmış izinler
        düşüldükten sonraki kalan günlerinin toplamı."""
        self.ensure_one()
        year_start, _year_end = self._get_year_bounds()
        prior_allocations = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
            ('state', '=', 'validate'),
            ('date_from', '<', year_start),
            '|', ('date_to', '=', False), ('date_to', '>=', year_start),
        ])
        carryover = 0.0
        Leave = self.env['hr.leave']
        for allocation in prior_allocations:
            domain = [
                ('employee_id', '=', self.employee_id.id),
                ('holiday_status_id', '=', self.holiday_status_id.id),
                ('state', '=', 'validate'),
                ('request_date_from', '>=', allocation.date_from),
                ('request_date_from', '<', year_start),
            ]
            if allocation.date_to:
                domain.append(
                    ('request_date_from', '<=', allocation.date_to))
            used = sum(Leave.search(domain).mapped('number_of_days'))
            carryover += max(0.0, allocation.number_of_days - used)
        return carryover

    def get_reconciliation_data(self):
        """Mutabakat formunun kullandığı bakiye verisi."""
        self.ensure_one()
        allocations = self._get_year_allocations()
        leaves = self._get_year_leaves()
        carryover = self._get_carryover()
        allocated = sum(allocations.mapped('number_of_days'))
        used = sum(leaves.mapped('number_of_days'))
        return {
            'carryover': carryover,
            'allocated': allocated,
            'used': used,
            'remaining': carryover + allocated - used,
            'leaves': leaves,
            'allocations': allocations,
        }

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'hr_leave_reports_tr.action_report_leave_reconciliation'
        ).report_action(self)
