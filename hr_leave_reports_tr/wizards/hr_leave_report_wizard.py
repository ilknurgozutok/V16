# -*- coding: utf-8 -*-
from collections import OrderedDict

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date


class HrLeaveReportWizard(models.TransientModel):
    _name = 'hr.leave.report.wizard'
    _description = 'İzin Raporu Sihirbazı'

    def _default_date_from(self):
        return fields.Date.context_today(self).replace(month=1, day=1)

    date_from = fields.Date(
        string='Başlangıç Tarihi', required=True, default=_default_date_from)
    start_from_hire_date = fields.Boolean(
        string='İşe Girişten İtibaren',
        help='İşaretliyse her personel kendi işe giriş tarihinden itibaren '
             'raporlanır; başlangıç tarihi alanı yok sayılır.')
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
    holiday_status_ids = fields.Many2many(
        'hr.leave.type', string='İzin Türleri',
        help='Boş bırakılırsa tüm izin türleri rapora dahil edilir.')
    state = fields.Selection([
        ('validate', 'Onaylanmış'),
        ('all', 'Tümü (İptal/Reddedilen hariç)'),
    ], string='Durum', default='validate', required=True)
    show_description = fields.Boolean(
        string='Açıklamaları Göster',
        help='İşaretliyse detay tablosunda izin açıklamaları da listelenir.')
    company_id = fields.Many2one(
        'res.company', string='Şirket', required=True,
        default=lambda self: self.env.company)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_(
                    'Başlangıç tarihi bitiş tarihinden sonra olamaz.'))

    def _get_employee_start(self, employee):
        """'İşe Girişten İtibaren' açıkken personelin etkin dönem başlangıcı."""
        self.ensure_one()
        if not self.start_from_hire_date:
            return self.date_from
        if 'first_contract_date' in employee._fields \
                and employee.first_contract_date:
            return fields.Date.to_date(employee.first_contract_date)
        return self.date_from

    def _get_employee_start_label(self, employee):
        """Rapor çıktısında gösterilecek işe giriş tarihi etiketi."""
        self.ensure_one()
        if 'first_contract_date' in employee._fields \
                and employee.first_contract_date:
            return format_date(self.env, employee.first_contract_date)
        return _('tarih yok')

    def _start_label(self, record):
        """Personel kaydıysa ve mod açıksa işe giriş etiketi, yoksa boş."""
        if self.start_from_hire_date and record._name == 'hr.employee':
            return self._get_employee_start_label(record)
        return ''

    def _get_target_employees(self):
        self.ensure_one()
        if self.employee_ids:
            return self.employee_ids
        domain = [('company_id', '=', self.company_id.id)]
        if self.department_id:
            domain.append(
                ('department_id', 'child_of', self.department_id.id))
        return self.env['hr.employee'].search(domain)

    def _get_leave_domain(self):
        self.ensure_one()
        floor = self.date_from
        if self.start_from_hire_date:
            starts = [self._get_employee_start(emp)
                      for emp in self._get_target_employees()]
            floor = min(starts) if starts else self.date_from
        domain = [
            ('employee_id.company_id', '=', self.company_id.id),
            ('request_date_from', '<=', self.date_to),
            '|', ('request_date_to', '=', False),
            ('request_date_to', '>=', floor),
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(
                ('employee_id.department_id', 'child_of', self.department_id.id))
        if self.holiday_status_ids:
            domain.append(
                ('holiday_status_id', 'in', self.holiday_status_ids.ids))
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
        ]
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(
                ('employee_id.department_id', 'child_of', self.department_id.id))
        if self.holiday_status_ids:
            domain.append(
                ('holiday_status_id', 'in', self.holiday_status_ids.ids))
        return domain

    @staticmethod
    def _get_allocation_year(allocation):
        """Tahsisin ait olduğu yıl: geçerlilik başlangıç (date_from) yılı."""
        start = fields.Date.to_date(allocation.date_from)
        if start:
            return start.year
        return allocation.create_date.year

    def _get_allocations(self):
        """Seçilen döneme ait tahsisler: tahsisin ait olduğu yıl dönemin
        yıl aralığı içinde olmalı (süresiz tahsisler her yıla sayılmaz).
        'İşe Girişten İtibaren' modunda tahsisler işe giriş filtresine tabi
        değildir; personelin tüm onaylı tahsisleri sayılır."""
        self.ensure_one()
        allocations = self.env['hr.leave.allocation'].search(
            self._get_allocation_domain())
        return allocations.filtered(
            lambda a: self._get_allocation_year(a) <= self.date_to.year
            and (self.start_from_hire_date
                 or self._get_allocation_year(a) >= self.date_from.year))

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
        breakdown_field = 'holiday_status_id' if self.group_by == 'employee' \
            else 'employee_id'
        leaves = self._get_leaves()
        allocations = self._get_allocations()
        if self.start_from_hire_date:
            leaves = leaves.filtered(
                lambda l: (l.request_date_to or l.request_date_from)
                >= self._get_employee_start(l.employee_id))
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
            breakdown_records = group_allocations.mapped(
                breakdown_field).sorted('name')
            breakdown = []
            for brecord in breakdown_records:
                b_leaves = leaves.filtered(
                    lambda l: l[breakdown_field] == brecord)
                b_allocations = group_allocations.filtered(
                    lambda a: a[breakdown_field] == brecord)
                b_allocated = sum(b_allocations.mapped('number_of_days'))
                b_used = sum(b_leaves.mapped('number_of_days'))
                breakdown.append({
                    'record': brecord,
                    'name': brecord.display_name,
                    'hire_label': self._start_label(brecord),
                    'allocated_days': b_allocated,
                    'used_days': b_used,
                    'remaining_days': b_allocated - b_used,
                })
            summary_used = sum(b['used_days'] for b in breakdown)
            result.append({
                'record': record,
                'name': record.display_name,
                'hire_label': self._start_label(record),
                'leaves': leaves,
                'total_days': used,
                'allocated_days': allocated,
                'remaining_days': allocated - used,
                'summary_used_days': summary_used,
                'summary_remaining_days': allocated - summary_used,
                'breakdown': breakdown,
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
