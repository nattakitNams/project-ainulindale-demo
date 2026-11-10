# -*- coding: utf-8 -*-
"""ชุดใน Data hub ต้องมีบัญชี/โทเคนไหม — กติกาเดียวกับ web/hub.js (hubAccess) · แก้ที่หนึ่งต้องแก้อีกที่ด้วย

ระดับ: app = ดึงเข้าแอปได้เลย · open = ดาวน์โหลดเองได้ ไม่ต้องบัญชี · account = ต้องสมัคร/ล็อกอิน · key = ต้องมี API key ของตัวเอง"""
from urllib.parse import urlparse

# โดเมนที่ดาวน์โหลดต้องล็อกอิน (ดูหน้าเว็บได้ แต่ไฟล์ต้องมีบัญชี)
ACCOUNT = {
    'eogdata.mines.edu': 'บัญชี EOG (Colorado School of Mines)',
    'earthexplorer.usgs.gov': 'บัญชี USGS EROS',
    'search.earthdata.nasa.gov': 'บัญชี NASA Earthdata',
    'oceancolor.gsfc.nasa.gov': 'บัญชี NASA Earthdata',
    'search.asf.alaska.edu': 'บัญชี NASA Earthdata (ASF)',
    'dataspace.copernicus.eu': 'บัญชี Copernicus Data Space',
    'marine.copernicus.eu': 'บัญชี Copernicus Marine',
    'www.emdat.be': 'บัญชี EM-DAT',
    'globalfishingwatch.org': 'บัญชี Global Fishing Watch',
    'glad.earthengine.app': 'บัญชี Google Earth Engine (ไฟล์ดิบ) / ดูบนเว็บได้',
}
KEY = {
    'firms.modaps.eosdis.nasa.gov': 'MAP_KEY ของ FIRMS (ขอฟรีด้วยอีเมล)',
    'opentopography.org': 'API key ของ OpenTopography (สมัครฟรี)',
}


def access(it, sat_ids=None):
    """(ระดับ, คำอธิบาย) ของรายการใน index"""
    s = it.get('s')
    if s == 'gee':
        return 'account', 'บัญชี Google Earth Engine (ลงทะเบียนฟรี) — ไม่มีไฟล์ตรง ต้องส่งออกจาก GEE เอง'
    if s == 'pc':
        cid = (it.get('k') or '').split(':', 1)[-1]
        if sat_ids is not None and cid in sat_ids:
            return 'app', 'ดึงเข้าแอปได้เลย (เครื่องมือ → ภาพดาวเทียม) ไม่ต้องมีบัญชี'
        return 'open', 'ไม่ต้องมีบัญชี — Planetary Computer ออกโทเคนชั่วคราวให้อัตโนมัติ'
    if it.get('ni'):
        return 'app', 'มีไฟล์ที่แอปนำเข้าคลังได้เอง'
    host = urlparse(it.get('u') or '').netloc.lower()
    if host in KEY:
        return 'key', KEY[host]
    if host in ACCOUNT:
        return 'account', ACCOUNT[host]
    return 'open', 'เปิด — ดาวน์โหลดจากหน้าเว็บได้โดยไม่ต้องล็อกอิน (ตรวจเงื่อนไขการใช้ก่อน)'
