# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrLeaveReportWizard(models.TransientModel):
    _name = 'hr.leave.report.wizard'
    _description = 'İzin Raporu Sihirbazı'

    def _default_date_from(self):
        return fields.Date.context_today(self).replace(month=1, day=1)

    date_from = fields.Date(
        string='Başlangıç Tarihi', required=True, default=_default_date_from)
    date_to = fields.Date(
        string='Bitiş Tarihi', required=True,
        default=fields.Date.context_today)
    group_by = fields.Selection([
        ('employee', 'Personel Bazlı'),
        ('leave_type', 'İzin Türü Bazlı'),
    ], string='Gruplama', default='employee', required=True)
    employee_ids = fields.Many2many(
        'hr.employee', string='Personeller',
        help='Boş bırakılırsa şirketteki tüm personel rapora dahil edilir.')
    department_id = fields.Many2one('hr.department', string='Departman')
    holiday_status_id = fields.Many2one(
        'hr.leave.type', string='İzin Türü',
        help='Boş bırakılırsa tüm izin türleri rapora dahil edilir.')
    state = fields.Selection([
        ('validate', 'Onaylanmış'),
        ('all', 'Tümü (İptal/Reddedilen hariç)'),
    ], string='Durum', default='validate', required=True)
    company_id = fields.Many2one(
        'res.company', string='Şirket', required=True,
        default=lambda self: self.env.company)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_(
                    'Başlangıç tarihi bitiş tarihinden sonra olamaz.'))

    def _get_leave_domain(self):
        self.ensure_one()
        domain = [
            ('employee_id.company_id', '=', self.company_id.id),
            ('request_date_from', '<=', self.date_to),
            '|', ('request_date_to', '=', False),
            ('request_date_to', '>=', self.date_from),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(
                ('employee_id.department_id', 'child_of', self.department_id.id))
        if self.holiday_status_id:
            domain.append(
                ('holiday_status_id', '=', self.holiday_status_id.id))
        if self.state == 'validate':
            domain.append(('state', '=', 'validate'))
        else:
            domain.append(('state', 'not in', ('refuse', 'cancel')))
        return domain

    def _get_allocation_domain(self):
        self.ensure_one()
        domain = [
            ('employee_id.company_id', '=', self.company_id.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', self.date_to),
            '|', ('date_to', '=', False), ('date_to', '>=', self.date_from),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(
                ('employee_id.department_id', 'child_of', self.department_id.id))
        if self.holiday_status_id:
            domain.append(
                ('holiday_status_id', '=', self.holiday_status_id.id))
        return domain

    def _get_leaves(self):
        self.ensure_one()
        return self.env['hr.leave'].search(
            self._get_leave_domain(), order='request_date_from')

    def get_grouped_lines(self):
        """PDF ve XLSX raporlarının ortak kullandığı gruplanmış veri.
        Her grup; izin kayıtları, dönemdeki tahsis ve kalan gün bilgisini içerir."""
        self.ensure_one()
        key_field = 'employee_id' if self.group_by == 'employee' \
            else 'holiday_status_id'
        leaves = self._get_leaves()
        allocations = self.env['hr.leave.allocation'].search(
            self._get_allocation_domain())
        groups = OrderedDict()
        for leave in leaves:
            groups.setdefault(leave[key_field], self.env['hr.leave'])
            groups[leave[key_field]] |= leave
        for allocation in allocations:
            groups.setdefault(allocation[key_field], self.env['hr.leave'])
        result = []
        for record, leaves in sorted(
                groups.items(), key=lambda kv: kv[0].display_name or ''):
            group_allocations = allocations.filtered(
                lambda a: a[key_field] == record)
            allocated = sum(group_allocations.mapped('number_of_days'))
            used = sum(leaves.mapped('number_of_days'))
            result.append({
                'record': record,
                'name': record.display_name,
                'leaves': leaves,
                'total_days': used,
                'allocated_days': allocated,
                'remaining_days': allocated - used,
            })
        return result

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            'hr_leave_reports_tr.action_report_leave').report_action(self)

    def action_print_xlsx(self):
        self.ensure_one()
        return self.env.ref(
            'hr_leave_reports_tr.action_report_leave_xlsx').report_action(self)
