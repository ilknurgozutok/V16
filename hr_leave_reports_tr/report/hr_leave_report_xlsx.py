# -*- coding: utf-8 -*-
from odoo import models


class LeaveReportXlsx(models.AbstractModel):
    _name = 'report.hr_leave_reports_tr.leave_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'İzin Raporu (XLSX)'

    def generate_xlsx_report(self, workbook, data, wizards):
        title = workbook.add_format({'bold': True, 'font_size': 14})
        subtitle = workbook.add_format({'italic': True})
        header = workbook.add_format({
            'bold': True, 'bg_color': '#D9D9D9', 'border': 1})
        group_fmt = workbook.add_format({
            'bold': True, 'bg_color': '#F2F2F2', 'border': 1})
        cell = workbook.add_format({'border': 1})
        num = workbook.add_format({'border': 1, 'num_format': '0.0'})
        num_bold = workbook.add_format(
            {'border': 1, 'num_format': '0.0', 'bold': True})

        for wizard in wizards:
            sheet = workbook.add_worksheet('İzin Raporu')
            for col, width in enumerate([28, 20, 22, 12, 12, 8, 14, 30]):
                sheet.set_column(col, col, width)

            sheet.write(0, 0, 'İzin Raporu', title)
            sheet.write(1, 0, 'Dönem', subtitle)
            period_from = 'İşe Girişten İtibaren' \
                if wizard.start_from_hire_date \
                else wizard.date_from.strftime('%d/%m/%Y')
            if wizard.start_from_hire_date \
                    and len(wizard.employee_ids) == 1:
                period_from += ' (%s)' % wizard._get_employee_start_label(
                    wizard.employee_ids)
            sheet.write(1, 1, '%s - %s' % (
                period_from, wizard.date_to.strftime('%d/%m/%Y')))
            sheet.write(2, 0, 'Gruplama', subtitle)
            sheet.write(2, 1, dict(wizard._fields['group_by'].selection)
                        .get(wizard.group_by))

            groups = wizard.get_grouped_lines()
            group_label = 'Personel' if wizard.group_by == 'employee' \
                else 'İzin Türü'
            breakdown_label = 'İzin Türü' if wizard.group_by == 'employee' \
                else 'Personel'

            show_hire_col = wizard.start_from_hire_date \
                and len(wizard.employee_ids) != 1
            sheet.write(4, 0, 'Özet', group_fmt)
            summary_headers = [group_label]
            if wizard.group_by == 'employee' and show_hire_col:
                summary_headers.append('İşe Giriş Tarihi')
            summary_headers.append(breakdown_label)
            if wizard.group_by == 'leave_type' and show_hire_col:
                summary_headers.append('İşe Giriş Tarihi')
            summary_headers += ['Tahsis (Gün)', 'Kullanılan (Gün)',
                                'Kalan (Gün)']
            for col, label in enumerate(summary_headers):
                sheet.write(5, col, label, header)
            label_cols = len(summary_headers) - 3
            row = 6
            total_alloc = 0.0
            total_used = 0.0
            total_remaining = 0.0
            for group in groups:
                first_line = True
                for line in group['breakdown']:
                    col = 0
                    sheet.write(
                        row, col, group['name'] if first_line else '', cell)
                    col += 1
                    if wizard.group_by == 'employee' and show_hire_col:
                        sheet.write(
                            row, col,
                            group['hire_label'] if first_line else '', cell)
                        col += 1
                    sheet.write(row, col, line['name'], cell)
                    col += 1
                    if wizard.group_by == 'leave_type' and show_hire_col:
                        sheet.write(row, col, line['hire_label'], cell)
                        col += 1
                    sheet.write_number(row, col, line['allocated_days'], num)
                    sheet.write_number(row, col + 1, line['used_days'], num)
                    sheet.write_number(
                        row, col + 2, line['remaining_days'], num)
                    first_line = False
                    row += 1
                if len(groups) == 1 and len(group['breakdown']) > 1:
                    sheet.merge_range(
                        row, 0, row, label_cols - 1,
                        '%s Toplamı' % group['name'], group_fmt)
                    sheet.write_number(
                        row, label_cols, group['allocated_days'], num_bold)
                    sheet.write_number(
                        row, label_cols + 1, group['summary_used_days'],
                        num_bold)
                    sheet.write_number(
                        row, label_cols + 2, group['summary_remaining_days'],
                        num_bold)
                    row += 1
                total_alloc += group['allocated_days']
                total_used += group['summary_used_days']
                total_remaining += group['summary_remaining_days']
            if not wizard.department_id:
                sheet.merge_range(
                    row, 0, row, label_cols - 1, 'Genel Toplam', header)
                sheet.write_number(row, label_cols, total_alloc, num_bold)
                sheet.write_number(row, label_cols + 1, total_used, num_bold)
                sheet.write_number(
                    row, label_cols + 2, total_remaining, num_bold)
            row += 2

            headers = ['Personel', 'Departman', 'İzin Türü',
                       'Başlangıç', 'Bitiş', 'Gün', 'Durum']
            if wizard.show_description:
                headers.append('Açıklama')
            sheet.write(row, 0, 'İzin Kullanım Detayı', group_fmt)
            row += 1
            for col, label in enumerate(headers):
                sheet.write(row, col, label, header)
            row += 1

            grand_total = 0.0
            states = dict(wizard.env['hr.leave']._fields['state'].selection)
            for group in groups:
                sheet.merge_range(
                    row, 0, row, len(headers) - 1, group['name'], group_fmt)
                row += 1
                for leave in group['leaves']:
                    sheet.write(row, 0, leave.employee_id.name or '', cell)
                    sheet.write(
                        row, 1,
                        leave.employee_id.department_id.name or '', cell)
                    sheet.write(
                        row, 2, leave.holiday_status_id.name or '', cell)
                    sheet.write(
                        row, 3,
                        leave.request_date_from.strftime('%d/%m/%Y'), cell)
                    sheet.write(
                        row, 4,
                        (leave.request_date_to or leave.request_date_from)
                        .strftime('%d/%m/%Y'), cell)
                    sheet.write_number(row, 5, leave.number_of_days, num)
                    sheet.write(row, 6, states.get(leave.state, ''), cell)
                    if wizard.show_description:
                        sheet.write(row, 7, leave.name or '', cell)
                    row += 1
                sheet.merge_range(
                    row, 0, row, 4,
                    '%s Ara Toplamı (Kullanılan İzin)' % group['name'],
                    group_fmt)
                sheet.write_number(row, 5, group['total_days'], num_bold)
                row += 1
                grand_total += group['total_days']
            sheet.merge_range(
                row, 0, row, 4, 'Genel Toplam (Kullanılan İzin)', header)
            sheet.write_number(row, 5, grand_total, num_bold)
