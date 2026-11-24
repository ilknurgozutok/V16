# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


class TestLeaveReportsCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.leave_type = cls.env['hr.leave.type'].create({
            'name': 'Test Yıllık İzin',
            'requires_allocation': 'yes',
            'allocation_validation_type': 'officer',
            'leave_validation_type': 'hr',
            'request_unit': 'day',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Personel',
            'company_id': cls.company.id,
        })
        cls.employee2 = cls.env['hr.employee'].create({
            'name': 'Test Personel 2',
            'company_id': cls.company.id,
        })
        cls.alloc_2025 = cls._create_allocation(cls.employee, date(2025, 1, 1), 14)
        cls.alloc_2026 = cls._create_allocation(cls.employee, date(2026, 1, 1), 14)
        # Yıl sınırını aşan izin: 29.12.2025 - 02.01.2026 (5 gün)
        cls.leave_cross = cls._create_leave(
            cls.employee, date(2025, 12, 29), date(2026, 1, 2), 5)
        cls.leave_2025 = cls._create_leave(
            cls.employee, date(2025, 3, 3), date(2025, 3, 4), 2)
        cls.leave_2026 = cls._create_leave(
            cls.employee, date(2026, 3, 2), date(2026, 3, 4), 3)

    @classmethod
    def _create_allocation(cls, employee, date_from, days):
        allocation = cls.env['hr.leave.allocation'].create({
            'name': 'Tahsis %s' % date_from.year,
            'employee_id': employee.id,
            'holiday_status_id': cls.leave_type.id,
            'number_of_days': days,
            'date_from': date_from,
            'allocation_type': 'regular',
        })
        allocation.action_validate()
        return allocation

    @classmethod
    def _create_leave(cls, employee, date_from, date_to, days):
        return cls.env['hr.leave'].with_context(
            leave_fast_create=True,
            leave_skip_state_check=True,
            leave_skip_date_check=True,
        ).create({
            'name': 'İzin',
            'employee_id': employee.id,
            'holiday_status_id': cls.leave_type.id,
            'date_from': datetime.combine(date_from, datetime.min.time()).replace(hour=8),
            'date_to': datetime.combine(date_to, datetime.min.time()).replace(hour=17),
            'request_date_from': date_from,
            'request_date_to': date_to,
            'number_of_days': days,
            'state': 'validate',
        })

    def _report_wizard(self, **vals):
        values = {
            'date_from': date(2025, 1, 1),
            'date_to': date(2025, 12, 31),
            'employee_ids': [(6, 0, self.employee.ids)],
            'holiday_status_ids': [(6, 0, self.leave_type.ids)],
            'company_id': self.company.id,
        }
        values.update(vals)
        return self.env['hr.leave.report.wizard'].create(values)

    def _reconciliation_wizard(self, year=2026, employee=None):
        return self.env['hr.leave.reconciliation.wizard'].create({
            'employee_id': (employee or self.employee).id,
            'holiday_status_id': self.leave_type.id,
            'year': year,
        })


