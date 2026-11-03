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
            sheet.write(1, 1, '%s - %s' % (
                wizard.date_from.strftime('%d/%m/%Y'),
                wizard.date_to.strftime('%d/%m/%Y')))
            sheet.write(2, 0, 'Gruplama', subtitle)
            sheet.write(2, 1, dict(wizard._fields['group_by'].selection)
                        .get(wizard.group_by))

            headers = ['Personel', 'Departman', 'İzin Türü',
                       'Başlangıç', 'Bitiş', 'Gün', 'Durum', 'Açıklama']
            for col, label in enumerate(headers):
                sheet.write(4, col, label, header)

            row = 5
            grand_total = 0.0
            states = dict(wizard.env['hr.leave']._fields['state'].selection)
            for group in wizard.get_grouped_lines():
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
                    sheet.write(row, 7, leave.name or '', cell)
                    row += 1
                sheet.merge_range(row, 0, row, 4, '%s Toplamı' % group['name'],
                                  group_fmt)
                sheet.write_number(row, 5, group['total_days'], num_bold)
                row += 1
                grand_total += group['total_days']
            sheet.merge_range(row, 0, row, 4, 'Genel Toplam', header)
            sheet.write_number(row, 5, grand_total, num_bold)
