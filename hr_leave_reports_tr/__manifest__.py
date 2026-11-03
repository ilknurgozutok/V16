# -*- coding: utf-8 -*-
{
    'name': 'İzin Raporları ve Yıllık İzin Mutabakatı',
    'summary': 'Personel/izin türü bazlı izin raporları (PDF/Excel) ve yıllık izin mutabakat formu',
    'description': """
        İzin (Time Off) raporlaması:
        - Dönem, personel, departman ve izin türü filtreli izin raporu
        - Personel bazlı veya izin türü bazlı gruplama
        - PDF ve Excel (XLSX) çıktısı
        - İşten ayrılırken imzalatılabilen yıllık izin mutabakat formu
    """,
    'author': 'Quanimo',
    'website': 'https://www.quanimo.com',
    'category': 'Human Resources/Time Off',
    'version': '16.0.1.0.0',
    'depends': ['hr_holidays', 'report_xlsx'],
    'data': [
        'security/ir.model.access.csv',
        'wizards/hr_leave_report_wizard_views.xml',
        'wizards/hr_leave_reconciliation_wizard_views.xml',
        'report/hr_leave_report_actions.xml',
        'report/hr_leave_report_templates.xml',
        'views/hr_leave_reports_menus.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