@tagged('post_install', '-at_install')
class TestLeaveReports(TestLeaveReportsCommon):

    # ------------------------------------------------------------------
    # Mutabakat: yıl sınırını aşan izin tek kez sayılmalı
    # ------------------------------------------------------------------
    def test_reconciliation_cross_year_leave_counted_once(self):
        cross = self.leave_cross.number_of_days
        used_2025 = cross + self.leave_2025.number_of_days
        used_2026 = self.leave_2026.number_of_days

        data = self._reconciliation_wizard(2026).get_reconciliation_data()
        by_year = {line['year']: line for line in data['yearly_summary']}

        self.assertEqual(data['start_year'], 2025)
        self.assertAlmostEqual(by_year[2025]['used'], used_2025)
        self.assertAlmostEqual(by_year[2026]['used'], used_2026)
        self.assertAlmostEqual(data['carryover'], 14 - used_2025)
        self.assertAlmostEqual(data['used'], used_2026)
        self.assertAlmostEqual(data['remaining'], 28 - used_2025 - used_2026)
        self.assertAlmostEqual(data['yearly_remaining'], data['remaining'])
        self.assertAlmostEqual(
            data['yearly_used_total'], used_2025 + used_2026,
            msg='Yıl sınırını aşan izin iki kez sayılmamalı')
        self.assertNotIn(self.leave_cross, data['leaves'])

    # ------------------------------------------------------------------
    # İzin raporu: ardışık dönemlerde izin tek kez sayılmalı
    # ------------------------------------------------------------------
    def test_report_consecutive_periods_count_leave_once(self):
        total = sum((self.leave_cross | self.leave_2025 | self.leave_2026)
                    .mapped('number_of_days'))
        used = 0.0
        for year in (2025, 2026):
            wizard = self._report_wizard(
                date_from=date(year, 1, 1), date_to=date(year, 12, 31))
            groups = wizard.get_grouped_lines()
            used += sum(g['total_days'] for g in groups)
        self.assertAlmostEqual(used, total)

    def test_report_grouped_lines_by_leave_type(self):
        wizard = self._report_wizard(group_by='leave_type')
        groups = wizard.get_grouped_lines()
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group['record'], self.leave_type)
        self.assertEqual(group['leaves'], self.leave_cross | self.leave_2025)
        self.assertAlmostEqual(group['allocated_days'], 14)
        self.assertEqual(group['breakdown'][0]['record'], self.employee)

    # ------------------------------------------------------------------
    # 'İşe Girişten İtibaren' modu
    # ------------------------------------------------------------------
    def test_hire_mode_ignores_hidden_date_from(self):
        with self.assertRaises(ValidationError):
            self._report_wizard(
                date_from=date(2026, 1, 1), date_to=date(2025, 12, 31))
        # Gizli başlangıç tarihi bitişten sonra olsa da hata verilmemeli
        wizard = self._report_wizard(
            start_from_hire_date=True,
            date_from=date(2026, 1, 1), date_to=date(2025, 12, 31))
        self.assertTrue(wizard)

    def test_hire_mode_without_hire_date_reports_full_history(self):
        if 'first_contract_date' in self.employee._fields:
            self.assertFalse(self.employee.first_contract_date)
        wizard = self._report_wizard(
            start_from_hire_date=True,
            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        leaves = wizard.get_grouped_lines()[0]['leaves']
        self.assertEqual(
            leaves, self.leave_2025 | self.leave_cross | self.leave_2026,
            'İşe giriş tarihi olmayan personelin tüm geçmişi raporlanmalı')

    # ------------------------------------------------------------------
    # Server action
    # ------------------------------------------------------------------
    def test_server_action_requires_single_employee(self):
        action = self.env.ref(
            'hr_leave_reports_tr.action_leave_reconciliation_server')
        employees = self.employee | self.employee2
        with self.assertRaises(UserError):
            action.with_context(
                active_model='hr.employee', active_ids=employees.ids,
                active_id=employees[0].id).run()
        result = action.with_context(
            active_model='hr.employee', active_ids=self.employee.ids,
            active_id=self.employee.id).run()
        wizard = self.env['hr.leave.reconciliation.wizard'].browse(
            result['res_id'])
        self.assertEqual(wizard.employee_id, self.employee)

    # ------------------------------------------------------------------
    # Çıktıların üretilmesi
    # ------------------------------------------------------------------
    def test_render_reports(self):
        report = self.env['ir.actions.report']
        for group_by in ('employee', 'leave_type'):
            wizard = self._report_wizard(
                group_by=group_by, show_description=True)
            html = report._render_qweb_html(
                'hr_leave_reports_tr.action_report_leave', wizard.ids)[0]
            self.assertIn(b'Test Personel', html)
            content, ext = report._render_xlsx(
                'hr_leave_reports_tr.action_report_leave_xlsx',
                wizard.ids, None)
            self.assertEqual(ext, 'xlsx')
            self.assertTrue(content)
        wizard = self._reconciliation_wizard(2026)
        html = report._render_qweb_html(
            'hr_leave_reports_tr.action_report_leave_reconciliation',
            wizard.ids)[0]
        self.assertIn(b'YILLIK', html)

    # ------------------------------------------------------------------
    # Danışman kararları (bilinçli tasarım)
    # ------------------------------------------------------------------
    def test_unallocated_leave_type_only_in_detail(self):
        """Tahsissiz izin türü özet tabloda yer almaz, detayda listelenir."""
        free_type = self.env['hr.leave.type'].create({
            'name': 'Test Mazeret İzni',
            'requires_allocation': 'no',
            'leave_validation_type': 'hr',
            'request_unit': 'day',
            'company_id': self.company.id,
        })
        free_leave = self.env['hr.leave'].with_context(
            leave_fast_create=True, leave_skip_state_check=True,
            leave_skip_date_check=True,
        ).create({
            'name': 'Mazeret',
            'employee_id': self.employee.id,
            'holiday_status_id': free_type.id,
            'date_from': datetime(2025, 5, 5, 8),
            'date_to': datetime(2025, 5, 5, 17),
            'request_date_from': date(2025, 5, 5),
            'request_date_to': date(2025, 5, 5),
            'number_of_days': 1,
            'state': 'validate',
        })
        wizard = self._report_wizard(
            holiday_status_ids=[(6, 0, (self.leave_type | free_type).ids)])
        group = wizard.get_grouped_lines()[0]
        self.assertIn(free_leave, group['leaves'])
        self.assertEqual(
            [line['record'] for line in group['breakdown']],
            [self.leave_type])

    def test_short_period_uses_full_year_allocation(self):
        """Kısa dönemde özet birikimlidir: geçerli tüm tahsisler sayılır,
        kullanım detayı dönemden gelir."""
        wizard = self._report_wizard(
            date_from=date(2026, 3, 1), date_to=date(2026, 3, 31))
        group = wizard.get_grouped_lines()[0]
        self.assertAlmostEqual(group['allocated_days'], 28)
        self.assertEqual(group['leaves'], self.leave_2026)

    def test_allocated_type_without_allocation_shows_negative(self):
        """'Tahsisat gerektirir' türde tahsis yok ama kullanım varsa
        özet satırı Tahsis 0 / negatif Kalan ile görünür."""
        free_type = self.env['hr.leave.type'].create({
            'name': 'Test İkame İzni',
            'requires_allocation': 'yes',
            'allocation_validation_type': 'officer',
            'leave_validation_type': 'hr',
            'request_unit': 'day',
            'company_id': self.company.id,
        })
        self.env['hr.leave'].with_context(
            leave_fast_create=True, leave_skip_state_check=True,
            leave_skip_date_check=True,
        ).create({
            'name': 'İkame kullanım',
            'employee_id': self.employee.id,
            'holiday_status_id': free_type.id,
            'date_from': datetime(2025, 6, 2, 8),
            'date_to': datetime(2025, 6, 2, 17),
            'request_date_from': date(2025, 6, 2),
            'request_date_to': date(2025, 6, 2),
            'number_of_days': 1,
            'state': 'validate',
        })
        wizard = self._report_wizard(
            holiday_status_ids=[(6, 0, (self.leave_type | free_type).ids)])
        group = wizard.get_grouped_lines()[0]
        rows = {line['record']: line for line in group['breakdown']}
        self.assertIn(free_type, rows)
        self.assertAlmostEqual(rows[free_type]['allocated_days'], 0)
        self.assertAlmostEqual(rows[free_type]['used_days'], 1)
        self.assertAlmostEqual(rows[free_type]['remaining_days'], -1)

    def test_grand_total_visible_with_department_filter(self):
        department = self.env['hr.department'].create({
            'name': 'Test Departman', 'company_id': self.company.id})
        self.employee.department_id = department
        wizard = self._report_wizard(
            employee_ids=[(5, 0, 0)], department_id=department.id)
        html = self.env['ir.actions.report']._render_qweb_html(
            'hr_leave_reports_tr.action_report_leave', wizard.ids)[0]
        self.assertIn(b'Genel Toplam</strong>', html)


@tagged('post_install', '-at_install')
class TestLeaveReportsHireDate(TestLeaveReportsCommon):
    """hr_contract kuruluyken işe giriş tarihi ve yetki senaryoları."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_contract = 'hr.contract' in cls.env
        if not cls.has_contract:
            return
        cls.env['hr.contract'].create({
            'name': 'Sözleşme',
            'employee_id': cls.employee.id,
            'wage': 1000,
            'date_start': date(2025, 6, 1),
            'state': 'open',
        })
        cls.employee.departure_date = date(2026, 6, 30)
        cls.officer = cls.env['res.users'].create({
            'name': 'İzin Yetkilisi',
            'login': 'leave_officer_tr_test',
            'company_id': cls.company.id,
            'company_ids': [(6, 0, cls.company.ids)],
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('hr_holidays.group_hr_holidays_user').id,
            ])],
        })

    def setUp(self):
        super().setUp()
        if not self.has_contract:
            self.skipTest('hr_contract kurulu değil')

    def test_hire_mode_filters_leaves_before_hire_date(self):
        self.assertEqual(self.employee.first_contract_date, date(2025, 6, 1))
        wizard = self._report_wizard(
            start_from_hire_date=True,
            date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
        group = wizard.get_grouped_lines()[0]
        self.assertEqual(group['leaves'], self.leave_cross | self.leave_2026)
        self.assertNotIn(self.leave_2025, group['leaves'])

    def test_officer_without_hr_user_group(self):
        """hr.group_hr_user olmayan izin yetkilisi raporları alabilmeli."""
        self.assertFalse(self.officer.has_group('hr.group_hr_user'))
        env = self.env(user=self.officer)
        wizard = env['hr.leave.report.wizard'].create({
            'date_from': date(2025, 1, 1),
            'date_to': date(2026, 12, 31),
            'start_from_hire_date': True,
            'employee_ids': [(6, 0, self.employee.ids)],
            'company_id': self.company.id,
        })
        group = wizard.get_grouped_lines()[0]
        self.assertTrue(group['hire_label'])
        self.assertNotEqual(group['hire_label'], 'tarih yok')
        env['ir.actions.report']._render_qweb_html(
            'hr_leave_reports_tr.action_report_leave', wizard.ids)
        env['ir.actions.report']._render_xlsx(
            'hr_leave_reports_tr.action_report_leave_xlsx', wizard.ids, None)

        rec_wizard = env['hr.leave.reconciliation.wizard'].create({
            'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'year': 2026,
        })
        data = rec_wizard.get_reconciliation_data()
        self.assertEqual(data['hire_date'], date(2025, 6, 1))
        self.assertEqual(data['departure_date'], date(2026, 6, 30))
        html = env['ir.actions.report']._render_qweb_html(
            'hr_leave_reports_tr.action_report_leave_reconciliation',
            rec_wizard.ids)[0]
        self.assertIn('İşten Ayrılış Tarihi'.encode(), html)
