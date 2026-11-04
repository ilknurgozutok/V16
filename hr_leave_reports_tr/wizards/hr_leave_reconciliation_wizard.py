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

    def _get_all_allocations(self):
        return self.env['hr.leave.allocation'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
            ('state', '=', 'validate'),
        ])

    @staticmethod
    def _get_allocation_year(allocation):
        """Tahsisin ait olduğu yıl: geçerlilik başlangıç (date_from) yılı."""
        start = fields.Date.to_date(allocation.date_from)
        if start:
            return start.year
        return allocation.create_date.year

    def _get_leaves_in_period(self, period_start, period_end):
        return self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', period_end),
            '|', ('request_date_to', '=', False),
            ('request_date_to', '>=', period_start),
        ], order='request_date_from')

    def _get_year_allocations(self):
        self.ensure_one()
        return self._get_all_allocations().filtered(
            lambda a: self._get_allocation_year(a) == self.year)

    def _get_year_leaves(self):
        self.ensure_one()
        year_start, year_end = self._get_year_bounds()
        return self._get_leaves_in_period(year_start, year_end)

    def _get_start_year(self):
        """Tablonun başlayacağı yıl: işe giriş, ilk tahsis ve ilk izin
        yıllarından en erkeni (hatalı erken kayıtlar da görünsün)."""
        self.ensure_one()
        emp = self.employee_id
        years = []
        if 'first_contract_date' in emp._fields and emp.first_contract_date:
            years.append(emp.first_contract_date.year)
        first_leave = self.env['hr.leave'].search([
            ('employee_id', '=', emp.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
        ], order='request_date_from', limit=1)
        if first_leave:
            years.append(first_leave.request_date_from.year)
        first_allocation = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', emp.id),
            ('holiday_status_id', '=', self.holiday_status_id.id),
        ], order='date_from', limit=1)
        if first_allocation and first_allocation.date_from:
            years.append(
                fields.Date.to_date(first_allocation.date_from).year)
        if not years:
            return self.year
        return min(min(years), self.year)

    def _get_yearly_summary(self):
        """İşe başlangıç yılından seçilen yıla kadar yıl bazında
        tahsis/kullanılan satırları ve kümülatif kalan bakiye."""
        self.ensure_one()
        allocated_by_year = {}
        for allocation in self._get_all_allocations():
            year = self._get_allocation_year(allocation)
            allocated_by_year[year] = allocated_by_year.get(year, 0.0) \
                + allocation.number_of_days
        lines = []
        balance = 0.0
        for year in range(self._get_start_year(), self.year + 1):
            year_start, year_end = date(year, 1, 1), date(year, 12, 31)
            allocated = allocated_by_year.get(year, 0.0)
            used = sum(self._get_leaves_in_period(
                year_start, year_end).mapped('number_of_days'))
            balance += allocated - used
            lines.append({
                'year': year,
                'allocated': allocated,
                'used': used,
                'remaining': balance,
            })
        return lines

    def get_reconciliation_data(self):
        """Mutabakat formunun kullandığı bakiye verisi."""
        self.ensure_one()
        allocations = self._get_year_allocations()
        leaves = self._get_year_leaves()
        allocated = sum(allocations.mapped('number_of_days'))
        used = sum(leaves.mapped('number_of_days'))
        yearly_summary = self._get_yearly_summary()
        # Devir: seçilen yıldan önceki yılların kümülatif net bakiyesi
        carryover = sum(
            line['allocated'] - line['used']
            for line in yearly_summary if line['year'] < self.year)
        return {
            'start_year': yearly_summary and
                yearly_summary[0]['year'] or self.year,
            'carryover': carryover,
            'allocated': allocated,
            'used': used,
            'remaining': carryover + allocated - used,
            'leaves': leaves,
            'allocations': allocations,
            'yearly_summary': yearly_summary,
            'yearly_allocated_total': sum(
                line['allocated'] for line in yearly_summary),
            'yearly_used_total': sum(
                line['used'] for line in yearly_summary),
            'yearly_remaining': yearly_summary and
                yearly_summary[-1]['remaining'] or 0.0,
        }

    def action_print(self):
        self.ensure_one()
        return self.env.ref(
            'hr_leave_reports_tr.action_report_leave_reconciliation'
        ).report_action(self)
