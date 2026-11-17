# -*- coding: utf-8 -*-
"""İzin raporu ve mutabakat sihirbazlarının ortak yardımcıları."""
from odoo import fields


def get_allocation_year(allocation):
    """Tahsisin ait olduğu yıl: geçerlilik başlangıç (date_from) yılı."""
    start = fields.Date.to_date(allocation.date_from)
    if start:
        return start.year
    return allocation.create_date.year


def get_employee_private_date(employee, field_name):
    """hr.group_hr_user'a özel tarih alanlarını (first_contract_date,
    departure_date) okur. İzin yetkilisi bu gruba sahip olmayabileceği için
    alan sudo ile okunur; alan kurulu değilse False döner."""
    if not employee or field_name not in employee._fields:
        return False
    return fields.Date.to_date(employee.sudo()[field_name]) or False


def get_hire_date(employee):
    """Personelin işe giriş tarihi (hr_contract kuruluysa)."""
    return get_employee_private_date(employee, 'first_contract_date')
